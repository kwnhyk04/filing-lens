"""The Claude provider on a mock transport: credits gone, short 429s, the expiry date, usage and
cost. No request leaves the process."""

import asyncio
import json
from datetime import date, timedelta

import httpx2
import pytest
from structlog.testing import capture_logs

from filinglens_core.errors import AiUnavailableError, RateLimitedError, UpstreamError
from filinglens_llm.providers import Anthropic, Completion, credits_usd

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
        "claude-haiku-5-5", "k", expires=EXPIRES, today=lambda: today, http_client=client
    )
    return model, sent


async def ask(model: Anthropic) -> Completion:
    return await model.complete("system", "question", max_tokens=1024)


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        (error(402, "billing_error", "Your credit balance is too low."), "402 billing_error"),
        (error(400, "invalid_request_error", SPEND_LIMIT), "400 invalid_request_error"),
        (error(429, "rate_limit_error", SPEND_CAP), "429 without Retry-After"),  # the spend cap
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


async def test_a_refusal_fails_the_call_so_the_chain_moves_on() -> None:
    body = json.loads(message("").content) | {"stop_reason": "refusal"}
    model, _ = claude(httpx2.Response(200, json=body))
    with pytest.raises(UpstreamError, match="refusal"):
        await ask(model)
    assert model.off() is None
