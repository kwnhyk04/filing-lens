"""Answers: route the question, gather facts or chunks, write a cited answer, then validate it.

The router (LLM_ROUTER) picks the path and names the companies and periods. Numeric questions read
XBRL facts first (get_financial_fact) and search filing text only when no fact exists; textual and
comparison questions search. That search starts while the router runs, on the companies and years
the question names (router.guess), and is kept only when the router's plan asks for the same
scope, so it changes when an answer arrives, never what it says. The primary model (LLM_PRIMARY)
writes the answer with [n] markers and quotes, and every sentence must pass validation
(filinglens_llm.answer.check); a failure gets one regeneration, then the failing sentences are
dropped with a warning. A router call
that fails falls back to LLM_FALLBACK; an answer call tries LLM_ANSWER_FALLBACK, then LLM_FALLBACK.
Production puts Claude first (LLM_PRIMARY) and Gemini as LLM_ANSWER_FALLBACK; Claude sits out
while it cannot answer (filinglens_llm.providers.Anthropic). Evals turn fallbacks off
(allow_fallback), and each fallback is logged and counted. Out-of-scope questions, unknown
companies, fiscal years with no 10-K yet and questions without relevant evidence get a refusal
instead of a model answer.
"""

import asyncio
import itertools
import time
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol, Self

import structlog
from opentelemetry import trace
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from filinglens_api.schemas import (
    Answer,
    AnswerCompleted,
    AnswerDelta,
    AnswerRequest,
    Citation,
    FigureCheck,
    ReadCompany,
    Reading,
    Usage,
)
from filinglens_core.errors import (
    AiUnavailableError,
    FilingLensError,
    OverloadedError,
    RateLimitedError,
    UpstreamError,
)
from filinglens_core.settings import ApiSettings
from filinglens_db.models import Company, Filing, FilingStatus
from filinglens_llm import answer as drafting
from filinglens_llm import budget, router
from filinglens_llm.providers import Anthropic, Completion, Provider, credits_usd
from filinglens_retrieval import Hit, Ranking, Scope, search
from filinglens_retrieval.facts import Fact, get_financial_fact, latest_fiscal_year
from filinglens_telemetry import metrics

SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
MAX_CHUNKS = 12  # chunks the answer model reads
RELEVANCE_MIN = -3.0  # provisional: TinyBERT gave 0.7 to 9.4 on topic, -10.9 off; 6b calibrates
NO_EVIDENCE = "The filings in FilingLens hold nothing relevant enough to answer this question."
OUT_OF_SCOPE = "SEC filings cannot answer this question, so FilingLens does not answer it."
STAGES = ("route_ms", "facts_ms", "retrieve_ms", "generate_ms", "regenerate_ms", "total_ms")
log = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class Evidence(Protocol):
    """What answers read: companies, facts and chunks. PostgresEvidence serves production."""

    async def companies(self, tickers: Sequence[str]) -> dict[str, int]:
        """CIK by ticker, for the tickers FilingLens tracks."""
        ...

    async def tracked(self) -> dict[str, str]:
        """Name by ticker for each company with an indexed filing: the router's choices."""
        ...

    async def names(self, ciks: Sequence[int]) -> dict[int, str]:
        """Display name, such as 'Apple Inc. (AAPL)', by CIK."""
        ...

    async def latest_fiscal_year(self, cik: int) -> int | None: ...

    async def fact(
        self, cik: int, concepts: Sequence[str], unit: str, fiscal_year: int | None, period: str
    ) -> Fact | None: ...

    async def search(self, question: str, scope: Scope) -> Ranking: ...


@dataclass(frozen=True)
class Models:
    router: Provider
    primary: Provider
    fallback: Provider
    answer_fallback: Provider | None = None  # LLM_ANSWER_FALLBACK: answers only, before `fallback`


