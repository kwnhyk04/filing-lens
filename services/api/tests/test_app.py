import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Iterator
from contextlib import suppress
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from amqp.exceptions import NotFound
from fastapi.testclient import TestClient
from filing_lens_api_client import AuthenticatedClient
from filing_lens_api_client.api.catalog import list_companies
from filing_lens_api_client.models import CompanyPage
from filing_lens_api_client.types import UNSET, Unset
from kombu import Connection, Queue
from redis import Redis
from seed_fake import CIK_BASE, seed_fake
from sqlalchemy import column, func, select, table, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import create_async_engine

from filinglens_api.backend import (
    SEC_ARCHIVES,
    CompanyKey,
    DiscoverQueue,
    ItemKey,
    LiveBackend,
    SearchKey,
    decode_cursor,
    encode_cursor,
)
from filinglens_api.main import app
from filinglens_api.schemas import FormType, Page
from filinglens_core import queues
from filinglens_core.errors import InvalidInputError
from filinglens_db.models import Company, Filing, IngestJobItem, ItemStatus
from filinglens_db.seed import COMPANIES

QUERY = {"query": "{ __typename }"}
PYPROJECT = Path(__file__).parents[3] / "pyproject.toml"


def test_healthz(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok", "checks": {}}


def test_readyz_reports_each_unreachable_dependency(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"] == {"postgres": False, "rabbitmq": False, "redis": False}


def test_request_id_is_reused_when_well_formed_and_generated_otherwise(client: TestClient) -> None:
    reused = client.get("/healthz", headers={"X-Request-ID": "abc-123"})
    assert reused.headers["X-Request-ID"] == "abc-123"
    generated = client.get("/healthz", headers={"X-Request-ID": "not valid!"})
    assert re.fullmatch(r"[0-9a-f]{32}", generated.headers["X-Request-ID"])


@pytest.mark.parametrize("sent", ["no key", "wrong key", "key in the URL"])
def test_graphql_rejects_missing_wrong_or_url_api_key(
    client: TestClient, api_key: str, sent: str
) -> None:
    url, headers = {
        "no key": ("/graphql", {}),
        "wrong key": ("/graphql", {"X-API-Key": "wrong"}),
        "key in the URL": (f"/graphql?api_key={api_key}", {}),  # only the header counts
    }[sent]
    response = client.post(url, json=QUERY, headers=headers)
    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "unauthorized"


@pytest.mark.parametrize("key", ["api_key", "admin_key"])
def test_graphql_accepts_either_key(
    client: TestClient, request: pytest.FixtureRequest, key: str
) -> None:
    headers = {"X-API-Key": request.getfixturevalue(key)}
    response = client.post("/graphql", json=QUERY, headers=headers)
    assert response.json() == {"data": {"__typename": "Query"}}


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/v1/search?q=revenue", None),
        ("POST", "/v1/answers", {"question": "What was revenue?"}),
        ("POST", "/v1/answers/stream", {"question": "What was revenue?"}),
    ],
)
def test_routes_whose_backend_comes_later_answer_501(
    client: TestClient, admin_key: str, method: str, path: str, body: object
) -> None:
    headers = {"X-API-Key": admin_key, "Idempotency-Key": "job-1"}
    response = client.request(method, path, json=body, headers=headers)
    assert response.status_code == 501
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "not_implemented"


def test_graphql_errors_carry_the_taxonomy_code(client: TestClient, api_key: str) -> None:
    query = {"query": '{ answer(question: "What was revenue?") { answer } }'}
    response = client.post("/graphql", json=query, headers={"X-API-Key": api_key})
    assert response.json()["errors"][0]["extensions"] == {"code": "not_implemented"}


def test_cursor_round_trips_and_rejects_anything_else() -> None:
    key = SearchKey(score=0.85, chunk_id="c-2", index_version="v1")
    assert decode_cursor(encode_cursor(key), SearchKey) == key
    for bad in ["", "not-a-cursor", "%%%", encode_cursor(CompanyKey(cik=1))]:
        with pytest.raises(InvalidInputError):
            decode_cursor(bad, SearchKey)


def test_spec_has_both_key_schemes_and_no_framework_validation_schema() -> None:
    spec = app.openapi()
    assert set(spec["components"]["securitySchemes"]) == {"ApiKey", "AdminApiKey"}
    assert "HTTPValidationError" not in spec["components"]["schemas"]


