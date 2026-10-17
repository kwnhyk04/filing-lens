"""The answer pipeline on recorded model replies and evidence (scripts/record_llm_fixtures.py).

The real provider adapters run against respx, which replays the recorded response bodies; the
failure paths use the same bodies doctored, or the providers' documented error shapes.
"""

import asyncio
import json
from collections import defaultdict
from collections.abc import Callable, Iterator, Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import httpx
import httpx2
import pytest
import respx
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from redis.asyncio import Redis

from filinglens_api import limits
from filinglens_api.answering import Answerer, Evidence, Models
from filinglens_api.schemas import Answer, AnswerCompleted, AnswerDelta, AnswerRequest
from filinglens_core.errors import AiUnavailableError, OverloadedError, UpstreamError
from filinglens_llm.providers import (
    BASE_URLS,
    Anthropic,
    Gemini,
    OpenAICompatible,
    Provider,
    credits_usd,
)
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
RETIRED = httpx.Response(410, json={"detail": "The model has reached its end of life"})
TRACKED = {"AAPL": "Apple Inc.", "NVDA": "NVIDIA Corporation"}
GROQ = "api.groq.com"
TRACER = trace.get_tracer("tests")
SERVER = "POST /v1/answers"  # the request's span, which FastAPI starts in the app
type Changes = Callable[[str], dict[str, float]]


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class RecordedEvidence:
    """The evidence a recording read, answered again in the same order."""

    def __init__(self, calls: list[dict[str, Any]]) -> None:
        self._results: defaultdict[str, list[Any]] = defaultdict(list)
        self.scopes: list[Scope] = []  # each search's scope, in order
        for call in calls:
            self._results[call["method"]].append(call["result"])

    def _next(self, method: str) -> Any:
        """The next recorded result; the last one answers again, since the search that starts
        with the router asks for companies and chunks before the plan does."""
        results = self._results[method]
        return results.pop(0) if len(results) > 1 else results[0]

    async def companies(self, tickers: Sequence[str]) -> dict[str, int]:
        return {ticker: int(cik) for ticker, cik in self._next("companies").items()}

    async def tracked(self) -> dict[str, str]:
        """The recorded list, or for fixtures recorded before the router saw one, its tickers."""
        return self._next("tracked") if self._results["tracked"] else TRACKED

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
        self.scopes.append(scope)
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


def claude_stream(text: str) -> httpx2.Response:
    """A Claude Messages stream holding `text`, 900 tokens in and 60 out."""
    start = {"type": "message", "role": "assistant", "content": [], "usage": {"input_tokens": 900}}
    events = [
        ("message_start", {"message": start | {"model": "claude-haiku-5-5"}}),
        ("content_block_start", {"index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": text}}),
        ("content_block_stop", {"index": 0}),
        ("message_delta", {"delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 60}}),
        ("message_stop", {}),
    ]
    body = "".join(f"event: {n}\ndata: {json.dumps(d | {'type': n})}\n\n" for n, d in events)
    return httpx2.Response(200, text=body, headers=SSE)


def claude(
    *replies: httpx2.Response, today: date = date(2026, 10, 17)
) -> tuple[Anthropic, list[httpx2.Request]]:
    """Claude (LLM_ANSWER_FALLBACK) answering each request with the next reply, and its requests."""
    sent: list[httpx2.Request] = []
    queue = list(replies)

    def handle(request: httpx2.Request) -> httpx2.Response:
        sent.append(request)
        return queue.pop(0)

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handle))
    expires = date(2026, 11, 10)
    model = Anthropic(
        "claude-haiku-5-5", "k", expires=expires, today=lambda: today, http_client=client
    )
    return model, sent


def answerer(
    recorded: dict[str, Any],
    http: httpx.AsyncClient,
    max_inflight: int,
    evidence: RecordedEvidence | None = None,
    answer_fallback: Provider | None = None,
    **options: Any,
) -> Answerer:
    groq = OpenAICompatible("groq", BASE_URLS["groq"], "openai/gpt-oss-20b", "k", http)
    nvidia = OpenAICompatible("nvidia", BASE_URLS["nvidia"], "openai/gpt-oss-20b", "k", http)
    gemini = Gemini("gemini-3.5-flash-lite", KEY, http)
    models = Models(groq, gemini, nvidia, answer_fallback)
    redis = Redis.from_url("redis://0.0.0.0:1/0")  # down: usage is logged, not counted
    evidence = evidence or RecordedEvidence(recorded["evidence"])
    return Answerer(evidence, models, redis, max_inflight=max_inflight, **options)


