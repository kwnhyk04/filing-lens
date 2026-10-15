"""The answer pipeline on recorded model replies and evidence (scripts/record_llm_fixtures.py).

The real provider adapters run against respx, which replays the recorded response bodies; the
failure paths use the same bodies doctored, or the providers' documented error shapes.
"""

import json
from collections import defaultdict
from collections.abc import AsyncGenerator, Iterator, Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
import respx
from redis.asyncio import Redis

from filinglens_api.answering import Answerer, Models
from filinglens_api.schemas import Answer, AnswerCompleted, AnswerDelta, AnswerRequest
from filinglens_core.errors import AiUnavailableError, OverloadedError
from filinglens_llm.providers import BASE_URLS, Gemini, OpenAICompatible
from filinglens_llm.validate import citation_error
from filinglens_retrieval import Hit, Ranking, Scope
from filinglens_retrieval.facts import Fact

FIXTURES = Path(__file__).parent / "fixtures" / "answers"
GEMINI = "generativelanguage.googleapis.com"
STREAM = "/v1beta/models/gemini-3.5-flash-lite:streamGenerateContent"
NVIDIA_CHAT = "/v1/chat/completions"
KEY = "test-gemini-key"
SSE = {"content-type": "text/event-stream"}
RATE_LIMITED = httpx.Response(
    429, json={"error": {"code": 429, "message": "Quota exceeded", "status": "RESOURCE_EXHAUSTED"}}
)
NO_CREDITS = httpx.Response(402, json={"detail": "Payment required: no credits left"})


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class RecordedEvidence:
    """The evidence a recording read, answered again in the same order."""

    def __init__(self, calls: list[dict[str, Any]]) -> None:
        self._results: defaultdict[str, list[Any]] = defaultdict(list)
        for call in calls:
            self._results[call["method"]].append(call["result"])

    def _next(self, method: str) -> Any:
        return self._results[method].pop(0)

    async def companies(self, tickers: Sequence[str]) -> dict[str, int]:
        return {ticker: int(cik) for ticker, cik in self._next("companies").items()}

    async def names(self, ciks: Sequence[int]) -> dict[int, str]:
        return {int(cik): name for cik, name in self._next("names").items()}

    async def latest_fiscal_year(self, cik: int) -> int | None:
        return self._next("latest_fiscal_year")

    async def fact(
        self, cik: int, concepts: Sequence[str], unit: str, fiscal_year: int | None, period: str
    ) -> Fact | None:
        found = self._next("fact")
        if found is None:
            return None
        dates = ("period_start", "period_end", "filed_on")
        values: dict[str, Any] = {
            k: date.fromisoformat(v) if k in dates and v else v for k, v in found.items()
        }
        values["value"] = Decimal(found["value"])
        return Fact(**values)

    async def search(self, question: str, scope: Scope) -> Ranking:
        found = self._next("search")
        hits = [
            Hit(**hit | {k: date.fromisoformat(hit[k]) for k in ("filed_on", "period_end")})
            for hit in found["hits"]
        ]
        return Ranking(hits, found["degraded"], found["similarity"], found["timings_ms"])


def replay(router: respx.MockRouter, exchanges: list[dict[str, Any]]) -> None:
    """Answer each recorded endpoint with its recorded responses, in order."""
    replies: defaultdict[tuple[str, str], list[httpx.Response]] = defaultdict(list)
    for exchange in exchanges:
        replies[exchange["host"], exchange["path"]].append(
            httpx.Response(
                exchange["status"],
                content=exchange["body"].encode(),
                headers={"content-type": exchange["content_type"]},
            )
        )
    for (host, path), responses in replies.items():
        router.post(host=host, path=path).mock(side_effect=responses)


def reply_text(stream_body: str) -> str:
    """The whole text of a recorded Gemini stream (server-sent events)."""
    parts: list[str] = []
    for line in stream_body.splitlines():
        if line.startswith("data:"):
            chunk = json.loads(line[5:])
            parts += [part.get("text", "") for part in chunk["candidates"][0]["content"]["parts"]]
    return "".join(parts)


