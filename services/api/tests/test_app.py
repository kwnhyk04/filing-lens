import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from filinglens_api.main import app

API_KEY = "k" * 32
QUERY = {"query": "{ status }"}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    # Nothing listens on port 1, so every dependency check fails.
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@127.0.0.1:1/app")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setenv("BROKER_URL", "amqp://app:app@127.0.0.1:1//")
    monkeypatch.setenv("API_KEY", API_KEY)
    return monkeypatch


@pytest.fixture
def client(env: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


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


@pytest.mark.parametrize(
    ("url", "headers"),
    [
        ("/graphql", {}),
        ("/graphql", {"X-API-Key": "wrong"}),
        (f"/graphql?api_key={API_KEY}", {}),  # only the header counts, never the URL
    ],
)
def test_graphql_rejects_missing_wrong_or_url_api_key(
    client: TestClient, url: str, headers: dict[str, str]
) -> None:
    response = client.post(url, json=QUERY, headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_graphql_answers_with_api_key(client: TestClient) -> None:
    response = client.post("/graphql", json=QUERY, headers={"X-API-Key": API_KEY})
    assert response.json() == {"data": {"status": "ok"}}


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
