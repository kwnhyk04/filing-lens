"""Answers: route the question, gather facts or chunks, write a cited answer, then validate it.

The router (LLM_ROUTER) picks the path and names the companies and periods. Numeric questions read
XBRL facts first (get_financial_fact) and search filing text only when no fact exists; textual and
comparison questions search. The primary model (LLM_PRIMARY) writes the answer with [n] markers
and quotes, and every sentence must pass validation (filinglens_llm.answer.check); a failure gets
one regeneration, then the failing sentences are dropped with a warning. A router or primary call
that fails falls back once to LLM_FALLBACK, unless allow_fallback is off (evals), and each fallback
is logged and counted. Out-of-scope questions, unknown companies, fiscal years with no 10-K yet
and questions without relevant evidence get a refusal instead of a model answer.
"""

import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

import structlog
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
from filinglens_db.models import Company
from filinglens_llm import answer as drafting
from filinglens_llm import budget, router
from filinglens_llm.providers import Completion, Provider
from filinglens_retrieval import Hit, Ranking, Scope, search
from filinglens_retrieval.facts import Fact, get_financial_fact, latest_fiscal_year

SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
MAX_CHUNKS = 12  # chunks the answer model reads
RELEVANCE_MIN = -3.0  # provisional: TinyBERT gave 0.7 to 9.4 on topic, -10.9 off; 6b calibrates
NO_EVIDENCE = "The filings in FilingLens hold nothing relevant enough to answer this question."
OUT_OF_SCOPE = "SEC filings cannot answer this question, so FilingLens does not answer it."
log = structlog.get_logger(__name__)


class Evidence(Protocol):
    """What answers read: companies, facts and chunks. PostgresEvidence serves production."""

    async def companies(self, tickers: Sequence[str]) -> dict[str, int]:
        """CIK by ticker, for the tickers FilingLens tracks."""
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