async def run(
    name: str,
    evidence: RecordedEvidence | None = None,
    answer_fallback: Provider | None = None,
    **options: Any,
) -> tuple[Answer, str, dict[str, Any]]:
    """Answer the fixture's question; returns the answer, the joined deltas and the stats."""
    recorded = fixture(name)
    async with httpx.AsyncClient() as http:
        stats: dict[str, Any] = {}
        deltas: list[str] = []
        answer = None
        request = AnswerRequest(question=recorded["question"])
        pipeline = answerer(recorded, http, 2, evidence, answer_fallback, **options)
        async for event in pipeline.events(request, stats):
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
    answer, streamed, stats = await run("textual")
    search = next(c for c in fixture("textual")["evidence"] if c["method"] == "search")
    hits = search["result"]["hits"]
    chunks = {hit["chunk_id"]: hit["text"] for hit in hits}
    assert not answer.refused and answer.citations and answer.answer == streamed
    assert all(c.chunk_id and citation_error(c, chunks, ()) is None for c in answer.citations)
    assert stats["top_score"] == hits[0]["score"]  # the evals read the sources the model got
    assert stats["sources"] == {f"C{n}": hit["chunk_id"] for n, hit in enumerate(hits[:12], 1)}


async def test_the_search_started_with_the_router_is_kept_when_the_router_agrees(
    mocked: respx.MockRouter,
) -> None:
    replay(mocked, fixture("textual")["exchanges"])
    evidence = RecordedEvidence(fixture("textual")["evidence"])
    answer, _, stats = await run("textual", evidence)  # "Apple ... its latest annual report"
    assert not answer.refused and stats["early_search"] is True
    assert evidence.scopes == [Scope([320193], None)]  # one search, the early one


async def test_a_router_that_disagrees_gets_its_own_search(mocked: respx.MockRouter) -> None:
    recorded = fixture("textual")
    content = json.loads(
        json.loads(recorded["exchanges"][0]["body"])["choices"][0]["message"]["content"]
    )
    mocked.post(host=GROQ).mock(return_value=router_reply(**content | {"fiscal_years": [2024]}))
    replay(mocked, recorded["exchanges"][1:])
    evidence = RecordedEvidence(recorded["evidence"])
    answer, _, stats = await run("textual", evidence)
    assert not answer.refused and stats["early_search"] is False
    assert evidence.scopes == [Scope([320193], None), Scope([320193], [2024])]


async def test_a_best_hit_under_min_relevance_is_refused_without_an_answer_call(
    mocked: respx.MockRouter,
) -> None:
    replay(mocked, fixture("textual")["exchanges"][:1])  # the router's reply
    gemini = mocked.post(host=GEMINI)
    answer, _, stats = await run("textual", min_relevance=0.0)  # the best hit scored -0.76
    assert answer.refused and "nothing relevant enough" in answer.answer
    assert not gemini.called and stats["sources"] == {} and stats["top_score"] < 0


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


@pytest.mark.parametrize(
    ("reply", "says"), [(NO_CREDITS, "no credits left"), (RETIRED, "retired this model")]
)
async def test_a_fallback_without_credits_or_retired_fails_the_answer_with_503(
    mocked: respx.MockRouter, reply: httpx.Response, says: str
) -> None:
    replay(mocked, fixture("numeric")["exchanges"][:1])
    mocked.post(host=GEMINI, path=STREAM).mock(return_value=RATE_LIMITED)
    nvidia = mocked.post(host="integrate.api.nvidia.com", path=NVIDIA_CHAT)
    nvidia.mock(return_value=reply)
    with pytest.raises(AiUnavailableError, match=says) as raised:
        await run("numeric")
    assert raised.value.http_status == 503 and nvidia.call_count == 1  # 402/410: no retry