@pytest.mark.integration
def test_readyz_ok_against_real_dependencies(
    env: pytest.MonkeyPatch, postgres_url: str, redis_url: str, rabbitmq_url: str
) -> None:
    env.setenv("DATABASE_URL", postgres_url)
    env.setenv("REDIS_URL", redis_url)
    env.setenv("BROKER_URL", rabbitmq_url)
    with TestClient(app) as client:
        response = client.get("/readyz")
    assert response.status_code == 200, response.json()


@pytest.mark.integration
def test_companies_come_from_postgres_in_cik_order(postgres_user: AuthenticatedClient) -> None:
    ciks: list[int] = []
    cursor: str | Unset = UNSET
    while True:
        page = list_companies.sync(client=postgres_user, limit=4, cursor=cursor)
        assert isinstance(page, CompanyPage)
        ciks += [company.cik for company in page.items]
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    assert ciks == sorted(company["cik"] for company in COMPANIES)


async def _all_pages[T](fetch: Callable[[str | None], Awaitable[Page[T]]]) -> list[T]:
    """Every item, following next_cursor until it is null."""
    items: list[T] = []
    cursor: str | None = None
    while True:
        page = await fetch(cursor)
        items += page.items
        if page.next_cursor is None:
            return items
        cursor = page.next_cursor