def gemini_stream(text: str) -> httpx.Response:
    chunk = {"candidates": [{"content": {"parts": [{"text": text}], "role": "model"}}]}
    return httpx.Response(200, text=f"data: {json.dumps(chunk)}\r\n\r\n", headers=SSE)


def gemini_json(text: str) -> httpx.Response:
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})


def chat_stream(text: str) -> httpx.Response:
    chunk = {"choices": [{"delta": {"content": text}}]}
    usage = {"choices": [], "usage": {"prompt_tokens": 900, "completion_tokens": 60}}
    body = f"data: {json.dumps(chunk)}\n\ndata: {json.dumps(usage)}\n\ndata: [DONE]\n\n"
    return httpx.Response(200, text=body, headers=SSE)


def answerer(recorded: dict[str, Any], http: httpx.AsyncClient, max_inflight: int) -> Answerer:
    groq = OpenAICompatible("groq", BASE_URLS["groq"], "openai/gpt-oss-20b", "k", http)
    nvidia = OpenAICompatible("nvidia", BASE_URLS["nvidia"], "openai/gpt-oss-20b", "k", http)
    models = Models(
        router=groq, primary=Gemini("gemini-3.5-flash-lite", KEY, http), fallback=nvidia
    )
    redis = Redis.from_url("redis://0.0.0.0:1/0")  # down: usage is logged, not counted
    evidence = RecordedEvidence(recorded["evidence"])
    return Answerer(evidence, models, redis, max_inflight=max_inflight)


async def run(name: str) -> tuple[Answer, str, dict[str, Any]]:
    """Answer the fixture's question; returns the answer, the joined deltas and the stats."""
    recorded = fixture(name)
    async with httpx.AsyncClient() as http:
        stats: dict[str, Any] = {}
        deltas: list[str] = []
        answer = None
        request = AnswerRequest(question=recorded["question"])
        async for event in answerer(recorded, http, 2).events(request, stats):
            if isinstance(event, AnswerDelta):
                deltas.append(event.text)
            elif isinstance(event, AnswerCompleted):
                answer = event.answer
    assert answer is not None
    return answer, "".join(deltas), stats


@pytest.fixture
def mocked() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


async def test_a_numeric_question_is_answered_from_the_xbrl_fact(mocked: respx.MockRouter) -> None:
    replay(mocked, fixture("numeric")["exchanges"])
    answer, streamed, stats = await run("numeric")
    fact = next(c for c in fixture("numeric")["evidence"] if c["method"] == "fact")["result"]
    assert stats["routing"]["route"] == "numeric"
    assert not answer.refused and answer.warnings == []
    assert [c.fact_id for c in answer.citations] == [str(fact["id"])]
    assert "416" in answer.answer and answer.answer == streamed


async def test_a_textual_answer_quotes_the_chunks_it_cites(mocked: respx.MockRouter) -> None:
    replay(mocked, fixture("textual")["exchanges"])
    answer, streamed, _ = await run("textual")
    search = next(c for c in fixture("textual")["evidence"] if c["method"] == "search")
    chunks = {hit["chunk_id"]: hit["text"] for hit in search["result"]["hits"]}
    assert not answer.refused and answer.citations and answer.answer == streamed
    assert all(c.chunk_id and citation_error(c, chunks, ()) is None for c in answer.citations)


@pytest.mark.parametrize(
    ("name", "says"), [("out_of_scope", "SEC filings cannot answer"), ("time_trap", "fiscal 2027")]
)
async def test_out_of_scope_and_time_traps_are_refused_without_an_answer_call(
    mocked: respx.MockRouter, name: str, says: str
) -> None:
    replay(mocked, fixture(name)["exchanges"])
    gemini = mocked.post(host=GEMINI)
    answer, streamed, _ = await run(name)
    assert answer.refused and says in answer.answer and streamed == answer.answer
    assert not gemini.called