async def test_claude_answers_when_gemini_fails_and_its_credits_are_counted(
    mocked: respx.MockRouter,
) -> None:
    recorded = fixture("numeric")
    replay(mocked, recorded["exchanges"][:1])  # the router's reply
    mocked.post(host=GEMINI, path=STREAM).mock(return_value=RATE_LIMITED)
    nvidia = mocked.post(host="integrate.api.nvidia.com", path=NVIDIA_CHAT)
    model, sent = claude(claude_stream(reply_text(recorded["exchanges"][1]["body"])))
    answer, _, stats = await run("numeric", answer_fallback=model)
    assert not answer.refused and len(sent) == 1 and not nvidia.called  # Claude before NVIDIA
    assert [entry.split(": ")[1] for entry in stats["fallbacks"]] == [
        "gemini:gemini-3.5-flash-lite"
    ]
    assert answer.usage.cost_usd == pytest.approx(credits_usd(model.name, 900, 60))


async def test_claude_without_credits_hands_over_to_nvidia_and_is_skipped_after(
    mocked: respx.MockRouter,
) -> None:
    recorded = fixture("numeric")
    replay(mocked, recorded["exchanges"][:1] * 2)  # the router's reply, for two answers
    mocked.post(host=GEMINI, path=STREAM).mock(return_value=RATE_LIMITED)
    text = reply_text(recorded["exchanges"][1]["body"])
    nvidia = mocked.post(host="integrate.api.nvidia.com", path=NVIDIA_CHAT)
    nvidia.mock(side_effect=[chat_stream(text), chat_stream(text)])
    body = {"type": "error", "error": {"type": "billing_error", "message": "No credit left."}}
    model, sent = claude(httpx2.Response(402, json=body))
    first, _, stats = await run("numeric", answer_fallback=model)
    assert not first.refused and first.usage.cost_usd == 0.0
    assert [entry.split(": ")[1] for entry in stats["fallbacks"]] == [
        "gemini:gemini-3.5-flash-lite",
        "anthropic:claude-haiku-5-5",
    ]
    second, _, stats = await run("numeric", answer_fallback=model)
    assert not second.refused and len(stats["fallbacks"]) == 1  # Gemini to NVIDIA directly
    assert len(sent) == 1 and nvidia.call_count == 2


async def test_claude_is_skipped_from_the_day_its_credits_expire(mocked: respx.MockRouter) -> None:
    recorded = fixture("numeric")
    replay(mocked, recorded["exchanges"][:1])
    mocked.post(host=GEMINI, path=STREAM).mock(return_value=RATE_LIMITED)
    nvidia = mocked.post(host="integrate.api.nvidia.com", path=NVIDIA_CHAT)
    nvidia.mock(return_value=chat_stream(reply_text(recorded["exchanges"][1]["body"])))
    model, sent = claude(today=date(2026, 11, 10))
    answer, _, _ = await run("numeric", answer_fallback=model)
    assert not answer.refused and not sent and nvidia.call_count == 1


async def test_an_eval_pinned_to_claude_stops_once_its_credits_are_gone(
    mocked: respx.MockRouter,
) -> None:
    recorded = fixture("numeric")
    replay(mocked, recorded["exchanges"][:1])
    body = {"type": "error", "error": {"type": "billing_error", "message": "No credit left."}}
    model, _ = claude(httpx2.Response(402, json=body))
    async with httpx.AsyncClient() as http:
        groq = OpenAICompatible("groq", BASE_URLS["groq"], "openai/gpt-oss-20b", "k", http)
        evidence = RecordedEvidence(recorded["evidence"])
        redis = Redis.from_url("redis://0.0.0.0:1/0")
        models = Models(router=groq, primary=model, fallback=model)  # as evals pin one model
        pipeline = Answerer(evidence, models, redis, max_inflight=1, allow_fallback=False)
        with pytest.raises(AiUnavailableError, match="off for the credit period"):
            async for _ in pipeline.events(AnswerRequest(question=recorded["question"])):
                pass  # evals exit 4 on this error (evals.harness)


