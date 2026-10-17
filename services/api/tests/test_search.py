"""/v1/search over a real Postgres with model A vectors (revision 0008), served over HTTP.

The deferred step 5 tests: the cursor pages through every hit once and in order, a cursor from
another embedding index gets 409, and a reranker past its timeout gives 200 with degraded: true.
"""

import asyncio
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from datetime import date
from pathlib import Path
from typing import Any

import httpx2
import pytest
from alembic import command
from alembic.config import Config
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import bindparam, insert, text
from sqlalchemy.ext.asyncio import create_async_engine

from filinglens_db.models import Chunk, Company, Filing, FilingStatus, Section, Vector, chunk_id
from filinglens_llm import embed

pytestmark = pytest.mark.integration
PYPROJECT = Path(__file__).parents[3] / "pyproject.toml"
ACCESSION = "0000320193-25-000079"
TOPICS = [
    "Supply chain disruption at single-source component suppliers could delay shipments",
    "Net sales grew because of higher demand for services such as cloud and advertising",
    "Interest rate changes affect the fair value of the marketable debt securities held",
    "The Company faces litigation over patents, antitrust claims and consumer protection",
    "Gross margin depends on product mix, component costs and foreign currency rates",
]
TEXTS = [f"{topic}, case {n}." for topic in TOPICS for n in range(8)]  # 40 chunks
type Start = Callable[..., AbstractContextManager[str]]


async def _seed(url: str) -> None:
    engine = create_async_engine(url)
    filing = insert(Filing).values(
        accession_number=ACCESSION,
        cik=320193,
        form_type="10-K",
        fiscal_year=2025,
        fiscal_period="FY",
        filed_on=date(2025, 10, 31),
        period_end=date(2025, 9, 27),
        primary_document="aapl-20250927.htm",
        status=FilingStatus.INDEXED,
    )
    async with engine.begin() as connection:
        await connection.execute(insert(Company).values(cik=320193, ticker="AAPL", name="Apple"))
        filing_id = (await connection.execute(filing.returning(Filing.id))).scalar_one()
        section = insert(Section).values(
            filing_id=filing_id, item="1A", title="Risk Factors", char_start=0, char_end=9
        )
        section_id = (await connection.execute(section.returning(Section.id))).scalar_one()
        rows = [
            {
                "id": chunk_id(ACCESSION, "1A", n),
                "section_id": section_id,
                "char_start": n,
                "text": chunk,
                "token_count": 20,
            }
            for n, chunk in enumerate(TEXTS)
        ]
        await connection.execute(insert(Chunk), rows)
        vectors = embed(TEXTS, "BAAI/bge-small-en-v1.5")
        update = text("UPDATE chunks SET embedding = :vector WHERE id = :id").bindparams(
            bindparam("vector", type_=Vector(384))
        )
        params = [{"id": row["id"], "vector": v} for row, v in zip(rows, vectors, strict=True)]
        await connection.execute(update, params)
    await engine.dispose()


@pytest.fixture
def served(
    env: pytest.MonkeyPatch, database_url: str, serve: Callable[[], AbstractContextManager[str]]
) -> Iterator[Start]:
    """Serve the app over the seeded database, with settings overridden per call."""
    env.setenv("DATABASE_URL", database_url)
    command.upgrade(Config(toml_file=PYPROJECT), "0008")  # the dev path: model A in `embedding`
    asyncio.run(_seed(database_url))

    def start(**settings: str) -> AbstractContextManager[str]:
        env.setenv("RETRIEVAL_EMBEDDING_COLUMN", "embedding")
        for name, value in settings.items():
            env.setenv(name, value)
        return serve()

    yield start


def get(url: str, key: str, **params: Any) -> httpx2.Response:
    return httpx2.get(f"{url}/v1/search", params=params, headers={"X-API-Key": key}, timeout=60)


def test_the_cursor_pages_through_every_hit_once_in_score_order(
    served: Start, api_key: str
) -> None:
    pages: list[dict[str, Any]] = []
    with served() as url:
        cursor = None
        while True:
            more = {"cursor": cursor} if cursor else {}
            page = get(url, api_key, q="supplier disruption", limit=7, **more).json()
            pages.append(page)
            cursor = page["next_cursor"]
            if cursor is None:
                break
        filtered = get(url, api_key, q="supplier disruption", cik=1, fiscal_year=2025).json()
    hits = [hit for page in pages for hit in page["items"]]
    assert len(hits) == len(TEXTS) and len({h["chunk_id"] for h in hits}) == len(TEXTS)
    assert hits == sorted(hits, key=lambda h: (-h["score"], h["chunk_id"]))
    assert hits[0]["text"].startswith("Supply chain disruption") and not pages[0]["degraded"]
    assert hits[0]["filing"]["fiscal_year"] == 2025 and hits[0]["section"] == "1A"
    assert filtered["items"] == []  # another company: filtered out in SQL


def test_a_cursor_from_another_embedding_index_gets_409(served: Start, api_key: str) -> None:
    with served() as url:
        cursor = get(url, api_key, q="litigation", limit=5).json()["next_cursor"]
    with served(RETRIEVAL_EMBEDDING_COLUMN="embedding_v2") as url:
        response = get(url, api_key, q="litigation", limit=5, cursor=cursor)
    assert response.status_code == 409
    assert response.json()["code"] == "conflict"


def test_a_reranker_timeout_keeps_the_fused_order_and_says_degraded(
    served: Start, api_key: str, metric_changes: Callable[[str], dict[str, float]]
) -> None:
    with served(RERANK_TIMEOUT_MS="1") as url:
        first = get(url, api_key, q="gross margin", limit=20)
        second = get(url, api_key, q="gross margin", limit=20, cursor=first.json()["next_cursor"])
    assert first.status_code == second.status_code == 200
    assert first.json()["degraded"] and second.json()["degraded"]
    hits = first.json()["items"] + second.json()["items"]
    assert len({h["chunk_id"] for h in hits}) == len(TEXTS)  # the fused pages hold together
    # SearchDegraded divides timeouts by reranks; the second page keeps the fused order unasked.
    assert metric_changes("filinglens.search.rerank_timeouts") == {"": 1}
    assert metric_changes("filinglens.search.duration")["phase=rerank"] == 1


def test_a_search_is_one_span_with_a_child_and_a_histogram_per_phase(
    served: Start,
    api_key: str,
    spans: InMemorySpanExporter,
    metric_changes: Callable[[str], dict[str, float]],
) -> None:
    with served() as url:
        assert get(url, api_key, q="supplier disruption", limit=5).status_code == 200
    finished = {span.name: span for span in spans.get_finished_spans()}
    search, server = finished["search"], finished["GET /v1/search"]
    assert search.context is not None and server.context is not None
    assert search.parent is not None and search.parent.span_id == server.context.span_id
    for phase in ("embed", "sql", "load", "rerank"):
        parent = finished[phase].parent
        assert parent is not None and parent.span_id == search.context.span_id
    assert (server.attributes or {})["url.query"] == "q&limit"  # names only
    assert metric_changes("filinglens.search.duration") == {
        f"phase={phase}": 1 for phase in ("embed", "sql", "load", "rerank", "total")
    }
    assert "supplier" not in "".join(span.to_json() for span in finished.values())
