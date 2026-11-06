"""A1 to A3 of the architecture review: an empty reply and a slow model move to the next model, and
a reranker that runs late never lets a passage through unchecked."""

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from datetime import date
from typing import Any, cast

import pytest
from redis.asyncio import Redis

from filinglens_api.about import Collection
from filinglens_api.answering import RERANK_LATE, Answerer, Deadlines, Models
from filinglens_api.schemas import AnswerCompleted, AnswerRequest
from filinglens_core.errors import UpstreamError
from filinglens_llm.providers import Completion
from filinglens_retrieval import Hit, Ranking, Scope
from filinglens_retrieval.facts import Fact

ROUTED = json.dumps(
    {
        "route": "textual",
        "tickers": ["AAPL"],
        "other_companies": [],
        "fiscal_years": [],
        "fiscal_period": None,
        "metric": None,
    }
)
PASSAGE = "Net sales rose 6% to $416.2 billion."
DRAFT = f'Net sales rose 6% [C1].\n\nSources:\n[C1] "{PASSAGE}"'
BROKEN = 'Net sales rose 7% [C1].\n\nSources:\n[C1] "Net sales rose 7%"'
QUESTION = AnswerRequest(question="How did Apple's net sales change?")
FAST = Deadlines(router=0.05, first_token=0.05, reply=0.15)


class Stall:
    """A reply that arrives after `seconds`; `after` is the text sent before the stall."""

    def __init__(self, seconds: float, after: str = "") -> None:
        self.seconds, self.after = seconds, after


class Scripted:
    """A model that takes each call's reply from a list: text, or a Stall."""

    def __init__(self, name: str, *replies: str | Stall) -> None:
        self.name = name
        self.replies = list(replies)
        self.calls = 0

    def _next(self) -> str | Stall:
        self.calls += 1
        return self.replies.pop(0)

    def _done(self, text: str) -> Completion:
        return Completion(self.name, text, 10, 5, 0.01)

    async def complete(self, system: str, user: str, *, max_tokens: int, schema: Any = None) -> Any:
        reply = self._next()
        if isinstance(reply, Stall):
            await asyncio.sleep(reply.seconds)
            return self._done(reply.after)
        return self._done(reply)

    async def stream(
        self, system: str, user: str, *, max_tokens: int
    ) -> AsyncIterator[str | Completion]:
        reply = self._next()
        if isinstance(reply, Stall):
            if reply.after:
                yield reply.after
            await asyncio.sleep(reply.seconds)
            yield self._done(reply.after)
            return
        if reply:
            yield reply
        yield self._done(reply)


class Filings:
    """One company, and a search that may come back without the reranker."""

    def __init__(self, degraded: bool = False) -> None:
        self.degraded = degraded

    async def companies(self, tickers: Sequence[str]) -> dict[str, int]:
        return {"AAPL": 320193}

    async def tracked(self) -> dict[str, str]:
        return {"AAPL": "Apple Inc."}

    async def names(self, ciks: Sequence[int]) -> dict[int, str]:
        return {320193: "Apple Inc. (AAPL)"}

    async def latest_fiscal_year(self, cik: int) -> int | None:
        return 2025

    async def fact(
        self, cik: int, concepts: Sequence[str], unit: str, fiscal_year: int | None, period: str
    ) -> Fact | None:
        return None

    async def search(self, question: str, scope: Scope) -> Ranking:
        day = date(2025, 10, 31)
        score = 0.016 if self.degraded else 5.0  # a fused score, or the reranker's
        hit = Hit("c-1", score, PASSAGE, "7", "a", 320193, "10-K", day, day, 2025, "FY", "d")
        return Ranking([hit], self.degraded, 0.8, {})

    async def collection(self) -> Collection:
        raise AssertionError("no question here asks about the collection")


