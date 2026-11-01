"""Recent questions: what counts as the same question, the store, and the answer stream giving a
sign-in its earlier answer back without a model call. One test runs against a real Redis."""

import asyncio
import json
import time
from typing import Any

import httpx2
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from redis.asyncio import Redis as AsyncRedis

from filinglens_api import limits
from filinglens_api.limits import answer_limits
from filinglens_api.main import app
from filinglens_api.recent import KEEP, RecentAnswers, normalized, question_key
from filinglens_api.schemas import Answer, AnswerRequest, Usage
from filinglens_core.errors import RateLimitedError, TransientError, UpstreamError
from filinglens_telemetry import configure_logging

SESSION = "Zr4cC9cQ0vB5o2kq7nJ1xw"  # the web's 16 random bytes in base64url
OTHER = "Q1w2E3r4T5y6U7i8O9p0aA"
QUESTION = "What was Apple's revenue in fiscal 2025?"
ANSWER = Answer(
    answer="Revenue was $416.2 billion [1].",
    citations=[],
    degraded=False,
    usage=Usage(input_tokens=1200, output_tokens=60, cost_usd=0.0),
)
STREAM = "POST /v1/answers/stream"  # the request's span


def ask(question: str = QUESTION, **scope: Any) -> AnswerRequest:
    return AnswerRequest(question=question, **scope)


def _stream(
    url: str,
    api_key: str,
    question: str = QUESTION,
    session: str | None = SESSION,
    fresh: bool = False,
) -> list[dict[str, Any]]:
    """The events of one streamed answer."""
    headers = {"X-API-Key": api_key} | ({"X-Session-ID": session} if session else {})
    response = httpx2.post(
        f"{url}/v1/answers/stream",
        json={"question": question},
        params={"fresh": "true"} if fresh else None,
        headers=headers,
        timeout=10,
    )
    assert response.status_code == 200, response.text
    return [json.loads(line[5:]) for line in response.text.splitlines() if line.startswith("data:")]