async def _page_through_live_backend(url: str, embedding: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            count = select(func.count(column(embedding))).select_from(table("chunks"))
            assert await connection.scalar(count) == 150  # every chunk has a vector
            hnsw = text(
                "SELECT indexname FROM pg_indexes"
                " WHERE tablename = 'chunks' AND indexdef LIKE '%USING hnsw%'"
            )
            # The seed dropped and rebuilt it.
            assert set((await connection.execute(hnsw)).scalars()) == {f"ix_chunks_{embedding}"}
        backend = LiveBackend(engine, DiscoverQueue("amqp://unused:unused@127.0.0.1:1//"))

        filings = await _all_pages(lambda c: backend.list_filings(3, c))
        assert len(filings) == 10
        assert filings == sorted(filings, key=lambda f: (f.filed_on, f.accession_number))[::-1]
        assert filings[0].url.startswith(f"{SEC_ARCHIVES}/{filings[0].cik}/")
        quarters = await _all_pages(
            lambda c: backend.list_filings(2, c, cik=CIK_BASE, form_type=FormType.FORM_10Q)
        )
        assert quarters == [
            f for f in filings if f.cik == CIK_BASE and f.form_type == FormType.FORM_10Q
        ]

        accession = filings[0].accession_number
        sections = await backend.list_sections(accession)
        chunks = await _all_pages(lambda c: backend.list_chunks(accession, 4, c))
        assert [c.section_id for c in chunks] == [s.id for s in sections for _ in range(3)]
        second = await _all_pages(
            lambda c: backend.list_chunks(accession, 2, c, section_id=sections[1].id)
        )
        assert second == chunks[3:6]
        assert (await backend.list_chunks(accession, 2, None, section_id="1x")).items == []
        with pytest.raises(InvalidInputError):
            await backend.list_chunks(accession, 2, encode_cursor(ItemKey(id="unknown")))

        facts = await _all_pages(lambda c: backend.list_facts(accession, 2, c))
        assert [f.concept for f in facts] == [
            "us-gaap:Revenues",
            "us-gaap:NetIncomeLoss",
            "us-gaap:EarningsPerShareDiluted",
        ]
        revenue = await backend.list_facts(accession, 5, None, concept="us-gaap:Revenues")
        assert revenue.items == facts[:1]
    finally:
        await engine.dispose()


@pytest.mark.integration
@pytest.mark.parametrize(
    ("revision", "embedding"),
    [("0007", "embedding"), ("head", "embedding_v2")],  # dev stays at 0007 until the live swap
)
def test_live_backend_pages_seeded_filings_sections_chunks_and_facts(
    database_url: str, monkeypatch: pytest.MonkeyPatch, revision: str, embedding: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(Config(toml_file=PYPROJECT), revision)
    size = {"companies": 2, "filings_per_company": 5, "chunks_per_section": 3}
    assert seed_fake(database_url, **size) == 2
    assert seed_fake(database_url, **size) == 0  # a rerun loads nothing
    asyncio.run(_page_through_live_backend(database_url, embedding))


@pytest.fixture
def live(
    env: pytest.MonkeyPatch, database_url: str, rabbitmq_url: str, redis_url: str
) -> Iterator[TestClient]:
    """The app with its real backend on Postgres at head, RabbitMQ and Redis."""
    for name, url in [("DATABASE_URL", database_url), ("BROKER_URL", rabbitmq_url)]:
        env.setenv(name, url)
    env.setenv("REDIS_URL", redis_url)
    command.upgrade(Config(toml_file=PYPROJECT), "head")
    Redis.from_url(redis_url).flushdb()
    # Purge, not delete: kombu's pooled connections remember the queues they declared.
    with Connection(rabbitmq_url) as broker, suppress(NotFound):  # NotFound: not declared yet
        broker.channel().queue_purge(queues.DISCOVER)
    with TestClient(app) as client:
        yield client


def _queued_discovers(rabbitmq_url: str) -> list[list[Any]]:
    """Take the discover messages off their queue; returns each task's args."""
    found: list[list[Any]] = []
    with Connection(rabbitmq_url) as broker:
        queue = Queue(queues.DISCOVER)(broker)  # basic.get needs no declaration
        while (message := queue.get(no_ack=True)) is not None:
            assert message.headers["task"] == queues.DISCOVER_TASK
            assert message.body is not None
            found.append(json.loads(message.body)[0])
    return found


async def _worker_progress(url: str, job_id: UUID) -> None:
    """What workers leave behind: two filings fetched, two failed for good, one in flight."""
    statuses = [ItemStatus.SUCCEEDED] * 2 + [ItemStatus.FAILED] * 2 + [ItemStatus.RUNNING]
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                insert(Company).values(cik=320193, ticker="AAPL", name="Apple")
            )
            for n, status in enumerate(statuses):
                filing_id = await connection.scalar(
                    insert(Filing)
                    .values(
                        accession_number=f"0000320193-24-{n:06d}",
                        cik=320193,
                        form_type="10-K",
                        filed_on=date(2024, 11, 1),
                        period_end=date(2024, 9, 28),
                        primary_document=f"a{n}.htm",
                    )
                    .returning(Filing.id)
                )
                failed = status is ItemStatus.FAILED
                await connection.execute(
                    insert(IngestJobItem).values(
                        job_id=job_id,
                        filing_id=filing_id,
                        status=status,
                        attempts=7 if failed else 1,
                        error="UpstreamError: SEC answered 503" if failed else None,
                    )
                )
    finally:
        await engine.dispose()


@pytest.mark.integration
def test_ingest_jobs_are_idempotent_queue_discover_and_page_their_failures(
    live: TestClient, database_url: str, rabbitmq_url: str, admin_key: str
) -> None:
    body = {"ciks": [789019, 320193, 789019], "form_types": ["10-K"], "since": "2024-01-01"}
    headers = {"X-API-Key": admin_key, "Idempotency-Key": "job-1"}
    created = live.post("/v1/ingest-jobs", json=body, headers=headers)
    assert created.status_code == 202
    job_id = created.json()["job_id"]
    assert created.headers["Location"] == f"/v1/ingest-jobs/{job_id}"
    assert _queued_discovers(rabbitmq_url) == [[job_id, 320193], [job_id, 789019]]

    # A retry gets the same job; while it is still queued, discover is queued again.
    assert live.post("/v1/ingest-jobs", json=body, headers=headers).json() == {"job_id": job_id}
    assert _queued_discovers(rabbitmq_url) == [[job_id, 320193], [job_id, 789019]]
    reused = live.post("/v1/ingest-jobs", json=body | {"since": "2025-01-01"}, headers=headers)
    assert reused.status_code == 422
    assert reused.json()["code"] == "idempotency_key_reused"

    job = live.get(f"/v1/ingest-jobs/{job_id}", headers=headers).json()
    assert (job["status"], job["request"]) == ("queued", body)
    assert set(job["counts"].values()) == {0}

    asyncio.run(_worker_progress(database_url, UUID(job_id)))
    pages = []
    cursor = None
    for _ in range(3):
        params = {"limit": 1} | ({"cursor": cursor} if cursor else {})
        page = live.get(f"/v1/ingest-jobs/{job_id}", params=params, headers=headers).json()
        assert page["counts"] == {
            "pending": 0,
            "running": 1,
            "succeeded": 2,
            "failed": 2,
            "skipped": 0,
        }
        pages.append(page["failures"]["items"])
        cursor = page["failures"]["next_cursor"]
        if cursor is None:
            break
    assert [[f["accession_number"] for f in items] for items in pages] == [
        ["0000320193-24-000002"],
        ["0000320193-24-000003"],
    ]
    assert pages[0][0]["attempts"] == 7
    assert pages[0][0]["error"] == "UpstreamError: SEC answered 503"
    missing = live.get(f"/v1/ingest-jobs/{uuid4()}", headers=headers)
    assert missing.status_code == 404