async def test_a_failed_router_call_routes_with_the_fallback(mocked: respx.MockRouter) -> None:
    recorded = fixture("numeric")
    mocked.post(host="api.groq.com").mock(return_value=httpx.Response(500))
    router_reply = json.loads(recorded["exchanges"][0]["body"])
    nvidia = mocked.post(host="integrate.api.nvidia.com", path=NVIDIA_CHAT)
    nvidia.mock(return_value=httpx.Response(200, json=router_reply))
    replay(mocked, recorded["exchanges"][1:])
    answer, _, stats = await run("numeric")
    assert not answer.refused and stats["fallbacks"][0].startswith("router: groq:")


def router_reply(**routing: Any) -> httpx.Response:
    """A Groq chat completion holding the numeric fixture's routing, changed by `routing`."""
    body = json.loads(fixture("numeric")["exchanges"][0]["body"])
    content = json.loads(body["choices"][0]["message"]["content"]) | routing
    body["choices"][0]["message"]["content"] = json.dumps(content)
    return httpx.Response(200, json=body)


async def test_an_untracked_ticker_gets_one_retry_with_the_reason(mocked: respx.MockRouter) -> None:
    recorded = fixture("numeric")
    groq = mocked.post(host=GROQ)
    groq.mock(side_effect=[router_reply(tickers=["APPL"]), router_reply()])
    replay(mocked, recorded["exchanges"][1:])
    answer, _, stats = await run("numeric")
    assert groq.call_count == 2 and not answer.refused
    assert stats["routing"]["tickers"] == ["AAPL"]
    request = json.loads(groq.calls[1].request.content)
    assert "APPL are not on the list" in request["messages"][1]["content"]
    tickers = request["response_format"]["json_schema"]["schema"]["properties"]["tickers"]
    assert tickers["items"]["enum"] == sorted(TRACKED)


async def test_a_ticker_still_untracked_after_the_retry_is_refused(
    mocked: respx.MockRouter,
) -> None:
    groq = mocked.post(host=GROQ).mock(return_value=router_reply(tickers=["APPL"]))
    gemini = mocked.post(host=GEMINI)
    answer, _, _ = await run("numeric")
    assert groq.call_count == 2 and not gemini.called
    assert answer.refused and answer.answer == "FilingLens has no filings for APPL."


async def test_a_company_named_as_untracked_is_refused_without_a_retry(
    mocked: respx.MockRouter,
) -> None:
    groq = mocked.post(host=GROQ).mock(
        return_value=router_reply(tickers=[], other_companies=["Netflix"])
    )
    answer, _, _ = await run("numeric")
    assert groq.call_count == 1
    assert answer.refused and answer.answer == "FilingLens has no filings for Netflix."


async def test_a_textual_question_may_mention_an_untracked_company(
    mocked: respx.MockRouter,
) -> None:
    recorded = fixture("textual")
    content = json.loads(
        json.loads(recorded["exchanges"][0]["body"])["choices"][0]["message"]["content"]
    )
    mocked.post(host=GROQ).mock(return_value=router_reply(**content, other_companies=["Foxconn"]))
    replay(mocked, recorded["exchanges"][1:])
    answer, _, _ = await run("textual")
    assert not answer.refused  # Apple's filing answers; Foxconn is only mentioned


async def test_a_comparison_without_its_metric_gets_one_retry(mocked: respx.MockRouter) -> None:
    groq = mocked.post(host=GROQ)
    groq.mock(side_effect=[router_reply(route="comparison", metric=None), router_reply()])
    replay(mocked, fixture("numeric")["exchanges"][1:])
    answer, _, stats = await run("numeric")
    assert groq.call_count == 2 and not answer.refused
    assert "a comparison needs its metric" in groq.calls[1].request.content.decode()
    assert stats["routing"]["metric"] == "revenue"


async def test_gemini_sends_its_key_only_in_the_header(
    mocked: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "a-key-that-must-not-win")
    replay(mocked, fixture("numeric")["exchanges"])
    await run("numeric")
    request = next(call.request for call in mocked.calls if call.request.url.host == GEMINI)
    assert request.headers["x-goog-api-key"] == KEY
    assert "key" not in request.url.params