@dataclass
class _Run:
    """One answer's bookkeeping: tokens, fallbacks and stage times, logged at the end."""

    started: float = field(default_factory=time.perf_counter)
    lap_at: float = field(default_factory=time.perf_counter)
    lap_ns: int = field(default_factory=time.time_ns)  # wall clock, for the stage spans
    timings_ms: dict[str, float] = field(default_factory=dict)
    refusal: str | None = None  # the refusal code, such as time_trap
    dropped: int = 0  # sentences validation removed
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0  # prepaid credits spent (Claude); the free tiers cost nothing
    fallbacks: list[str] = field(default_factory=list)
    first_token_ms: float | None = None
    top_score: float | None = None  # the best hit's rerank score, when the answer searched
    early_search: bool | None = None  # whether that search was the one started with the router
    sources: dict[str, str] = field(default_factory=dict)  # alias -> chunk id or fact id

    def lap(self, stage: str) -> None:
        now, now_ns = time.perf_counter(), time.time_ns()
        self.timings_ms[stage] = round((now - self.lap_at) * 1000, 1)
        # The finished stage becomes a span under the request's. A span opened at the stage's
        # start would have to stay current across the stream's yields.
        tracer.start_span(stage.removesuffix("_ms"), start_time=self.lap_ns).end(end_time=now_ns)
        self.lap_at, self.lap_ns = now, now_ns

    def since_start_ms(self) -> float:
        return round((time.perf_counter() - self.started) * 1000, 1)


class Admitted:
    """An admitted answer's events. It holds an in-flight slot from admission until its last
    event, an error, a cancellation or aclose(), so a stream whose client left before the first
    event gives its slot back too."""

    def __init__(
        self, events: AsyncGenerator[AnswerDelta | AnswerCompleted, None], leave: Callable[[], None]
    ) -> None:
        self._events = events
        self._leave: Callable[[], None] | None = leave

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> AnswerDelta | AnswerCompleted:
        try:
            return await anext(self._events)
        except BaseException:  # the end of the answer, an error or a cancellation
            self._release()
            raise

    async def aclose(self) -> None:
        self._release()
        await self._events.aclose()

    def _release(self) -> None:
        leave, self._leave = self._leave, None
        if leave is not None:
            leave()


