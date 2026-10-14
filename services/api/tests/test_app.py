import re
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from filing_lens_api_client import AuthenticatedClient
from filing_lens_api_client.api.catalog import list_companies
from filing_lens_api_client.models import CompanyPage
from filing_lens_api_client.types import UNSET, Unset

from filinglens_api.backend import CompanyKey, SearchKey, decode_cursor, encode_cursor
from filinglens_api.main import app
from filinglens_core.errors import InvalidInputError
from filinglens_db.seed import COMPANIES

QUERY = {"query": "{ __typename }"}


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
        ("GET", "/v1/filings", None),
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
    query = {"query": "{ filings { edges { cursor } } }"}
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