async def test_a_sentence_with_an_unsupported_number_is_removed_after_one_regeneration(
    mocked: respx.MockRouter,
) -> None:
    recorded = fixture("textual")
    replay(mocked, recorded["exchanges"][:1])  # the router's reply
    text = reply_text(recorded["exchanges"][1]["body"])
    answer_part, sources = text.split("Sources:", 1)
    bad = " Apple paid its suppliers $999.9 billion [C1]."
    doctored = f"{answer_part.rstrip()}{bad}\n\nSources:{sources}"
    mocked.post(host=GEMINI, path=STREAM).mock(return_value=gemini_stream(doctored))
    path = STREAM.replace("streamGenerateContent", "generateContent")
    regenerate = mocked.post(host=GEMINI, path=path).mock(return_value=gemini_json(doctored))
    answer, _, _ = await run("textual")
    assert regenerate.call_count == 1
    assert "999.9" not in answer.answer and answer.citations
    assert answer.warnings == [
        "The draft failed validation, so the answer was written again.",
        "Removed 1 sentence(s) whose citations or amounts did not check out.",
    ]


async def test_a_rate_limited_primary_falls_back_and_the_fallback_is_recorded(
    mocked: respx.MockRouter,
) -> None:
    recorded = fixture("numeric")
    replay(mocked, recorded["exchanges"][:1])
    mocked.post(host=GEMINI, path=STREAM).mock(return_value=RATE_LIMITED)
    nvidia = mocked.post(host="integrate.api.nvidia.com", path=NVIDIA_CHAT)
    nvidia.mock(return_value=chat_stream(reply_text(recorded["exchanges"][1]["body"])))
    answer, _, stats = await run("numeric")
    assert not answer.refused and nvidia.call_count == 1
    assert [entry.split(": ")[1] for entry in stats["fallbacks"]] == [
        "gemini:gemini-3.5-flash-lite"
    ]


async def test_a_fallback_without_credits_fails_the_answer_with_503(
    mocked: respx.MockRouter,
) -> None:
    replay(mocked, fixture("numeric")["exchanges"][:1])
    mocked.post(host=GEMINI, path=STREAM).mock(return_value=RATE_LIMITED)
    nvidia = mocked.post(host="integrate.api.nvidia.com", path=NVIDIA_CHAT)
    nvidia.mock(return_value=NO_CREDITS)
    with pytest.raises(AiUnavailableError, match="no credits left") as raised:
        await run("numeric")
    assert raised.value.http_status == 503 and nvidia.call_count == 1  # 402 is not retried


async def test_a_failed_router_call_routes_with_the_fallback(mocked: respx.MockRouter) -> None:
    recorded = fixture("numeric")
    mocked.post(host="api.groq.com").mock(return_value=httpx.Response(500))
    router_reply = json.loads(recorded["exchanges"][0]["body"])
    nvidia = mocked.post(host="integrate.api.nvidia.com", path=NVIDIA_CHAT)
    nvidia.mock(return_value=httpx.Response(200, json=router_reply))
    replay(mocked, recorded["exchanges"][1:])
    answer, _, stats = await run("numeric")
    assert not answer.refused and stats["fallbacks"][0].startswith("router: groq:")


async def test_gemini_sends_its_key_only_in_the_header(
    mocked: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "a-key-that-must-not-win")
    replay(mocked, fixture("numeric")["exchanges"])
    await run("numeric")
    request = next(call.request for call in mocked.calls if call.request.url.host == GEMINI)
    assert request.headers["x-goog-api-key"] == KEY
    assert "key" not in request.url.params


async def test_answers_past_the_in_flight_cap_are_shed(mocked: respx.MockRouter) -> None:
    recorded = fixture("numeric")
    replay(mocked, recorded["exchanges"])
    async with httpx.AsyncClient() as http:
        pipeline = answerer(recorded, http, max_inflight=1)
        events = cast(
            AsyncGenerator[Any], pipeline.events(AnswerRequest(question=recorded["question"]))
        )
        await anext(events)  # the first delta: this answer is in flight
        with pytest.raises(OverloadedError) as shed:
            pipeline.admit()
        assert shed.value.retry_after_s == 2
        await events.aclose()
        pipeline.admit()  # the slot is free again