class Answerer:
    def __init__(
        self,
        evidence: Evidence,
        models: Models,
        redis: Redis,
        *,
        max_inflight: int,
        allow_fallback: bool = True,
        today: Callable[[], date] = date.today,
        min_relevance: float = RELEVANCE_MIN,
    ) -> None:
        self._evidence = evidence
        self._models = models
        self._redis = redis
        self._max_inflight = max_inflight
        self._allow_fallback = allow_fallback
        self._today = today
        self._min_relevance = min_relevance
        self._inflight = 0

    def admit(self, request: AnswerRequest) -> Admitted:
        """Shed load before any work: OverloadedError (503) past the in-flight cap. The answer
        counts as in flight from here, not from its first event, so streams opened together
        cannot pass the cap."""
        if self._inflight >= self._max_inflight:
            metrics.REJECTED.add(1, {"reason": "overloaded"})
            raise OverloadedError("Too many answers in progress; retry shortly.", retry_after_s=2)
        self._inflight += 1
        metrics.INFLIGHT.add(1)
        return Admitted(self.events(request), self._leave)

    def _leave(self) -> None:
        self._inflight -= 1
        metrics.INFLIGHT.add(-1)

    async def events(
        self, request: AnswerRequest, stats: dict[str, Any] | None = None
    ) -> AsyncGenerator[AnswerDelta | AnswerCompleted, None]:
        """Deltas of the draft as it is written, then the validated answer.

        The completed answer equals the joined deltas unless validation changed the draft; its
        warnings say so. `stats`, when given, receives the route, tokens and stage times. Only
        admit() counts answers in flight; evals and scripts call this directly, one at a time.
        """
        run = _Run()
        server = trace.get_current_span()  # the request's span carries the answer's outcome
        outcome: Answer | None = None
        failure: BaseException | None = None
        routing: router.Routing | None = None
        early: _Early | None = None
        try:
            companies = await self._evidence.tracked()
            early = self._search_early(request, companies)
            routing = await self._route(request.question, companies, run)
            run.lap("route_ms")
            # The plan reads the one company the question names when the router named none;
            # stats keep the router's own reply, which the evals score.
            planned = router.fill(routing, router.guess(request.question, companies)[0])
            plan = await self._plan(request, planned)
            if isinstance(plan, tuple):
                outcome = self._refusal(*plan, run)
            else:
                kept = early.task if early.agrees(request, planned, plan) else None
                if kept is None:  # a guess the plan does not use must not hold the reranker
                    early.task.cancel()
                async for event in self._answer(request.question, planned, plan, run, kept):
                    if isinstance(event, AnswerCompleted):
                        outcome = event.answer
                    else:
                        yield event
            if outcome is None:  # _answer always completes; this keeps the type checker sure
                raise UpstreamError("The answer ended without a result.")
            outcome = outcome.model_copy(update={"reading": reading_of(planned, companies)})
            if outcome.refused:
                yield AnswerDelta(text=outcome.answer)
            yield AnswerCompleted(answer=outcome)
        except BaseException as exc:  # recorded below, then raised as it was
            failure = exc
            raise
        finally:
            if early is not None:
                early.task.cancel()  # a search the plan did not use; no-op once it was awaited
            run.timings_ms["total_ms"] = run.since_start_ms()
            log.info(
                "answer",
                route=routing.route if routing else None,
                refused=outcome.refused if outcome else None,
                warnings=len(outcome.warnings) if outcome else None,
                degraded=outcome.degraded if outcome else None,
                input_tokens=run.input_tokens,
                output_tokens=run.output_tokens,
                cost_usd=run.cost_usd,
                fallbacks=run.fallbacks,
                first_token_ms=run.first_token_ms,
                **run.timings_ms,
            )
            if stats is not None:
                stats.update(
                    routing=routing.model_dump() if routing else None,
                    timings_ms=run.timings_ms,
                    first_token_ms=run.first_token_ms,
                    input_tokens=run.input_tokens,
                    output_tokens=run.output_tokens,
                    fallbacks=run.fallbacks,
                    top_score=run.top_score,
                    early_search=run.early_search,
                    sources=run.sources,
                )
            _record(run, routing, outcome, failure, server)

    def _search_early(self, request: AnswerRequest, companies: Mapping[str, str]) -> "_Early":
        """Start the search the plan will most likely ask for, so it runs while the router does."""
        tickers, years = router.guess(request.question, companies)
        tickers = [] if request.company_ids else tickers  # the request's companies win, as in _plan
        years = sorted(request.fiscal_years or years)
        task = asyncio.create_task(self._early_search(request, tickers, years))
        task.add_done_callback(_seen)
        return _Early(tickers, years, task)

    async def _early_search(
        self, request: AnswerRequest, tickers: list[str], years: list[int]
    ) -> Ranking:
        ciks = list(request.company_ids) if request.company_ids else None
        if tickers:
            found = await self._evidence.companies(tickers)
            ciks = [found[ticker] for ticker in tickers]
        return await self._evidence.search(request.question, Scope(ciks, years or None))

    async def _route(
        self, question: str, companies: Mapping[str, str], run: _Run
    ) -> router.Routing:
        system = router.system_prompt(self._today(), companies)
        schema = router.schema(companies)

        async def ask(provider: Provider, prompt: str) -> router.Routing:
            completion = await provider.complete(
                system, prompt, max_tokens=router.MAX_TOKENS, schema=schema
            )
            await self._spent(completion, run)
            return router.parse(completion.text, provider.name)

        async def route(provider: Provider) -> router.Routing:
            routing = router.resolve(await ask(provider, question), companies)
            if problems := router.problems(routing, companies):  # once; _plan refuses the rest
                log.info("router reply broke the rules, asking again", problems=problems)
                retry = router.retry_prompt(question, problems)
                routing = router.resolve(await ask(provider, retry), companies)
            if named := router.second_look(routing, question, companies):  # its reply stands
                log.info("router sent a named company out of scope, asking again")
                again = router.second_look_prompt(question, [companies[t] for t in named])
                routing = router.resolve(await ask(provider, again), companies)
            return routing

        return await self._with_fallback("router", route, run)

    async def _plan(
        self, request: AnswerRequest, routing: router.Routing
    ) -> "_Plan | tuple[str, str]":
        """The companies and years to read, or a refusal's code and text."""
        if routing.route == "out_of_scope":
            return "out_of_scope", OUT_OF_SCOPE
        ciks: list[int] | None = list(request.company_ids) if request.company_ids else None
        # An untracked company is refused when the question needs its figures or names nothing
        # tracked; a textual question about a tracked company may mention others (an acquisition).
        others = routing.other_companies
        if ciks is None and others and (not routing.tickers or routing.route != "textual"):
            return "untracked_company", f"FilingLens has no filings for {', '.join(others)}."
        if ciks is None and routing.tickers:
            found = await self._evidence.companies(routing.tickers)
            missing = [ticker for ticker in routing.tickers if ticker not in found]
            if missing:
                return "untracked_company", f"FilingLens has no filings for {', '.join(missing)}."
            ciks = [found[ticker] for ticker in routing.tickers]
        years = list(request.fiscal_years or routing.fiscal_years) or None
        asked = sorted({*map(int, years or []), *router.fiscal_years(request.question)})  # t07
        names = await self._evidence.names(ciks) if ciks else {}
        latest: dict[int, int | None] = {}
        for cik in ciks or []:
            latest[cik] = await self._evidence.latest_fiscal_year(cik)
            late = [year for year in asked if latest[cik] is None or year > (latest[cik] or 0)]
            if late:  # a time trap: that fiscal year has no 10-K yet
                newest = f"its latest is fiscal {latest[cik]}" if latest[cik] else "it has none yet"
                text = f"{names.get(cik, cik)} has filed no 10-K for fiscal {late[0]}; {newest}."
                return "time_trap", text
        return _Plan(ciks, years, names, latest, routing.fiscal_period or "FY")

    async def _answer(
        self,
        question: str,
        routing: router.Routing,
        plan: "_Plan",
        run: _Run,
        early: Awaitable[Ranking] | None = None,
    ) -> AsyncIterator[AnswerDelta | AnswerCompleted]:
        sources: list[drafting.Source] = []
        if routing.metric and routing.route in ("numeric", "comparison") and plan.ciks:
            unit, concepts = router.METRICS[routing.metric]
            for cik in plan.ciks:
                for year in plan.years or [plan.latest.get(cik)]:
                    fact = await self._evidence.fact(cik, concepts, unit, year, plan.period)
                    if fact is not None:
                        sources.append(_fact_source(len(sources) + 1, fact, year, plan))
            run.lap("facts_ms")
        degraded = False
        if routing.route != "numeric" or not sources:
            run.early_search = early is not None
            if early is not None:  # the same question and scope: the same ranking, sooner
                ranking = await early
            else:
                ranking = await self._evidence.search(question, Scope(plan.ciks, plan.years))
            run.lap("retrieve_ms")
            run.timings_ms.update({f"retrieve_{k}": v for k, v in ranking.timings_ms.items()})
            degraded = ranking.degraded
            hits = ranking.hits[:MAX_CHUNKS]
            run.top_score = hits[0].score if hits else None
            relevant = degraded or (bool(hits) and hits[0].score >= self._min_relevance)
            if relevant:
                names = plan.names or await self._evidence.names(sorted({h.cik for h in hits}))
                sources += [_chunk_source(n, hit, names) for n, hit in enumerate(hits, 1)]
        run.sources = {s.alias: s.chunk_id or s.fact_id or "" for s in sources}
        if not sources:
            refusal = self._refusal("no_relevant_passages", NO_EVIDENCE, run, degraded=degraded)
            yield AnswerCompleted(answer=refusal)
            return
        by_alias = {source.alias: source for source in sources}
        visible, reply_text = drafting.Visible(), ""
        prompt = drafting.user_prompt(question, sources)
        async for item in self._stream(drafting.SYSTEM, prompt, run):
            if isinstance(item, Completion):
                reply_text = item.text
                continue
            if shown := visible.feed(item):
                run.first_token_ms = run.first_token_ms or run.since_start_ms()
                yield AnswerDelta(text=shown)
        if shown := visible.feed(final=True):
            run.first_token_ms = run.first_token_ms or run.since_start_ms()
            yield AnswerDelta(text=shown)
        run.lap("generate_ms")
        reply = drafting.read_reply(reply_text)
        checked = drafting.check(reply, by_alias)
        warnings: list[str] = []
        if not reply.insufficient and checked.problems:
            log.info("answer failed validation, regenerating", problems=checked.problems)

            async def redo(provider: Provider) -> Completion:
                completion = await provider.complete(
                    drafting.SYSTEM,
                    drafting.user_prompt(question, sources, checked.problems),
                    max_tokens=drafting.MAX_TOKENS,
                )
                await self._spent(completion, run)
                return completion

            again = await self._with_fallback("primary", redo, run)
            reply = drafting.read_reply(again.text)
            checked = drafting.check(reply, by_alias)
            warnings.append("The draft failed validation, so the answer was written again.")
            run.dropped = checked.removed
            if checked.removed:
                warnings.append(
                    f"Removed {checked.removed} sentence(s) whose citations or amounts did not"
                    " check out."
                )
            run.lap("regenerate_ms")
        if checked.pruned:
            warnings.append(
                f"Removed {checked.pruned} citation(s) whose source or quote did not check out."
            )
        if reply.insufficient or not checked.text:
            code, text = (
                ("insufficient_evidence", NO_EVIDENCE)
                if reply.insufficient
                else ("validation_failed", "No sentence of the answer held up.")
            )
            yield AnswerCompleted(answer=self._refusal(code, text, run, degraded, warnings))
            return
        citations = [
            Citation(
                chunk_id=by_alias[alias].chunk_id,
                fact_id=by_alias[alias].fact_id,
                quote=by_alias[alias].text if by_alias[alias].fact_id else quote,
                filing_url=by_alias[alias].url,
            )
            for alias, quote in checked.citations
        ]
        number = {alias: n for n, (alias, _) in enumerate(checked.citations, 1)}
        answer = Answer(
            answer=checked.text,
            citations=citations,
            degraded=degraded,
            usage=_usage(run),
            refused=False,
            warnings=warnings,
            checks=[
                FigureCheck(
                    text=f.text, citation=number[f.alias], source_value=f"{f.number.normalize():,f}"
                )
                for f in checked.figures
            ],
        )
        yield AnswerCompleted(answer=answer)

    async def _chain(self, role: str) -> list[Provider]:
        """The models a router or answer call tries in order: its own, then for answers
        LLM_ANSWER_FALLBACK, then LLM_FALLBACK; evals turn fallbacks off. Claude is left out
        while it cannot answer (off for good, or today's budget used up), with no fallback logged;
        alone in the chain, its reason is raised."""
        models = self._models
        chain = [models.router if role == "router" else models.primary]
        if self._allow_fallback:
            if role == "primary" and models.answer_fallback:
                chain.append(models.answer_fallback)
            chain.append(models.fallback)
        usable: list[Provider] = []
        skipped: FilingLensError | None = None
        for provider in dict.fromkeys(chain):  # a model in two places is tried once
            reason = await provider.unusable() if isinstance(provider, Anthropic) else None
            if reason is None:
                usable.append(provider)
            else:
                skipped = reason
        if skipped is not None and not usable:
            raise skipped
        return usable

    async def _stream(self, system: str, user: str, run: _Run) -> AsyncIterator[str | Completion]:
        """The answer's stream; a failure before the first text tries the next model."""
        chain = await self._chain("primary")
        for attempt, provider in enumerate(chain):
            started = False
            try:
                async for item in provider.stream(system, user, max_tokens=drafting.MAX_TOKENS):
                    if isinstance(item, Completion):
                        await self._spent(item, run)
                    else:
                        started = True
                    yield item
                return
            except FilingLensError as exc:
                if started or attempt == len(chain) - 1:
                    raise _final(exc) from exc
                await self._fell_back("primary", provider, chain[attempt + 1], exc, run)

    async def _with_fallback[T](
        self, role: str, call: Callable[[Provider], Awaitable[T]], run: _Run
    ) -> T:
        chain = await self._chain(role)
        for provider, next_one in itertools.pairwise(chain):
            try:
                return await call(provider)
            except FilingLensError as exc:
                await self._fell_back(role, provider, next_one, exc, run)
        try:
            return await call(chain[-1])
        except FilingLensError as exc:
            raise _final(exc) from exc

    async def _fell_back(
        self, role: str, provider: Provider, to: Provider, exc: Exception, run: _Run
    ) -> None:
        run.fallbacks.append(f"{role}: {provider.name}: {exc}")
        kind = exc.code if isinstance(exc, FilingLensError) else type(exc).__qualname__
        trace.get_current_span().add_event(  # the request's span; never the message
            "fallback", {"role": role, "from": provider.name, "to": to.name, "error.type": kind}
        )
        log.warning(
            "model call fell back",
            role=role,
            model=provider.name,
            fallback=to.name,
            reason=str(exc),
        )
        try:
            await budget.record_fallback(self._redis)
        except RedisError as error:
            log.warning("fallback not counted", error=repr(error))

    async def _spent(self, completion: Completion, run: _Run) -> None:
        run.input_tokens += completion.input_tokens
        run.output_tokens += completion.output_tokens
        run.cost_usd += credits_usd(
            completion.model, completion.input_tokens, completion.output_tokens
        )
        if completion.model.startswith("anthropic:"):  # Claude counts in its own ledger
            return
        try:
            await budget.record(self._redis, completion.input_tokens + completion.output_tokens)
        except RedisError as error:  # the answer already cost the tokens; keep it
            log.warning("tokens not counted", error=repr(error))

    def _refusal(
        self,
        code: str,
        text: str,
        run: _Run,
        degraded: bool = False,
        warnings: Sequence[str] = (),
    ) -> Answer:
        run.refusal = code  # metrics.REFUSALS: the text names companies, so it never labels
        return Answer(
            answer=text,
            citations=[],
            degraded=degraded,
            usage=_usage(run),
            refused=True,
            warnings=list(warnings),
        )