def _recent(url: str, api_key: str, session: str = SESSION, **params: Any) -> dict[str, Any]:
    headers = {"X-API-Key": api_key, "X-Session-ID": session}
    response = httpx2.get(f"{url}/v1/answers/recent", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _ended(spans: InMemorySpanExporter, count: int) -> list[Any]:
    """The stream requests' spans, once `count` of them ended (uvicorn ends them on its thread)."""
    deadline = time.monotonic() + 5
    while len(ended := [s for s in spans.get_finished_spans() if s.name == STREAM]) < count:
        assert time.monotonic() < deadline, "the request spans never ended"
        time.sleep(0.01)
    return ended


SAME = [
    "What was Apple’s revenue in fiscal 2025?",  # noqa: RUF001 - a curly apostrophe
    "what was apple's revenue in fiscal 2025",
    "  What  was Apple's\nrevenue in fiscal 2025 ?!",
    "WHAT WAS APPLE'S REVENUE IN FISCAL 2025.",
    "What was Apple's revenue in fiscal ２０２５?",  # noqa: RUF001 - full-width digits
]


def test_the_same_question_ignores_case_spacing_curly_quotes_and_closing_punctuation() -> None:
    assert {question_key(ask(text)) for text in SAME} == {question_key(ask())}
    assert normalized(SAME[2]) == "what was apple's revenue in fiscal 2025"
    # Companies and years in any order or repeated, and none given as [] or as null.
    many = ask(company_ids=[320193, 789019], fiscal_years=[2025, 2024])
    shuffled = ask(company_ids=[789019, 320193, 320193], fiscal_years=[2024, 2025])
    assert question_key(many) == question_key(shuffled)
    assert question_key(ask(company_ids=[], fiscal_years=[])) == question_key(ask())


DIFFERENT: list[tuple[str, AnswerRequest, AnswerRequest]] = [
    ("another year", ask(), ask("What was Apple's revenue in fiscal 2024?")),
    ("another figure", ask(), ask("What was Apple's net income in fiscal 2025?")),
    ("another tense", ask(), ask("What is Apple's revenue in fiscal 2025?")),
    ("a ticker for the name", ask(), ask("What was AAPL's revenue in fiscal 2025?")),
    (
        "another number format",
        ask("Was Apple's revenue over $400 billion in fiscal 2025?"),
        ask("Was Apple's revenue over $400,000,000,000 in fiscal 2025?"),
    ),
    ("one company", ask(), ask(company_ids=[320193])),
    ("another year in scope", ask(fiscal_years=[2025]), ask(fiscal_years=[2024])),
]


@pytest.mark.parametrize(
    ("one", "other"), [row[1:] for row in DIFFERENT], ids=[row[0] for row in DIFFERENT]
)
def test_other_words_or_another_company_or_year_make_another_question(
    one: AnswerRequest, other: AnswerRequest
) -> None:
    assert question_key(one) != question_key(other)


async def test_a_session_keeps_its_ten_newest_answers_newest_first(
    recent: RecentAnswers, fake_redis: Any
) -> None:
    for n in range(KEEP + 2):
        await recent.put(SESSION, ask(f"Question number {n}?"), ANSWER)
    first = await recent.page(SESSION, 4, None)
    second = await recent.page(SESSION, 4, first.next_cursor)
    third = await recent.page(SESSION, 4, second.next_cursor)
    shown = [item.question for page in (first, second, third) for item in page.items]
    assert shown == [f"Question number {n}?" for n in range(11, 1, -1)]  # the two oldest went
    assert third.next_cursor is None
    assert set(fake_redis.ttls.values()) == {1800}
    stored = await recent.get(SESSION, ask("question NUMBER 11"))
    assert stored is not None
    assert (stored.question, stored.answer) == ("Question number 11?", ANSWER)
    assert await recent.get(SESSION, ask("Question number 0?")) is None
    assert await recent.get(OTHER, ask("Question number 11?")) is None


async def test_an_unreadable_stored_answer_is_a_miss(
    recent: RecentAnswers, fake_redis: Any
) -> None:
    await recent.put(SESSION, ask(), ANSWER)
    await recent.put(SESSION, ask("Another question?"), ANSWER)
    [fields] = fake_redis.hashes.values()
    fields[question_key(ask()).encode()] = b'{"question": "stored before a schema change"}'
    assert await recent.get(SESSION, ask()) is None
    page = await recent.page(SESSION, 10, None)
    assert [item.question for item in page.items] == ["Another question?"]


async def test_redis_down_is_a_miss_and_a_skipped_write_logged_by_error_type_only(
    recent: RecentAnswers, fake_redis: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("api")
    fake_redis.fail = True
    assert await recent.get(SESSION, ask()) is None
    await recent.put(SESSION, ask(), ANSWER)  # skipped, not raised
    with pytest.raises(TransientError) as listed:
        await recent.page(SESSION, 10, None)
    with pytest.raises(TransientError) as cleared:
        await recent.clear(SESSION)
    assert (listed.value.retry_after_s, cleared.value.retry_after_s) == (5, 5)
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    warned = [(line["op"], line["error"]) for line in lines if line["event"].startswith("recent")]
    assert warned == [("get", "RedisError"), ("put", "RedisError")]
    assert "Apple" not in json.dumps(lines)  # the replies quoted the question


def test_a_session_gets_its_stored_answer_back_without_another_answer(
    server_url: str, api_key: str, fake: Any
) -> None:
    *deltas, first = _stream(server_url, api_key)
    assert deltas
    assert first["stored_at"] is None
    again = _stream(server_url, api_key, "  what was apple’s revenue in FISCAL 2025 ")  # noqa: RUF001
    assert [event["type"] for event in again] == ["completed"]  # no draft: nothing is written
    assert again[0]["answer"] == first["answer"]
    assert again[0]["stored_at"] == "2026-11-01T14:02:00Z"
    assert fake.answered == 1


def test_fresh_asks_again_and_replaces_the_stored_answer(
    server_url: str, api_key: str, fake: Any
) -> None:
    _stream(server_url, api_key)
    fake.given = fake.given.model_copy(update={"answer": "A newer answer [1]."})
    *_, fresh = _stream(server_url, api_key, fresh=True)
    assert (fresh["answer"]["answer"], fresh["stored_at"]) == ("A newer answer [1].", None)
    [replayed] = _stream(server_url, api_key)
    assert replayed["answer"]["answer"] == "A newer answer [1]."
    assert fake.answered == 2


@pytest.mark.parametrize("kind", ["refused", "degraded", "failed"])
def test_refusals_degraded_answers_and_failed_streams_are_never_stored(
    server_url: str, api_key: str, fake: Any, fake_redis: Any, kind: str
) -> None:
    if kind == "failed":
        fake.fail_mid_stream = UpstreamError("The model provider timed out.")
    else:
        fake.given = fake.given.model_copy(update={kind: True})
    for _ in range(2):
        _stream(server_url, api_key)
    assert fake.answered == 2
    assert fake_redis.hashes == {}


def test_without_a_session_nothing_is_stored_or_replayed(
    server_url: str, api_key: str, fake: Any, fake_redis: Any
) -> None:
    for _ in range(2):
        *_, last = _stream(server_url, api_key, session=None)
        assert (last["type"], last["stored_at"]) == ("completed", None)
    assert fake.answered == 2
    assert fake_redis.hashes == {}


def test_one_session_never_sees_another_sessions_answers(
    server_url: str, api_key: str, fake: Any, fake_redis: Any
) -> None:
    _stream(server_url, api_key, session=SESSION)
    *_, theirs = _stream(server_url, api_key, session=OTHER)
    assert theirs["stored_at"] is None  # answered again, not given the first sign-in's answer
    assert fake.answered == 2
    assert _recent(server_url, api_key, "N" * 22) == {"items": [], "next_cursor": None}
    assert len(fake_redis.hashes) == 2
    assert not any(SESSION in key or OTHER in key for key in fake_redis.hashes)  # hashed ids only


def test_a_replayed_answer_still_takes_the_answer_limits(
    server_url: str, api_key: str, fake: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stream(server_url, api_key)

    async def limited() -> None:
        raise RateLimitedError("Rate limit of 10 requests a minute reached.", retry_after_s=6)

    monkeypatch.setitem(app.dependency_overrides, answer_limits, limited)
    headers = {"X-API-Key": api_key, "X-Session-ID": SESSION}
    url = f"{server_url}/v1/answers/stream"
    response = httpx2.post(url, json={"question": QUESTION}, headers=headers, timeout=10)
    assert (response.status_code, response.json()["code"]) == (429, "rate_limited")
    assert fake.answered == 1


def test_a_slow_store_never_turns_a_finished_answer_into_a_failure(
    server_url: str, api_key: str, recent: RecentAnswers, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(limits, "ANSWER_TIMEOUT_S", 0.2)
    put = recent.put

    async def slow_put(*args: Any) -> None:
        await asyncio.sleep(0.5)  # past the answer's deadline
        await put(*args)

    monkeypatch.setattr(recent, "put", slow_put)
    *_, last = _stream(server_url, api_key)
    assert last["type"] == "completed"
    [replayed] = _stream(server_url, api_key)
    assert replayed["stored_at"] is not None


def test_a_replayed_answer_marks_the_request_span_as_stored(
    server_url: str, api_key: str, spans: InMemorySpanExporter
) -> None:
    _stream(server_url, api_key)
    _stream(server_url, api_key)
    marks = [(s.attributes or {}).get("filinglens.answer.stored") for s in _ended(spans, 2)]
    assert marks == [None, True]


def test_recent_answers_page_newest_first_by_cursor(
    server_url: str, api_key: str, fake: Any
) -> None:
    questions = [f"What was revenue in fiscal {year}?" for year in (2023, 2024, 2025)]
    for question in questions:
        _stream(server_url, api_key, question)
    first = _recent(server_url, api_key, limit=2)
    assert [item["question"] for item in first["items"]] == [questions[2], questions[1]]
    second = _recent(server_url, api_key, limit=2, cursor=first["next_cursor"])
    assert [item["question"] for item in second["items"]] == [questions[0]]
    assert second["next_cursor"] is None
    newest = first["items"][0]
    assert set(newest) == {"id", "question", "answered_at", "answer"}
    assert newest["answer"] == fake.given.model_dump(mode="json")
    headers = {"X-API-Key": api_key, "X-Session-ID": SESSION}
    bad = httpx2.get(f"{server_url}/v1/answers/recent?cursor=not-one", headers=headers)
    assert (bad.status_code, bad.json()["code"]) == (400, "invalid_input")


def test_clearing_a_session_empties_its_list(server_url: str, api_key: str, fake: Any) -> None:
    _stream(server_url, api_key, session=SESSION)
    _stream(server_url, api_key, session=OTHER)
    headers = {"X-API-Key": api_key, "X-Session-ID": SESSION}
    cleared = httpx2.delete(f"{server_url}/v1/answers/recent", headers=headers)
    assert (cleared.status_code, cleared.content) == (204, b"")
    assert _recent(server_url, api_key)["items"] == []
    assert len(_recent(server_url, api_key, OTHER)["items"]) == 1
    *_, again = _stream(server_url, api_key)
    assert again["stored_at"] is None
    assert fake.answered == 3


@pytest.mark.parametrize("method", ["GET", "DELETE"])
@pytest.mark.parametrize("session", [None, "too-short", "twenty-two characters!"])
def test_the_recent_routes_need_a_well_formed_session_id(
    server_url: str, api_key: str, method: str, session: str | None
) -> None:
    headers = {"X-API-Key": api_key} | ({"X-Session-ID": session} if session else {})
    response = httpx2.request(method, f"{server_url}/v1/answers/recent", headers=headers)
    assert response.status_code == 422
    assert [error["pointer"] for error in response.json()["errors"]] == ["/header/X-Session-ID"]


def test_a_malformed_session_id_is_refused_before_any_answer(
    server_url: str, api_key: str, fake: Any
) -> None:
    headers = {"X-API-Key": api_key, "X-Session-ID": "too-short"}
    url = f"{server_url}/v1/answers/stream"
    response = httpx2.post(url, json={"question": QUESTION}, headers=headers, timeout=10)
    assert response.status_code == 422
    assert fake.answered == 0


def test_recent_answers_leave_no_question_answer_or_session_id_in_logs_or_spans(
    server_url: str,
    api_key: str,
    fake: Any,
    fake_redis: Any,
    spans: InMemorySpanExporter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("api")
    _stream(server_url, api_key)
    _stream(server_url, api_key)  # from earlier
    _recent(server_url, api_key)
    headers = {"X-API-Key": api_key, "X-Session-ID": SESSION}
    httpx2.delete(f"{server_url}/v1/answers/recent", headers=headers)
    fake_redis.fail = True  # every reply quotes its command, the question included
    _stream(server_url, api_key)
    _ended(spans, 3)
    out = capsys.readouterr().out
    exported = "".join(span.to_json() for span in spans.get_finished_spans())
    for private in (SESSION, "Apple", fake.given.answer):
        assert private not in out
        assert private not in exported
    lines = [json.loads(line) for line in out.splitlines()]
    warned = [line["op"] for line in lines if line["event"] == "recent answers unavailable"]
    assert warned == ["get", "put"]


@pytest.mark.integration
async def test_redis_stores_each_answer_with_its_own_ttl_and_drops_the_hash_on_clear(
    redis_url: str,
) -> None:
    redis = AsyncRedis.from_url(redis_url)
    try:
        recent = RecentAnswers(redis, 120)
        for n in range(KEEP + 1):
            await recent.put(SESSION, ask(f"Question number {n}?"), ANSWER)
        key = RecentAnswers.key(SESSION)
        assert await redis.keys(f"*{SESSION}*") == []  # the raw id names no key
        fields = await redis.hkeys(key)
        assert len(fields) == KEEP
        assert question_key(ask("Question number 0?")).encode() not in fields
        assert all(0 < ttl <= 120 for ttl in await redis.httl(key, *fields))
        assert await redis.ttl(key) == -1  # the fields expire, not the hash
        stored = await recent.get(SESSION, ask("question number 10"))
        assert stored is not None and stored.answer == ANSWER
        await recent.clear(SESSION)
        assert await redis.exists(key) == 0
        await RecentAnswers(redis, 1).put(OTHER, ask(), ANSWER)
        deadline = time.monotonic() + 5
        while await redis.exists(RecentAnswers.key(OTHER)):  # Redis drops it with its last field
            assert time.monotonic() < deadline, "the hash outlived its last field"
            await asyncio.sleep(0.1)
    finally:
        await redis.aclose()