@dataclass
class _Run:
    """One answer's bookkeeping: tokens, fallbacks and stage times, logged at the end."""

    started: float = field(default_factory=time.perf_counter)
    lap_at: float = field(default_factory=time.perf_counter)
    timings_ms: dict[str, float] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    fallbacks: list[str] = field(default_factory=list)
    first_token_ms: float | None = None

    def lap(self, stage: str) -> None:
        now = time.perf_counter()
        self.timings_ms[stage] = round((now - self.lap_at) * 1000, 1)
        self.lap_at = now

    def since_start_ms(self) -> float:
        return round((time.perf_counter() - self.started) * 1000, 1)


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
    ) -> None:
        self._evidence = evidence
        self._models = models
        self._redis = redis
        self._max_inflight = max_inflight
        self._allow_fallback = allow_fallback
        self._today = today
        self._inflight = 0

    def admit(self) -> None:
        """Shed load before any work: OverloadedError (503) past the in-flight cap."""
        if self._inflight >= self._max_inflight:
            raise OverloadedError("Too many answers in progress; retry shortly.", retry_after_s=2)

    async def events(
        self, request: AnswerRequest, stats: dict[str, Any] | None = None
    ) -> AsyncIterator[AnswerDelta | AnswerCompleted]:
        """Deltas of the draft as it is written, then the validated answer.

        The completed answer equals the joined deltas unless validation changed the draft; its
        warnings say so. `stats`, when given, receives the route, tokens and stage times.
        """
        self._inflight += 1
        run = _Run()
        outcome: Answer | None = None
        routing: router.Routing | None = None
        try:
            routing = await self._route(request.question, run)
            run.lap("route_ms")
            plan = await self._plan(request, routing)
            if isinstance(plan, str):
                outcome = self._refusal(plan, run)
            else:
                async for event in self._answer(request.question, routing, plan, run):
                    if isinstance(event, AnswerCompleted):
                        outcome = event.answer
                    else:
                        yield event
            if outcome is None:  # _answer always completes; this keeps the type checker sure
                raise UpstreamError("The answer ended without a result.")
            if outcome.refused:
                yield AnswerDelta(text=outcome.answer)
            yield AnswerCompleted(answer=outcome)
        finally:
            self._inflight -= 1
            run.timings_ms["total_ms"] = run.since_start_ms()
            log.info(
                "answer",
                route=routing.route if routing else None,
                refused=outcome.refused if outcome else None,
                warnings=len(outcome.warnings) if outcome else None,
                degraded=outcome.degraded if outcome else None,
                input_tokens=run.input_tokens,
                output_tokens=run.output_tokens,
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
                )

    async def _route(self, question: str, run: _Run) -> router.Routing:
        async def ask(provider: Provider) -> router.Routing:
            completion = await provider.complete(
                router.system_prompt(self._today()),
                question,
                max_tokens=router.MAX_TOKENS,
                schema=router.SCHEMA,
            )
            await self._spent(completion, run)
            return router.parse(completion.text, provider.name)

        return await self._with_fallback("router", self._models.router, ask, run)

    async def _plan(self, request: AnswerRequest, routing: router.Routing) -> "_Plan | str":
        """The companies and years to read, or a refusal."""
        if routing.route == "out_of_scope":
            return OUT_OF_SCOPE
        ciks: list[int] | None = list(request.company_ids) if request.company_ids else None
        if ciks is None and routing.tickers:
            found = await self._evidence.companies(routing.tickers)
            missing = [ticker for ticker in routing.tickers if ticker not in found]
            if missing:
                return f"FilingLens has no filings for {', '.join(missing)}."
            ciks = [found[ticker] for ticker in routing.tickers]
        years = list(request.fiscal_years or routing.fiscal_years) or None
        names = await self._evidence.names(ciks) if ciks else {}
        latest: dict[int, int | None] = {}
        for cik in ciks or []:
            latest[cik] = await self._evidence.latest_fiscal_year(cik)
            late = [
                year for year in years or [] if latest[cik] is None or year > (latest[cik] or 0)
            ]
            if late:  # a time trap: that fiscal year has no 10-K yet
                newest = f"its latest is fiscal {latest[cik]}" if latest[cik] else "it has none yet"
                return f"{names.get(cik, cik)} has filed no 10-K for fiscal {late[0]}; {newest}."
        return _Plan(ciks, years, names, latest, routing.fiscal_period or "FY")

    async def _answer(
        self, question: str, routing: router.Routing, plan: "_Plan", run: _Run
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
            ranking = await self._evidence.search(question, Scope(plan.ciks, plan.years))
            run.lap("retrieve_ms")
            run.timings_ms.update({f"retrieve_{k}": v for k, v in ranking.timings_ms.items()})
            degraded = ranking.degraded
            hits = ranking.hits[:MAX_CHUNKS]
            relevant = degraded or (bool(hits) and hits[0].score >= RELEVANCE_MIN)
            if relevant:
                names = plan.names or await self._evidence.names(sorted({h.cik for h in hits}))
                sources += [_chunk_source(n, hit, names) for n, hit in enumerate(hits, 1)]
        if not sources:
            yield AnswerCompleted(answer=self._refusal(NO_EVIDENCE, run, degraded=degraded))
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

            again = await self._with_fallback("primary", self._models.primary, redo, run)
            reply = drafting.read_reply(again.text)
            checked = drafting.check(reply, by_alias)
            warnings.append("The draft failed validation, so the answer was written again.")
            if checked.removed:
                warnings.append(
                    f"Removed {checked.removed} sentence(s) whose citations or amounts did not"
                    " check out."
                )
            run.lap("regenerate_ms")
        if reply.insufficient or not checked.text:
            reason = NO_EVIDENCE if reply.insufficient else "No sentence of the answer held up."
            yield AnswerCompleted(answer=self._refusal(reason, run, degraded, warnings))
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
        answer = Answer(
            answer=checked.text,
            citations=citations,
            degraded=degraded,
            usage=_usage(run),
            refused=False,
            warnings=warnings,
        )
        yield AnswerCompleted(answer=answer)

    async def _stream(self, system: str, user: str, run: _Run) -> AsyncIterator[str | Completion]:
        """The primary's stream; a failure before its first text falls back to LLM_FALLBACK."""
        chain = [self._models.primary]
        if self._allow_fallback and self._models.fallback is not self._models.primary:
            chain.append(self._models.fallback)
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
                await self._fell_back("primary", provider, exc, run)

    async def _with_fallback[T](
        self, role: str, first: Provider, call: Callable[[Provider], Awaitable[T]], run: _Run
    ) -> T:
        try:
            return await call(first)
        except FilingLensError as exc:
            fallback = self._models.fallback
            if not self._allow_fallback or fallback is first:
                raise _final(exc) from exc
            await self._fell_back(role, first, exc, run)
            try:
                return await call(fallback)
            except FilingLensError as again:
                raise _final(again) from again

    async def _fell_back(self, role: str, provider: Provider, exc: Exception, run: _Run) -> None:
        run.fallbacks.append(f"{role}: {provider.name}: {exc}")
        log.warning(
            "model call fell back",
            role=role,
            model=provider.name,
            fallback=self._models.fallback.name,
            reason=str(exc),
        )
        try:
            await budget.record_fallback(self._redis)
        except RedisError as error:
            log.warning("fallback not counted", error=repr(error))

    async def _spent(self, completion: Completion, run: _Run) -> None:
        run.input_tokens += completion.input_tokens
        run.output_tokens += completion.output_tokens
        try:
            await budget.record(self._redis, completion.input_tokens + completion.output_tokens)
        except RedisError as error:  # the answer already cost the tokens; keep it
            log.warning("tokens not counted", error=repr(error))

    def _refusal(
        self, reason: str, run: _Run, degraded: bool = False, warnings: Sequence[str] = ()
    ) -> Answer:
        return Answer(
            answer=reason,
            citations=[],
            degraded=degraded,
            usage=_usage(run),
            refused=True,
            warnings=list(warnings),
        )


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
    return Usage(input_tokens=run.input_tokens, output_tokens=run.output_tokens, cost_usd=0.0)


def _folder(cik: int, accession_number: str) -> str:
    return f"{SEC_ARCHIVES}/{cik}/{accession_number.replace('-', '')}/"


def _fact_source(n: int, fact: Fact, year: int | None, plan: _Plan) -> drafting.Source:
    period = (
        f"{fact.period_start} to {fact.period_end}"
        if fact.period_start
        else f"at {fact.period_end}"
    )
    fiscal = f"fiscal {year} {fact.fiscal_period}" if year else fact.fiscal_period
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