@dataclass(frozen=True)
class _Early:
    """The search started with the router, on the tickers and fiscal years the question names."""

    tickers: list[str]  # [] when the request names its companies
    years: list[int]
    task: "asyncio.Task[Ranking]"

    def agrees(self, request: AnswerRequest, routing: router.Routing, plan: "_Plan") -> bool:
        """Whether the plan searches the same companies and fiscal years."""
        companies = bool(request.company_ids) or self.tickers == routing.tickers
        return companies and self.years == sorted(plan.years or [])


def _seen(task: "asyncio.Task[Ranking]") -> None:
    """Retrieve an unused early search's error, so asyncio does not log it as never retrieved."""
    if not task.cancelled():
        task.exception()


@dataclass(frozen=True)
class _Plan:
    ciks: list[int] | None  # None: every company
    years: list[int] | None  # None: any fiscal year
    names: dict[int, str]
    latest: dict[int, int | None]  # each company's latest fiscal year with a 10-K
    period: str  # FY, Q1-Q4


def _final(exc: FilingLensError) -> FilingLensError:
    """What the caller sees once no fallback is left: rate limits become 503 ai_unavailable."""
    if isinstance(exc, RateLimitedError):
        return AiUnavailableError(
            "The model providers are rate limited; try again shortly.",
            retry_after_s=exc.retry_after_s or 60,
        )
    if isinstance(exc, AiUnavailableError):
        log.error("model provider unavailable", reason=str(exc))  # 402 credits, refused key
    return exc