async def test_an_answer_is_in_flight_from_admission_until_it_ends(
    mocked: respx.MockRouter, metric_changes: Changes
) -> None:
    recorded = fixture("numeric")
    replay(mocked, recorded["exchanges"])
    request = AnswerRequest(question=recorded["question"])
    async with httpx.AsyncClient() as http:
        pipeline = answerer(recorded, http, max_inflight=1)
        unread = pipeline.admit(request)  # in flight before its first event
        assert metric_changes("filinglens.answers.inflight") == {"": 1}
        with pytest.raises(OverloadedError) as shed:
            pipeline.admit(request)
        assert shed.value.retry_after_s == 2
        assert metric_changes("filinglens.answers.rejected") == {"reason=overloaded": 1}
        await unread.aclose()  # closed before its first event: the slot comes back
        events = [event async for event in pipeline.admit(request)]  # an answer run to its end
        assert isinstance(events[-1], AnswerCompleted)
        await pipeline.admit(request).aclose()  # it gave its slot back too
    assert metric_changes("filinglens.answers.inflight") == {}  # every slot came back


async def test_an_answer_records_its_outcome_stages_and_model_calls(
    mocked: respx.MockRouter, spans: InMemorySpanExporter, metric_changes: Changes
) -> None:
    replay(mocked, fixture("numeric")["exchanges"])
    with TRACER.start_as_current_span(SERVER):
        await run("numeric")
    assert metric_changes("filinglens.answers") == {"outcome=answered,reason=none": 1}
    assert metric_changes("filinglens.answer.stage.duration") == {
        f"route=numeric,stage={stage}": 1 for stage in ("route", "facts", "generate", "total")
    }
    assert metric_changes("filinglens.answer.ttft") == {"route=numeric": 1}
    assert metric_changes("filinglens.llm.calls") == {
        "model=openai/gpt-oss-20b,outcome=ok,provider=groq": 1,
        "model=gemini-3.5-flash-lite,outcome=ok,provider=gemini": 1,
    }
    finished = {span.name: span for span in spans.get_finished_spans()}
    server = finished[SERVER]
    assert server.context is not None
    for name in ("route", "facts", "generate", "chat openai/gpt-oss-20b"):
        parent = finished[name].parent
        assert parent is not None and parent.span_id == server.context.span_id
    gemini = finished["chat gemini-3.5-flash-lite"]
    assert [event.name for event in gemini.events] == ["first_token"]
    attributes = server.attributes or {}
    assert attributes["filinglens.answer.outcome"] == "answered"
    assert attributes["filinglens.answer.route"] == "numeric"
    assert cast(int, attributes["gen_ai.usage.input_tokens"]) > 0
    exported = "".join(span.to_json() for span in finished.values())
    assert fixture("numeric")["question"] not in exported  # no question, prompt or quote
    assert KEY not in exported


def _gemini_writes(mocked: respx.MockRouter, text: str) -> None:
    """The textual fixture's routing, then Gemini writing `text` over that answer's sources."""
    recorded = fixture("textual")
    replay(mocked, recorded["exchanges"][:1])
    sources = reply_text(recorded["exchanges"][1]["body"]).split("Sources:", 1)[1]
    reply = f"{text}\n\nSources:{sources}"
    mocked.post(host=GEMINI, path=STREAM).mock(return_value=gemini_stream(reply))
    path = STREAM.replace("streamGenerateContent", "generateContent")
    mocked.post(host=GEMINI, path=path).mock(return_value=gemini_json(reply))


@pytest.mark.parametrize(
    ("code", "name", "options"),
    [
        ("out_of_scope", "out_of_scope", {}),
        ("time_trap", "time_trap", {}),
        ("untracked_company", "numeric", {}),
        ("no_relevant_passages", "textual", {"min_relevance": 0.0}),
        ("insufficient_evidence", "textual", {}),
        ("validation_failed", "textual", {}),
    ],
)
async def test_each_refusal_is_counted_under_its_code(
    mocked: respx.MockRouter,
    spans: InMemorySpanExporter,
    metric_changes: Changes,
    code: str,
    name: str,
    options: dict[str, Any],
) -> None:
    if code == "untracked_company":
        reply = router_reply(tickers=[], other_companies=["Netflix"])
        mocked.post(host=GROQ).mock(return_value=reply)
    elif code == "insufficient_evidence":
        _gemini_writes(mocked, "INSUFFICIENT_EVIDENCE")
    elif code == "validation_failed":  # the regenerated answer fails too, so nothing is left
        _gemini_writes(mocked, "Apple paid its suppliers $999.9 billion [C1].")
    else:
        replay(mocked, fixture(name)["exchanges"])
    with TRACER.start_as_current_span(SERVER):
        answer, _, _ = await run(name, **options)
    assert answer.refused
    assert metric_changes("filinglens.answers") == {f"outcome=refused,reason={code}": 1}
    [server] = [span for span in spans.get_finished_spans() if span.name == SERVER]
    assert (server.attributes or {})["filinglens.answer.reason"] == code


