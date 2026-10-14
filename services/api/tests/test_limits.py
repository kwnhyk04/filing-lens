"""Rate limits and the AI budget against a real Redis; body size and answer time without it."""

import asyncio
import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from filinglens_api import routes
from filinglens_api.backend import get_backend
from filinglens_api.limits import ANSWERS_PER_MINUTE, MAX_BODY_BYTES, PER_MINUTE
from filinglens_api.main import app
from filinglens_llm import budget

QUESTION = {"question": "What was revenue?"}


@contextmanager
def _limited(fake: Any, redis_url: str) -> Iterator[TestClient]:
    """The app over the in-memory backend with the real limits, on an empty Redis."""
    Redis.from_url(redis_url).flushdb()
    app.dependency_overrides[get_backend] = lambda: fake
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def limited(env: pytest.MonkeyPatch, fake: Any, redis_url: str) -> Iterator[TestClient]:
    env.setenv("REDIS_URL", redis_url)
    with _limited(fake, redis_url) as client:
        yield client


def _allowed_until_429(send: Any) -> tuple[int, float, Any]:
    """Send until the first 429; returns how many got through, the time taken and the 429."""
    started = time.monotonic()
    for allowed in range(200):
        response = send()
        if response.status_code == 429:
            return allowed, time.monotonic() - started, response
        assert response.status_code == 200
    raise AssertionError("no 429 after 200 requests")


async def _spend(url: str, tokens: int) -> None:
    redis = AsyncRedis.from_url(url)
    try:
        await budget.record(redis, tokens)
    finally:
        await redis.aclose()


@pytest.mark.integration
def test_every_route_takes_60_a_minute_per_key_then_429_with_rate_limit_headers(
    limited: TestClient, api_key: str, admin_key: str
) -> None:
    headers = {"X-API-Key": api_key}
    allowed, seconds, refused = _allowed_until_429(
        lambda: limited.get("/v1/companies", headers=headers)
    )
    # A bucket of 60 that refills one token a second.
    assert PER_MINUTE <= allowed <= PER_MINUTE + int(seconds) + 1
    assert refused.json()["code"] == "rate_limited"
    assert refused.headers["RateLimit-Limit"] == "60"
    assert refused.headers["RateLimit-Remaining"] == "0"
    assert refused.headers["Retry-After"] == "1"
    graphql = limited.post("/graphql", json={"query": "{ __typename }"}, headers=headers)
    assert graphql.status_code == 429  # GraphQL draws on the same bucket
    assert limited.get("/v1/companies", headers={"X-API-Key": admin_key}).status_code == 200


@pytest.mark.integration
def test_answers_take_10_a_minute_per_key_across_both_routes(
    limited: TestClient, api_key: str, admin_key: str
) -> None:
    headers = {"X-API-Key": api_key}
    paths = iter(["/v1/answers", "/v1/answers/stream"] * 100)
    allowed, seconds, refused = _allowed_until_429(
        lambda: limited.post(next(paths), json=QUESTION, headers=headers)
    )
    assert ANSWERS_PER_MINUTE <= allowed <= ANSWERS_PER_MINUTE + int(seconds / 6) + 1
    assert refused.headers["RateLimit-Limit"] == "10"
    assert 1 <= int(refused.headers["Retry-After"]) <= 6  # one token every 6 s
    assert limited.get("/v1/companies", headers=headers).status_code == 200  # other routes go on
    other = limited.post("/v1/answers", json=QUESTION, headers={"X-API-Key": admin_key})
    assert other.status_code == 200  # each key has its own bucket


@pytest.mark.integration
def test_answers_get_503_once_the_daily_ai_token_budget_is_spent(
    limited: TestClient, redis_url: str, api_key: str
) -> None:
    headers = {"X-API-Key": api_key}
    asyncio.run(_spend(redis_url, 999_999))
    assert limited.post("/v1/answers", json=QUESTION, headers=headers).status_code == 200
    asyncio.run(_spend(redis_url, 1))  # reaches the default budget of 1,000,000 tokens
    for path in ("/v1/answers", "/v1/answers/stream"):
        response = limited.post(path, json=QUESTION, headers=headers)
        assert response.status_code == 503
        problem = response.json()
        assert problem["code"] == "ai_unavailable"
        assert "budget of 1,000,000 tokens is used up" in problem["detail"]
        assert 0 < int(response.headers["Retry-After"]) <= 86_400  # until 00:00 UTC
    assert limited.get("/v1/companies", headers=headers).status_code == 200  # only answers stop
    usage = Redis.from_url(redis_url).hgetall(budget.usage_key(datetime.now(UTC).date()))
    assert usage == {b"calls": b"2", b"tokens": b"1000000"}


@pytest.mark.integration
def test_ai_enabled_false_turns_answers_off(
    env: pytest.MonkeyPatch, fake: Any, redis_url: str, api_key: str
) -> None:
    env.setenv("REDIS_URL", redis_url)
    env.setenv("AI_ENABLED", "false")
    with _limited(fake, redis_url) as client:
        response = client.post("/v1/answers", json=QUESTION, headers={"X-API-Key": api_key})
    assert response.status_code == 503
    assert response.json()["code"] == "ai_unavailable"
    assert "AI_ENABLED=false" in response.json()["detail"]


def test_bodies_over_64_kb_get_413_with_or_without_a_length(client: TestClient) -> None:
    sized = client.post("/v1/answers", json={"question": "x" * MAX_BODY_BYTES})
    chunks = iter([b'{"question": "', b"x" * MAX_BODY_BYTES, b'"}'])  # no Content-Length
    streamed = client.post("/v1/answers", content=chunks)
    for response in (sized, streamed):
        assert response.status_code == 413
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["code"] == "request_entity_too_large"
        assert "X-Request-ID" in response.headers


def test_answers_stop_at_the_time_limit(
    server_url: str, fake: Any, api_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes, "ANSWER_TIMEOUT_S", 0.2)
    fake.delay_s = 2
    headers = {"X-API-Key": api_key}
    response = httpx2.post(f"{server_url}/v1/answers", json=QUESTION, headers=headers, timeout=10)
    assert response.status_code == 502
    assert response.json()["code"] == "upstream_error"
    stream = httpx2.post(
        f"{server_url}/v1/answers/stream", json=QUESTION, headers=headers, timeout=10
    )
    events = [json.loads(line[5:]) for line in stream.text.splitlines() if line.startswith("data:")]
    assert [event["type"] for event in events] == ["failed"]
    assert events[0]["problem"]["code"] == "upstream_error"
