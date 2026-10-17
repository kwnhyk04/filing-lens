"""Rate limits and the AI budget against a real Redis; body size, answer time and the in-flight
cap without it. GraphQL answers take the same limits as REST."""

import asyncio
import json
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from typing import Any, cast

import httpx2
import pytest
from fastapi.testclient import TestClient
from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from filinglens_api import limits
from filinglens_api.answering import Answerer, Evidence, Models
from filinglens_api.backend import AnswerEvents, get_backend
from filinglens_api.limits import ANSWERS_PER_MINUTE, MAX_BODY_BYTES, PER_MINUTE
from filinglens_api.main import app
from filinglens_api.schemas import AnswerRequest
from filinglens_core.errors import UpstreamError
from filinglens_llm import budget

QUESTION = {"question": "What was revenue?"}
type Changes = Callable[[str], dict[str, float]]
ANSWER_QUERY = {
    "query": "query Ask($q: String!) { answer(question: $q) { answer } }",
    "variables": {"q": QUESTION["question"]},
}


def _graphql_error(response: Any) -> tuple[str, str] | None:
    """The first error's code and message of a GraphQL answer, or None when it answered."""
    assert response.status_code == 200
    errors = response.json().get("errors")
    return (errors[0]["extensions"]["code"], errors[0]["message"]) if errors else None


def _answered_until_refused(send: Any) -> tuple[int, float, tuple[str, str]]:
    """Ask GraphQL until the first error; returns the answers, the time taken and the error."""
    started = time.monotonic()
    for answered in range(200):
        if (refused := _graphql_error(send())) is not None:
            return answered, time.monotonic() - started, refused
    raise AssertionError("no refusal after 200 answers")


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
    # AI is off by default, and on it needs a key per role; the fake backend calls no model.
    for name in ("GEMINI_API_KEY", "GROQ_API_KEY", "NVIDIA_API_KEY"):
        env.setenv(name, "placeholder")
    env.setenv("AI_ENABLED", "true")
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
def test_graphql_answers_take_the_same_10_a_minute_from_the_same_bucket(
    limited: TestClient, fake: Any, api_key: str, metric_changes: Changes
) -> None:
    headers = {"X-API-Key": api_key}
    answered, seconds, refused = _answered_until_refused(
        lambda: limited.post("/graphql", json=ANSWER_QUERY, headers=headers)
    )
    assert refused[0] == "rate_limited"
    assert ANSWERS_PER_MINUTE <= answered <= ANSWERS_PER_MINUTE + int(seconds / 6) + 1
    assert fake.answered == answered  # the refused answer never reached the backend
    rest = limited.post("/v1/answers", json=QUESTION, headers=headers)
    assert rest.status_code == 429  # REST draws on the bucket GraphQL emptied
    assert metric_changes("filinglens.answers.rejected") == {"reason=rate_limited": 2}