def _usage(run: _Run) -> Usage:
    return Usage(
        input_tokens=run.input_tokens, output_tokens=run.output_tokens, cost_usd=run.cost_usd
    )


def reading_of(routing: router.Routing, companies: Mapping[str, str]) -> Reading:
    """The router's reading as the answer reports it, each tracked ticker with its name; the demo
    export reads its saved answers' routing the same way."""
    return Reading(
        route=routing.route,
        companies=[ReadCompany(ticker=t, name=companies.get(t, t)) for t in routing.tickers],
        other_companies=routing.other_companies,
        fiscal_years=routing.fiscal_years,
        fiscal_period=routing.fiscal_period,
        metric=routing.metric,
    )


def _outcome(run: _Run, outcome: Answer | None, failure: BaseException | None) -> tuple[str, str]:
    """The answer's outcome and reason, from metrics.REFUSALS and metrics.FAILURES."""
    if outcome is not None:
        return ("refused", run.refusal or "none") if outcome.refused else ("answered", "none")
    if isinstance(failure, FilingLensError):
        return "failed", failure.code if failure.code in metrics.FAILURES else "upstream_error"
    if isinstance(failure, asyncio.CancelledError | GeneratorExit):
        from filinglens_api.limits import ANSWER_TIMEOUT_S  # limits imports this module

        timed_out = run.since_start_ms() >= ANSWER_TIMEOUT_S * 1000 - 100
        return ("failed", "timeout") if timed_out else ("cancelled", "none")  # else: client left
    return "failed", "internal"


