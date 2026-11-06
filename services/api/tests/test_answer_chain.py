"""A1 to A3 of the architecture review: an empty reply and a slow model move to the next model, and
a reranker that runs late never lets a passage through unchecked. Then a question on how a figure
changed, and what an answer may say when only a fact was read (the demo capture, 2026-11-07)."""

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from datetime import date
from decimal import Decimal
from typing import Any, cast

import pytest
from redis.asyncio import Redis

from filinglens_api.about import Collection
from filinglens_api.answering import (
    FIGURE_SHORT,
    NO_EVIDENCE,
    RERANK_LATE,
    Answerer,
    Deadlines,
    Models,
)
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
        self.seen: list[str] = []  # each call's prompt

    def _next(self, user: str) -> str | Stall:
        self.calls += 1
        self.seen.append(user)
        return self.replies.pop(0)

    def _done(self, text: str) -> Completion:
        return Completion(self.name, text, 10, 5, 0.01)

    async def complete(self, system: str, user: str, *, max_tokens: int, schema: Any = None) -> Any:
        reply = self._next(user)
        if isinstance(reply, Stall):
            await asyncio.sleep(reply.seconds)
            return self._done(reply.after)
        return self._done(reply)

    async def stream(
        self, system: str, user: str, *, max_tokens: int
    ) -> AsyncIterator[str | Completion]:
        reply = self._next(user)
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


LAST_YEAR = "What was Apple's revenue last year, and how did it change?"
FROM_2024 = "What was Apple's revenue last year, and how did it change from 2024?"
AND_MORE = "What was Apple's total revenue in fiscal 2025, and who runs it?"
SEGMENT = "What was Apple's iPhone revenue in fiscal 2025?"
CHANGED = (
    "Apple's revenue rose from $391.0 billion in fiscal 2024 to $416.2 billion in fiscal 2025,"
    ' up 6.43% [F1][F2][K1].\n\nSources:\n[F1] "391,035,000,000 USD"\n'
    '[F2] "416,161,000,000 USD"\n[K1] "6.43%"'
)
FIGURE = "Apple's total revenue was $416.2 billion in fiscal 2025 [F1]."
FIGURE_DRAFT = f'{FIGURE}\n\nSources:\n[F1] "416,161,000,000 USD"'
SILENT_DRAFT = (
    f'{FIGURE} The sources do not state who runs it [F1].\n\nSources:\n[F1] "416,161,000,000 USD"'
)
INSUFFICIENT = "INSUFFICIENT_EVIDENCE"


def routed(route: str = "numeric", years: Sequence[int] = (2025,)) -> str:
    """The router's reply for Apple's revenue, on `route` over `years`."""
    return json.dumps(
        {
            "route": route,
            "tickers": ["AAPL"],
            "other_companies": [],
            "fiscal_years": list(years),
            "fiscal_period": "FY",
            "metric": "revenue",
        }
    )


class Figures(Filings):
    """Apple's revenue for two fiscal years, and filings that may hold nothing relevant."""

    def __init__(self, degraded: bool = False, relevant: bool = True) -> None:
        super().__init__(degraded)
        self.relevant = relevant
        self.read: list[int | None] = []  # the fiscal year of each fact asked for
        self.scopes: list[Scope] = []  # each search's scope

    async def fact(
        self, cik: int, concepts: Sequence[str], unit: str, fiscal_year: int | None, period: str
    ) -> Fact | None:
        self.read.append(fiscal_year)
        year = fiscal_year or 0
        value = {2024: 391_035_000_000, 2025: 416_161_000_000}.get(year)
        if value is None:
            return None
        return Fact(
            len(self.read), cik, "us-gaap:Revenues", "Revenues", Decimal(value), "USD",
            date(year - 1, 9, 28), date(year, 9, 27), 2025, "FY", "10-K", "0000320193-25-000079",
            date(2025, 10, 31),
        )  # fmt: skip

    async def search(self, question: str, scope: Scope) -> Ranking:
        self.scopes.append(scope)
        found = await super().search(question, scope)
        return found if self.relevant else Ranking([], False, 0.8, {})


async def asked(
    evidence: Figures, primary: Scripted, reply: str, question: str, **request: Any
) -> tuple[Any, dict[str, Any]]:
    """The completed answer to `question` when the router replies `reply`, and the stats."""
    models = Models(
        cast(Any, Scripted("r", reply)), cast(Any, primary), cast(Any, Scripted("second"))
    )
    redis = Redis.from_url("redis://0.0.0.0:1/0")  # down: usage is logged, not counted
    model = Answerer(evidence, models, redis, max_inflight=4, today=date.today, deadlines=FAST)
    stats: dict[str, Any] = {}
    last = None
    async for event in model.events(AnswerRequest(question=question, **request), stats):
        last = event
    assert isinstance(last, AnswerCompleted)
    return last.answer, stats