@pytest.mark.integration
def test_answers_get_503_once_the_daily_ai_token_budget_is_spent(
    limited: TestClient, fake: Any, redis_url: str, api_key: str, metric_changes: Changes
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
    graphql = _graphql_error(limited.post("/graphql", json=ANSWER_QUERY, headers=headers))
    assert graphql is not None
    assert graphql[0] == "ai_unavailable"
    assert "budget of 1,000,000 tokens is used up" in graphql[1]
    assert fake.answered == 1  # only the answer before the budget ran out
    assert limited.get("/v1/companies", headers=headers).status_code == 200  # only answers stop
    usage = Redis.from_url(redis_url).hgetall(budget.usage_key(datetime.now(UTC).date()))
    assert usage == {b"calls": b"2", b"tokens": b"1000000"}
    assert metric_changes("filinglens.answers.rejected") == {"reason=budget_exhausted": 3}
    assert budget.tokens_today(Redis.from_url(redis_url)) == 1_000_000  # the dashboard's gauge


@pytest.mark.integration
def test_ai_enabled_false_turns_answers_off(
    env: pytest.MonkeyPatch, fake: Any, redis_url: str, api_key: str, metric_changes: Changes
) -> None:
    env.setenv("REDIS_URL", redis_url)
    env.setenv("AI_ENABLED", "false")
    headers = {"X-API-Key": api_key}
    with _limited(fake, redis_url) as client:
        response = client.post("/v1/answers", json=QUESTION, headers=headers)
        graphql = _graphql_error(client.post("/graphql", json=ANSWER_QUERY, headers=headers))
    assert response.status_code == 503
    assert response.json()["code"] == "ai_unavailable"
    assert "AI_ENABLED=false" in response.json()["detail"]
    assert graphql is not None
    assert graphql[0] == "ai_unavailable"
    assert "AI_ENABLED=false" in graphql[1]
    assert fake.answered == 0
    assert metric_changes("filinglens.answers.rejected") == {"reason=ai_disabled": 2}


def test_bodies_over_64_kb_get_413_with_or_without_a_length(client: TestClient) -> None:
    sized = client.post("/v1/answers", json={"question": "x" * MAX_BODY_BYTES})
    chunks = iter([b'{"question": "', b"x" * MAX_BODY_BYTES, b'"}'])  # no Content-Length
    streamed = client.post("/v1/answers", content=chunks)
    for response in (sized, streamed):
        assert response.status_code == 413
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["code"] == "request_entity_too_large"
        assert "X-Request-ID" in response.headers


def test_graphql_answers_fail_closed_while_redis_is_down(
    env: pytest.MonkeyPatch, fake: Any, api_key: str, metric_changes: Changes
) -> None:
    for name in ("GEMINI_API_KEY", "GROQ_API_KEY", "NVIDIA_API_KEY"):
        env.setenv(name, "placeholder")
    env.setenv("AI_ENABLED", "true")  # Redis stays at the dead address `env` sets
    app.dependency_overrides[get_backend] = lambda: fake
    try:
        with TestClient(app) as client:
            response = client.post("/graphql", json=ANSWER_QUERY, headers={"X-API-Key": api_key})
    finally:
        app.dependency_overrides.clear()
    graphql = _graphql_error(response)
    assert graphql is not None
    assert graphql[0] == "ai_unavailable"
    assert "budget cannot be checked" in graphql[1]
    assert fake.answered == 0
    assert metric_changes("filinglens.answers.rejected") == {"reason=budget_unavailable": 1}
    assert budget.tokens_today(Redis.from_url("redis://0.0.0.0:1/0")) is None  # no gauge reading


def test_answers_stop_at_the_time_limit(
    server_url: str, fake: Any, api_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(limits, "ANSWER_TIMEOUT_S", 0.2)
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
    graphql = httpx2.post(f"{server_url}/graphql", json=ANSWER_QUERY, headers=headers, timeout=10)
    assert _graphql_error(graphql) == ("upstream_error", "No answer within 0.2 s.")


class _Held:
    """Evidence that holds every answer at its first read, before any event, until released."""

    def __init__(self) -> None:
        self.released = threading.Event()

    async def tracked(self) -> dict[str, str]:
        await asyncio.to_thread(self.released.wait)  # set from the test's thread
        raise UpstreamError("A held answer ends here.")


def test_one_stream_past_the_in_flight_cap_is_refused(
    server_url: str, fake: Any, api_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = _Held()
    redis = AsyncRedis.from_url("redis://0.0.0.0:1/0")  # never reached: answers stop at tracked()
    pipeline = Answerer(cast(Evidence, held), cast(Models, None), redis, max_inflight=2)

    async def admit(request: AnswerRequest) -> AnswerEvents:
        return pipeline.admit(request)

    monkeypatch.setattr(fake, "stream_answer", admit)  # the real admission behind the real route
    url, headers = f"{server_url}/v1/answers/stream", {"X-API-Key": api_key}
    with httpx2.Client(timeout=10) as client, ExitStack() as streams:

        def open_stream() -> httpx2.Response:
            return streams.enter_context(client.stream("POST", url, json=QUESTION, headers=headers))

        try:
            first, second = open_stream(), open_stream()  # admitted, held before any event
            assert (first.status_code, second.status_code) == (200, 200)
            refused = client.post(url, json=QUESTION, headers=headers)
            assert refused.status_code == 503
            assert refused.json()["code"] == "overloaded"
            first.close()  # its client leaves before the first event
            deadline = time.monotonic() + 5
            while (again := open_stream()).status_code != 200:  # the freed slot admits a stream
                assert again.status_code == 503
                assert time.monotonic() < deadline, "the closed stream kept its slot"
                time.sleep(0.05)
        finally:
            held.released.set()