def _record(
    run: _Run,
    routing: router.Routing | None,
    outcome: Answer | None,
    failure: BaseException | None,
    server: trace.Span,
) -> None:
    """The answer's metrics, and its outcome on the request's span, from the run's bookkeeping."""
    result, reason = _outcome(run, outcome, failure)
    route = {"route": routing.route if routing else "none"}
    metrics.ANSWERS.add(1, {"outcome": result, "reason": reason})
    for stage in STAGES:
        if stage in run.timings_ms:
            stage_label = {**route, "stage": stage.removesuffix("_ms")}
            metrics.ANSWER_STAGE.record(run.timings_ms[stage] / 1000, stage_label)
    if run.first_token_ms is not None:
        metrics.ANSWER_TTFT.record(run.first_token_ms / 1000, route)
    if "regenerate_ms" in run.timings_ms:
        metrics.REGENERATIONS.add(1)
    if run.dropped:
        metrics.DROPPED.add(run.dropped)
    if run.cost_usd:
        metrics.CREDITS.add(run.cost_usd)
    server.set_attributes(
        {
            "filinglens.answer.outcome": result,
            "filinglens.answer.reason": reason,
            "filinglens.answer.route": route["route"],
            "filinglens.answer.degraded": bool(outcome and outcome.degraded),
            "filinglens.answer.early_search": bool(run.early_search),
            "gen_ai.usage.input_tokens": run.input_tokens,
            "gen_ai.usage.output_tokens": run.output_tokens,
        }
    )