def answerer(
    primary: Scripted,
    fallback: Scripted,
    router: Scripted | None = None,
    router_fallback: Scripted | None = None,
    degraded: bool = False,
    deadlines: Deadlines = FAST,
) -> Answerer:
    models = Models(
        cast(Any, router or Scripted("r", ROUTED)),
        cast(Any, primary),
        cast(Any, fallback),
        router_fallback=cast(Any, router_fallback),
    )
    redis = Redis.from_url("redis://0.0.0.0:1/0")  # down: usage is logged, not counted
    return Answerer(
        Filings(degraded), models, redis, max_inflight=4, today=date.today, deadlines=deadlines
    )


async def completed(model: Answerer) -> Any:
    last = None
    async for event in model.events(QUESTION):
        last = event
    assert isinstance(last, AnswerCompleted)
    return last.answer


async def test_an_empty_reply_goes_to_the_next_model_not_to_a_refusal() -> None:
    primary, fallback = Scripted("first", ""), Scripted("second", DRAFT)
    answer = await completed(answerer(primary, fallback))
    assert not answer.refused and answer.answer.startswith("Net sales rose 6%")
    assert (primary.calls, fallback.calls) == (1, 1)


async def test_a_reply_of_only_spaces_counts_as_empty() -> None:
    answer = await completed(answerer(Scripted("first", " \n "), Scripted("second", DRAFT)))
    assert not answer.refused


async def test_empty_replies_from_every_model_are_a_failure_and_no_judgment_on_the_question() -> (
    None
):
    with pytest.raises(UpstreamError, match="no text"):
        await completed(answerer(Scripted("first", ""), Scripted("second", "")))


async def test_an_empty_rewrite_goes_to_the_next_model() -> None:
    primary, fallback = Scripted("first", BROKEN, ""), Scripted("second", DRAFT)
    answer = await completed(answerer(primary, fallback))
    assert not answer.refused and answer.answer.startswith("Net sales rose 6%")
    assert (primary.calls, fallback.calls) == (2, 1)


async def test_a_slow_first_token_goes_to_the_next_model() -> None:
    primary, fallback = Scripted("first", Stall(5)), Scripted("second", DRAFT)
    answer = await asyncio.wait_for(completed(answerer(primary, fallback)), 2)
    assert not answer.refused
    assert fallback.calls == 1


async def test_a_stream_that_stops_after_its_first_text_ends_at_its_deadline() -> None:
    primary, fallback = Scripted("first", Stall(5, after="Net sales")), Scripted("second", DRAFT)
    with pytest.raises(UpstreamError, match="took over"):
        await asyncio.wait_for(completed(answerer(primary, fallback)), 2)
    assert fallback.calls == 0  # text already went out, so no second voice joins it


async def test_a_slow_rewrite_goes_to_the_next_model() -> None:
    primary, fallback = Scripted("first", BROKEN, Stall(5)), Scripted("second", DRAFT)
    answer = await asyncio.wait_for(completed(answerer(primary, fallback)), 2)
    assert not answer.refused and fallback.calls == 1


async def test_a_slow_router_goes_to_the_next_model() -> None:
    router, behind = Scripted("r1", Stall(5)), Scripted("r2", ROUTED)
    model = answerer(Scripted("first", DRAFT), Scripted("second"), router, behind)
    answer = await asyncio.wait_for(completed(model), 2)
    assert not answer.refused and behind.calls == 1


async def test_every_model_past_its_deadline_is_a_failure_within_the_deadlines() -> None:
    model = answerer(Scripted("first", Stall(5)), Scripted("second", Stall(5)))
    with pytest.raises(UpstreamError, match=r"took over 0\.05 s"):
        await asyncio.wait_for(completed(model), 2)


async def test_a_late_reranker_fails_closed_with_a_clear_message_and_calls_no_answer_model() -> (
    None
):
    primary, fallback = Scripted("first", DRAFT), Scripted("second", DRAFT)
    answer = await completed(answerer(primary, fallback, degraded=True))
    assert answer.refused and answer.degraded
    assert answer.answer == RERANK_LATE
    assert "try again" in answer.answer.lower()
    assert primary.calls == fallback.calls == 0
