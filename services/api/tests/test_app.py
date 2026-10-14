import asyncio
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from filing_lens_api_client import AuthenticatedClient
from filing_lens_api_client.api.catalog import list_companies
from filing_lens_api_client.models import CompanyPage
from filing_lens_api_client.types import UNSET, Unset
from seed_fake import CIK_BASE, seed_fake
from sqlalchemy import column, func, select, table, text
from sqlalchemy.ext.asyncio import create_async_engine

from filinglens_api.backend import (
    SEC_ARCHIVES,
    CompanyKey,
    ItemKey,
    LiveBackend,
    SearchKey,
    decode_cursor,
    encode_cursor,
)
from filinglens_api.main import app
from filinglens_api.schemas import FormType, Page
from filinglens_core.errors import InvalidInputError
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
        (
            "POST",
            "/v1/ingest-jobs",
            {"ciks": [320193], "form_types": ["10-K"], "since": "2024-01-01"},
        ),
        ("GET", f"/v1/ingest-jobs/{uuid4()}", None),
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
        backend = LiveBackend(engine)

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
    [("0003", "embedding"), ("head", "embedding_v2")],  # dev stays at 0003 until the live swap
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