def _folder(cik: int, accession_number: str) -> str:
    return f"{SEC_ARCHIVES}/{cik}/{accession_number.replace('-', '')}/"


def _fact_source(n: int, fact: Fact, year: int | None, plan: _Plan) -> drafting.Source:
    period = (
        f"{fact.period_start} to {fact.period_end}"
        if fact.period_start
        else f"at {fact.period_end}"
    )
    fiscal = f"fiscal {year} {fact.fiscal_period}" if year else fact.fiscal_period
    if year and fact.period_start is None and fact.fiscal_period != plan.period:
        # A balance from a later filing's comparative (n17, n24): the period asked for, not that
        # filing's ("fiscal 2025 Q2" for a year-end balance from a 2026 10-Q).
        fiscal = f"at {fact.period_end}" if plan.period == "FY" else f"fiscal {year} {plan.period}"
        period = f"the end of fiscal {year}" if plan.period == "FY" else f"at {fact.period_end}"
    return drafting.Source(
        alias=f"F{n}",
        chunk_id=None,
        fact_id=str(fact.id),
        heading=(
            f"{plan.names.get(fact.cik, fact.cik)} | {fact.label} ({fact.concept}) | {fiscal},"
            f" {period} | {fact.form} filed {fact.filed_on}"
        ),
        text=f"{fact.value:,f} {fact.unit}",  # fixed point: values may come as 4.1616100E+11
        value=fact.value,
        url=_folder(fact.cik, fact.accession_number),
    )


