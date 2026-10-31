"""The Claude provider on a mock transport: credits gone, short 429s, the expiry date, usage and
cost. No request leaves the process."""

import asyncio
import json
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any, cast

import httpx2
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode
from structlog.testing import capture_logs

from filinglens_core.errors import AiUnavailableError, RateLimitedError, UpstreamError
from filinglens_llm import router
from filinglens_llm.providers import Anthropic, Completion, claude_schema, credits_usd

EXPIRES = date(2026, 11, 10)
SSE = {"content-type": "text/event-stream"}
SPEND_LIMIT = (
    "You have reached your specified API usage limits. You will regain access on 2026-11-01 at"
    " 00:00 UTC."
)
SPEND_CAP = (
    "You have reached your API usage limits: your organization has crossed its monthly API usage"
    " threshold, set based on your organization's API tier."
)


def message(text: str = "Revenue rose [F1].") -> httpx2.Response:
    body = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": [
            {"type": "thinking", "thinking": "", "signature": "sig"},
            {"type": "text", "text": text},
        ],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 4000, "output_tokens": 300},
    }
    return httpx2.Response(200, json=body)


def streamed(*parts: str) -> httpx2.Response:
    """A Messages stream: a thinking block (its text omitted, as by default), then the parts."""
    start = {
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": [],
        "usage": {"input_tokens": 4000, "output_tokens": 1},
    }
    thinking = {"type": "thinking", "thinking": ""}
    signature = {"type": "signature_delta", "signature": "s"}
    events = [
        ("message_start", {"message": start}),
        ("content_block_start", {"index": 0, "content_block": thinking}),
        ("content_block_delta", {"index": 0, "delta": signature}),
        ("content_block_stop", {"index": 0}),
        ("content_block_start", {"index": 1, "content_block": {"type": "text", "text": ""}}),
        *(
            ("content_block_delta", {"index": 1, "delta": {"type": "text_delta", "text": part}})
            for part in parts
        ),
        ("content_block_stop", {"index": 1}),
        ("message_delta", {"delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 300}}),
        ("message_stop", {}),
    ]
    body = "".join(
        f"event: {name}\ndata: {json.dumps(data | {'type': name})}\n\n" for name, data in events
    )
    return httpx2.Response(200, text=body, headers=SSE)


def error(status: int, kind: str, text: str, **headers: str) -> httpx2.Response:
    body = {"type": "error", "error": {"type": kind, "message": text}, "request_id": "req_1"}
    return httpx2.Response(status, json=body, headers=headers)


def claude(
    *replies: httpx2.Response, today: date = date(2026, 10, 17)
) -> tuple[Anthropic, list[httpx2.Request]]:
    """Claude answering each request with the next reply; the requests it sent, in order."""
    sent: list[httpx2.Request] = []
    queue = list(replies)

    def handle(request: httpx2.Request) -> httpx2.Response:
        sent.append(request)
        return queue.pop(0)

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handle))
    model = Anthropic(
        "claude-haiku-5-5",
        "k",
        expires=EXPIRES,
        ledger=cast(Any, Ledger()),
        today=lambda: today,
        http_client=client,
    )
    return model, sent


class Ledger:
    """budget.ClaudeLedger in memory: no budget used, Claude on."""

    daily_tokens = 1_500_000

    def __init__(self) -> None:
        self.used, self.reason = 0, None

    async def off(self) -> str | None:
        return self.reason

    async def turn_off(self, kind: str, reason: str) -> None:
        self.reason = reason

    async def tokens_today(self) -> int:
        return self.used

    async def record(self, tokens: int) -> None:
        self.used += tokens


async def ask(model: Anthropic) -> Completion:
    return await model.complete("system", "question", max_tokens=1024)


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        (error(402, "billing_error", "Your credit balance is too low."), "402 billing_error"),
        (error(400, "invalid_request_error", SPEND_LIMIT), "400 invalid_request_error"),
    ],
)
async def test_credits_gone_turn_claude_off_for_the_rest_of_the_credit_period(
    reply: httpx2.Response, reason: str
) -> None:
    model, sent = claude(reply)
    with capture_logs() as logs, pytest.raises(AiUnavailableError, match="off for the credit"):
        await ask(model)
    assert (off := model.off()) is not None and off.startswith(reason)
    assert [entry["event"] for entry in logs] == ["claude is off for the rest of the credit period"]
    with pytest.raises(AiUnavailableError):
        await ask(model)
    assert len(sent) == 1  # no request once the credits are gone