@pytest.mark.parametrize(
    ("question", "reply"),
    [
        (LAST_YEAR, routed()),  # the demo capture
        (FROM_2024, routed()),
        (FROM_2024, routed(years=[2024, 2025])),
        (FROM_2024, routed("comparison")),
        ("How did Apple's revenue change?", routed(years=[])),
    ],
)
async def test_a_question_on_how_a_figure_changed_reads_both_years_and_the_filing_text(
    question: str, reply: str
) -> None:
    evidence, primary = Figures(), Scripted("first", CHANGED)
    answer, stats = await asked(evidence, primary, reply, question)
    assert not answer.refused and answer.warnings == [] and "6.43%" in answer.answer
    assert evidence.read == [2024, 2025] and evidence.scopes[-1] == Scope([320193], [2024, 2025])
    prompt = primary.seen[0]
    assert "[K1] Calculated by FilingLens from F1 and F2" in prompt and "[C1]" in prompt
    assert (answer.reading.route, answer.reading.fiscal_years) == ("comparison", [2024, 2025])
    assert stats["routing"]["route"] == json.loads(reply)["route"]  # the evals score its own reply


async def test_a_change_the_calculation_states_stays_with_no_rewrite() -> None:
    draft = (
        "Apple's revenue was $391.0 billion in fiscal 2024 [F1]. It was $416.2 billion in fiscal"
        " 2025 [F2]. Fiscal 2025 revenue was higher by $25.13 billion, or 6.43% more than fiscal"
        ' 2024 [F1][F2][K1].\n\nSources:\n[F1] "391,035,000,000 USD"\n'
        '[F2] "416,161,000,000 USD"\n[K1] "6.43%"'
    )
    primary = Scripted("first", draft)
    answer, _ = await asked(Figures(), primary, routed(years=[2024, 2025]), FROM_2024)
    assert primary.calls == 1 and not answer.refused
    assert answer.answer.endswith("or 6.43% more than fiscal 2024 [3].")
    assert answer.citations[2].calculation.inputs == [1, 2]
    assert answer.warnings == [
        "Removed 2 fact citation(s) whose figures their sentence left to its calculation."
    ]


async def test_a_request_that_names_its_years_keeps_them() -> None:
    evidence = Figures()
    primary = Scripted("first", DRAFT)
    answer, _ = await asked(evidence, primary, routed(), LAST_YEAR, fiscal_years=[2025])
    assert evidence.read == [2025] and answer.reading.route == "comparison"


async def test_two_companies_keep_the_years_they_were_read_for() -> None:
    evidence = Figures()
    primary = Scripted("first", DRAFT)
    await asked(evidence, primary, routed(), LAST_YEAR, company_ids=[320193, 789019])
    assert evidence.read == [2025, 2025]


async def test_a_time_trap_names_the_year_asked_not_the_year_before_it() -> None:
    primary = Scripted("first")
    question = "How did Apple's revenue change in fiscal 2031?"
    answer, _ = await asked(Figures(), primary, routed(years=[2031]), question)
    assert answer.refused and "fiscal 2031" in answer.answer and primary.calls == 0


async def test_a_fact_that_answers_searches_nothing() -> None:
    primary = Scripted("first", FIGURE_DRAFT)
    answer, stats = await asked(Figures(), primary, routed(), SEGMENT)
    assert answer.answer == "Apple's total revenue was $416.2 billion in fiscal 2025 [1]."
    assert stats["early_search"] is None and set(stats["sources"]) == {"F1"}
    assert primary.calls == 1 and answer.warnings == []


async def test_a_draft_saying_what_the_sources_leave_out_reads_the_filing_text_first() -> None:
    primary = Scripted("first", SILENT_DRAFT, DRAFT)
    answer, stats = await asked(Figures(), primary, routed(), AND_MORE)
    assert answer.answer == "Net sales rose 6% [1]." and answer.warnings == [FIGURE_SHORT]
    assert answer.citations[0].chunk_id == "c-1" and stats["sources"]["C1"] == "c-1"
    assert "[C1]" not in primary.seen[0] and "[C1]" in primary.seen[1]
    assert "it says what the sources do not state" in primary.seen[1]


@pytest.mark.parametrize("reply", [routed(), routed("comparison")])
async def test_with_no_passage_to_read_a_draft_says_only_what_the_fact_shows(reply: str) -> None:
    primary = Scripted("first", SILENT_DRAFT, SILENT_DRAFT)
    answer, stats = await asked(Figures(relevant=False), primary, reply, AND_MORE)
    assert answer.answer == "Apple's total revenue was $416.2 billion in fiscal 2025 [1]."
    assert set(stats["sources"]) == {"F1"} and "do not state" not in answer.answer
    assert "it says what the sources do not state" in primary.seen[1]


async def test_a_fact_that_cannot_answer_reads_the_filing_text_before_any_refusal() -> None:
    primary = Scripted("first", INSUFFICIENT, DRAFT)
    answer, _ = await asked(Figures(), primary, routed(), SEGMENT)
    assert not answer.refused and answer.answer == "Net sales rose 6% [1]."
    assert answer.warnings == [FIGURE_SHORT] and "broke the rules" not in primary.seen[1]


@pytest.mark.parametrize(
    ("filings", "says", "degraded"),
    [({"relevant": False}, NO_EVIDENCE, False), ({"degraded": True}, RERANK_LATE, True)],
)
async def test_after_a_fact_a_refusal_says_what_the_search_found(
    filings: dict[str, bool], says: str, degraded: bool
) -> None:
    primary = Scripted("first", INSUFFICIENT)
    answer, stats = await asked(Figures(**filings), primary, routed(), SEGMENT)
    assert answer.refused and answer.answer == says and answer.degraded is degraded
    assert stats["early_search"] is not None and primary.calls == 1  # it searched, and no rewrite