def _chunk_source(n: int, hit: Hit, names: dict[int, str]) -> drafting.Source:
    return drafting.Source(
        alias=f"C{n}",
        chunk_id=hit.chunk_id,
        fact_id=None,
        heading=(
            f"{names.get(hit.cik, hit.cik)} | {hit.form_type} fiscal {hit.fiscal_year}"
            f" {hit.fiscal_period} | Item {hit.item}"
        ),
        text=hit.text,
        value=None,
        url=_folder(hit.cik, hit.accession_number) + hit.primary_document,
    )


class PostgresEvidence:
    """Evidence from Postgres: companies, XBRL facts (latest-filed rule) and hybrid search."""

    def __init__(self, engine: AsyncEngine, settings: ApiSettings) -> None:
        self._engine = engine
        self._settings = settings

    async def companies(self, tickers: Sequence[str]) -> dict[str, int]:
        query = select(func.upper(Company.ticker), Company.cik).where(
            func.upper(Company.ticker).in_([ticker.upper() for ticker in tickers])
        )
        async with self._engine.connect() as connection:
            return {ticker: cik for ticker, cik in await connection.execute(query)}

    async def tracked(self) -> dict[str, str]:
        indexed = (
            select(Filing.id)
            .where(Filing.cik == Company.cik, Filing.status == FilingStatus.INDEXED)
            .exists()
        )
        query = select(func.upper(Company.ticker), Company.name).where(indexed)
        async with self._engine.connect() as connection:
            return {ticker: name for ticker, name in await connection.execute(query)}

    async def names(self, ciks: Sequence[int]) -> dict[int, str]:
        query = select(Company.cik, Company.name, Company.ticker).where(Company.cik.in_(ciks))
        async with self._engine.connect() as connection:
            rows = await connection.execute(query)
            return {cik: f"{name} ({ticker})" for cik, name, ticker in rows}

    async def latest_fiscal_year(self, cik: int) -> int | None:
        async with self._engine.connect() as connection:
            return await latest_fiscal_year(connection, cik)

    async def fact(
        self, cik: int, concepts: Sequence[str], unit: str, fiscal_year: int | None, period: str
    ) -> Fact | None:
        async with self._engine.connect() as connection:
            return await get_financial_fact(
                connection, cik, concepts, unit, fiscal_year=fiscal_year, fiscal_period=period
            )

    async def search(self, question: str, scope: Scope) -> Ranking:
        settings = self._settings
        return await search(
            self._engine,
            question,
            embedding=settings.retrieval_embedding_column,
            scope=scope,
            rerank_model=settings.rerank_model,
            candidates=settings.rerank_candidates,
            max_tokens=settings.rerank_max_tokens,
            timeout_s=settings.rerank_timeout_ms / 1000,
        )