async def test_a_429_without_retry_after_is_a_rate_limit_and_keeps_claude_on() -> None:
    model, sent = claude(error(429, "rate_limit_error", SPEND_CAP))  # user rule, 2026-10-21
    with pytest.raises(RateLimitedError) as raised:
        await ask(model)
    assert raised.value.retry_after_s is None and model.off() is None and len(sent) == 1


async def test_any_other_400_fails_the_call_but_keeps_claude_on() -> None:
    model, _ = claude(error(400, "invalid_request_error", "max_tokens: must be at least 1"))
    with pytest.raises(UpstreamError):
        await ask(model)
    assert model.off() is None


async def test_a_429_with_a_short_retry_after_is_retried_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waits: list[float] = []

    async def no_wait(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", no_wait)
    limited = error(429, "rate_limit_error", "Rate limited.", **{"retry-after": "2"})
    model, sent = claude(limited, message())
    assert (await ask(model)).text == "Revenue rose [F1]."  # thinking blocks are left out
    assert waits == [2.0] and len(sent) == 2 and model.off() is None
    again = error(429, "rate_limit_error", "Rate limited.", **{"retry-after": "1"})
    model, sent = claude(again, again)
    with pytest.raises(RateLimitedError):  # transient: the chain moves on, Claude stays on
        await ask(model)
    assert len(sent) == 2 and model.off() is None
    model, sent = claude(error(429, "rate_limit_error", "Slow down.", **{"retry-after": "30"}))
    with pytest.raises(RateLimitedError) as raised:  # too long to wait inside an answer
        await ask(model)
    assert raised.value.retry_after_s == 30 and len(sent) == 1 and model.off() is None


async def test_claude_routes_with_its_reply_held_to_the_routers_schema() -> None:
    routing = '{"route": "numeric", "tickers": ["AAPL"]}'
    model, sent = claude(message(routing))
    schema = {
        "type": "object",
        "properties": {"route": {"type": "string", "enum": ["numeric", "textual"]}},
        "required": ["route"],
        "additionalProperties": False,
    }
    reply = await model.complete("system", "question", max_tokens=400, schema=schema)
    assert reply.text == routing and model.off() is None
    body = json.loads(sent[0].content)
    held = {"type": "json_schema", "schema": schema}
    assert body["output_config"] == {"effort": "low", "format": held}
    assert body["thinking"] == {"type": "disabled"}  # as for answers: one short reply
    model, sent = claude(message("Revenue rose [F1]."))
    await ask(model)  # an answer asks for no format
    assert json.loads(sent[0].content)["output_config"] == {"effort": "low"}


def test_a_nullable_enum_goes_to_claude_as_any_of_an_enum_and_null() -> None:
    # Claude refused the router's form: "Enum value 'FY' does not match declared type
    # '['string', 'null']'" (400, live check 2026-10-31); the free models keep it unchanged.
    sent = claude_schema(router.schema({"AAPL": "Apple"}))["properties"]
    assert sent["fiscal_period"] == {
        "anyOf": [{"type": "string", "enum": ["FY", "Q1", "Q2", "Q3", "Q4"]}, {"type": "null"}]
    }
    assert (
        sent["metric"]["anyOf"][1] == {"type": "null"}
        and None not in sent["metric"]["anyOf"][0]["enum"]
    )
    assert sent["tickers"] == {"type": "array", "items": {"type": "string", "enum": ["AAPL"]}}
    assert router.schema({"AAPL": "Apple"})["properties"]["fiscal_period"]["type"] == [
        "string",
        "null",
    ]


async def test_claude_is_off_from_the_day_its_credits_expire() -> None:
    model, sent = claude(message(), today=EXPIRES - timedelta(days=1))
    assert model.off() is None
    await ask(model)
    model, sent = claude(message(), today=EXPIRES)
    with capture_logs() as logs, pytest.raises(AiUnavailableError, match="expired on 2026-11-10"):
        await ask(model)
    assert not sent and len(logs) == 1


async def test_a_streamed_answer_gives_its_text_usage_and_credit_cost() -> None:
    model, sent = claude(streamed("Revenue ", "rose [F1]."))
    items = [item async for item in model.stream("system", "question", max_tokens=1024)]
    *texts, done = items
    assert texts == ["Revenue ", "rose [F1]."]
    assert isinstance(done, Completion) and done.text == "Revenue rose [F1]."
    assert (done.model, done.input_tokens, done.output_tokens) == (
        "anthropic:claude-haiku-5-5",
        4000,
        300,
    )
    assert done.first_token_s is not None
    body = json.loads(sent[0].content)
    assert body["model"] == "claude-haiku-5-5" and body["output_config"] == {"effort": "low"}
    assert body["thinking"] == {"type": "disabled"} and "temperature" not in body
    assert credits_usd(done.model, 4000, 300) == pytest.approx(0.00055)  # $0.10 / $0.50 per 1M
    assert credits_usd(done.model, 200_000, 1000) == pytest.approx(0.1025)  # past 100K tokens
    assert credits_usd("gemini:gemini-3.5-flash-lite", 4000, 300) == 0.0


async def test_each_call_gets_a_span_and_metrics_but_never_its_text(
    spans: InMemorySpanExporter, metric_changes: Callable[[str], dict[str, float]]
) -> None:
    prompt = "Which risks did the 10-K name?"
    model, _ = claude(message())
    await model.complete("system", prompt, max_tokens=1024)
    model, _ = claude(error(400, "invalid_request_error", f"Bad request: {prompt}"))
    with pytest.raises(UpstreamError):
        await model.complete("system", prompt, max_tokens=1024)
    ok, failed = spans.get_finished_spans()
    assert ok.name == failed.name == "chat claude-haiku-5-5" and ok.kind == SpanKind.CLIENT
    assert dict(ok.attributes or {}) == {
        "gen_ai.provider.name": "anthropic",
        "gen_ai.request.model": "claude-haiku-5-5",
        "gen_ai.operation.name": "chat",
        "gen_ai.usage.input_tokens": 4000,
        "gen_ai.usage.output_tokens": 300,
    }
    assert failed.status.status_code == StatusCode.ERROR and failed.status.description is None
    assert (failed.attributes or {})["error.type"] == "upstream_error"
    model_labels = "model=claude-haiku-5-5"
    assert metric_changes("filinglens.llm.calls") == {
        f"{model_labels},outcome=ok,provider=anthropic": 1,
        f"{model_labels},outcome=error,provider=anthropic": 1,
    }
    labels = "gen_ai.provider.name=anthropic,gen_ai.request.model=claude-haiku-5-5"
    assert metric_changes("gen_ai.client.token.usage") == {
        f"{labels},gen_ai.token.type=input": 1,
        f"{labels},gen_ai.token.type=output": 1,
    }
    assert metric_changes("gen_ai.client.operation.duration") == {
        labels: 1,
        f"error.type=upstream_error,{labels}": 1,
    }
    exported = ok.to_json() + failed.to_json()
    assert prompt not in exported and "Revenue rose" not in exported


async def test_a_streamed_call_marks_its_first_text_once(spans: InMemorySpanExporter) -> None:
    model, _ = claude(streamed("Revenue ", "rose [F1]."))
    _ = [item async for item in model.stream("system", "question", max_tokens=1024)]
    [span] = spans.get_finished_spans()
    assert [event.name for event in span.events] == ["first_token"]
    assert (span.attributes or {})["gen_ai.usage.output_tokens"] == 300


async def test_a_refusal_fails_the_call_so_the_chain_moves_on() -> None:
    body = json.loads(message("").content) | {"stop_reason": "refusal"}
    model, _ = claude(httpx2.Response(200, json=body))
    with pytest.raises(UpstreamError, match="refusal"):
        await ask(model)
    assert model.off() is None