class _Failing:
    """Evidence that fails, or stalls, at the answer's first read."""

    def __init__(self, error: Exception | None) -> None:
        self.error = error

    async def tracked(self) -> dict[str, str]:
        if self.error is None:
            await asyncio.sleep(10)
        raise self.error or AssertionError("unreachable")


@pytest.mark.parametrize(
    ("error", "reason"),
    [(UpstreamError("SEC is down."), "upstream_error"), (RuntimeError("bug"), "internal")],
)
async def test_a_failed_answer_is_counted_under_its_error_code(
    metric_changes: Changes, error: Exception, reason: str
) -> None:
    redis = Redis.from_url("redis://0.0.0.0:1/0")
    pipeline = Answerer(cast(Evidence, _Failing(error)), cast(Models, None), redis, max_inflight=1)
    with pytest.raises(type(error)):
        async for _ in pipeline.events(AnswerRequest(question="What was revenue?")):
            pass
    assert metric_changes("filinglens.answers") == {f"outcome=failed,reason={reason}": 1}


async def test_a_provider_without_credits_fails_the_answer_as_ai_unavailable(
    mocked: respx.MockRouter, spans: InMemorySpanExporter, metric_changes: Changes
) -> None:
    replay(mocked, fixture("numeric")["exchanges"][:1])
    mocked.post(host=GEMINI, path=STREAM).mock(return_value=RATE_LIMITED)
    mocked.post(host="integrate.api.nvidia.com", path=NVIDIA_CHAT).mock(return_value=NO_CREDITS)
    with TRACER.start_as_current_span(SERVER), pytest.raises(AiUnavailableError):
        await run("numeric")
    assert metric_changes("filinglens.answers") == {"outcome=failed,reason=ai_unavailable": 1}
    [server] = [span for span in spans.get_finished_spans() if span.name == SERVER]
    assert [(event.name, dict(event.attributes or {})) for event in server.events] == [
        (
            "fallback",
            {
                "role": "primary",
                "from": "gemini:gemini-3.5-flash-lite",
                "to": "nvidia:openai/gpt-oss-20b",
                "error.type": "rate_limited",
            },
        )
    ]
    assert metric_changes("filinglens.llm.calls") == {
        "model=openai/gpt-oss-20b,outcome=ok,provider=groq": 1,
        "model=gemini-3.5-flash-lite,outcome=error,provider=gemini": 1,
        "model=openai/gpt-oss-20b,outcome=error,provider=nvidia": 1,
    }
    gemini = next(s for s in spans.get_finished_spans() if s.name == "chat gemini-3.5-flash-lite")
    assert (gemini.attributes or {})["error.type"] == "rate_limited"
    assert gemini.status.description is None  # provider messages can echo the prompt


@pytest.mark.parametrize(("limit_s", "outcome"), [(30, "cancelled"), (0.05, "failed")])
async def test_an_answer_cut_off_at_the_time_limit_is_a_timeout_and_earlier_a_cancellation(
    metric_changes: Changes, monkeypatch: pytest.MonkeyPatch, limit_s: float, outcome: str
) -> None:
    monkeypatch.setattr(limits, "ANSWER_TIMEOUT_S", limit_s)
    redis = Redis.from_url("redis://0.0.0.0:1/0")
    pipeline = Answerer(cast(Evidence, _Failing(None)), cast(Models, None), redis, max_inflight=1)
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.05):  # the route's limit, or a client that left
            async for _ in pipeline.events(AnswerRequest(question="What was revenue?")):
                pass
    reason = "timeout" if outcome == "failed" else "none"
    assert metric_changes("filinglens.answers") == {f"outcome={outcome},reason={reason}": 1}
