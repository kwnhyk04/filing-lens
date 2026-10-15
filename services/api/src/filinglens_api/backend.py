"""The routes' data seam. LiveBackend serves production; the tests swap in an in-memory fake."""

import asyncio
import base64
from collections.abc import AsyncIterator, Callable, Sequence
from datetime import date
from typing import Annotated, Any, Protocol
from uuid import UUID

from celery import Celery
from fastapi import Depends, Request
from kombu import Queue
from kombu.exceptions import OperationalError
from pydantic import BaseModel
from sqlalchemy import Row, Select, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from filinglens_api.answering import Answerer
from filinglens_api.schemas import (
    Answer,
    AnswerCompleted,
    AnswerDelta,
    AnswerRequest,
    Chunk,
    ChunkPage,
    Company,
    CompanyPage,
    FactPage,
    FailurePage,
    Filing,
    FilingCounts,
    FilingFailure,
    FilingPage,
    FinancialFact,
    FiscalPeriod,
    FormType,
    IngestJob,
    IngestJobRequest,
    SearchHit,
    SearchPage,
    Section,
)
from filinglens_core import queues
from filinglens_core.errors import (
    AiUnavailableError,
    ConflictError,
    IdempotencyKeyReusedError,
    InvalidInputError,
    NotFoundError,
    NotImplementedYetError,
    OverloadedError,
    UpstreamError,
)
from filinglens_core.settings import ApiSettings
from filinglens_db.models import Chunk as ChunkRow
from filinglens_db.models import Company as CompanyRow
from filinglens_db.models import Filing as FilingRow
from filinglens_db.models import FilingStatus, ItemStatus, JobStatus
from filinglens_db.models import FinancialFact as FactRow
from filinglens_db.models import IngestJob as JobRow
from filinglens_db.models import IngestJobCompany as JobCompanyRow
from filinglens_db.models import IngestJobItem as ItemRow
from filinglens_db.models import Section as SectionRow
from filinglens_retrieval import Hit, Scope, search

SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
UNUSABLE_CURSOR = "Unusable cursor; start again without one"


# Keyset cursor contents: the sort key of the last item on a page.
class CompanyKey(BaseModel):
    cik: int


class FilingKey(BaseModel):
    filed_on: date
    accession_number: str


class FailureKey(BaseModel):
    accession_number: str


class ItemKey(BaseModel):
    """Chunks and facts page by id."""

    id: str


class SearchKey(BaseModel):
    """Hits rank by (score desc, chunk_id); index_version pins the page to one embedding index.

    degraded marks a page in fused order (reranker timed out): the next pages keep that order.
    """

    score: float
    chunk_id: str
    index_version: str
    degraded: bool = False


def encode_cursor(key: BaseModel) -> str:
    """Opaque cursor: unpadded URL-safe base64 of the key's JSON."""
    return base64.urlsafe_b64encode(key.model_dump_json().encode()).decode().rstrip("=")


def decode_cursor[K: BaseModel](cursor: str, key: type[K]) -> K:
    try:
        return key.model_validate_json(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except ValueError:  # bad base64, bad JSON and ValidationError are all ValueErrors
        raise InvalidInputError(UNUSABLE_CURSOR) from None


def _page[T](
    items: list[T], limit: int, key: Callable[[T], BaseModel]
) -> tuple[list[T], str | None]:
    """Cut a query's limit + 1 items to a page; the extra one only says another page exists."""
    if len(items) <= limit:
        return items, None
    return items[:limit], encode_cursor(key(items[limit - 1]))


def _row_id(value: str) -> int | None:
    """A bigint id from client input, or None when the input cannot be one."""
    return int(value) if value.isascii() and value.isdigit() and len(value) < 19 else None


def _filing(row: Row[*tuple[Any, ...]]) -> Filing:
    folder = row.accession_number.replace("-", "")
    return Filing(
        accession_number=row.accession_number,
        cik=row.cik,
        form_type=row.form_type,
        filed_on=row.filed_on,
        period_end=row.period_end,
        fiscal_year=row.fiscal_year,
        fiscal_period=row.fiscal_period,
        url=f"{SEC_ARCHIVES}/{row.cik}/{folder}/{row.primary_document}",
    )


class Backend(Protocol):
    async def create_ingest_job(self, request: IngestJobRequest, idempotency_key: str) -> UUID:
        """Same key and body: the existing job. Same key, other body: IdempotencyKeyReusedError."""
        ...

    async def get_ingest_job(self, job_id: UUID, limit: int, cursor: str | None) -> IngestJob:
        """Raises NotFoundError for an unknown job; limit and cursor page its failures."""
        ...

    async def list_companies(self, limit: int, cursor: str | None) -> CompanyPage: ...

    async def list_filings(
        self,
        limit: int,
        cursor: str | None,
        *,
        cik: int | None = None,
        form_type: FormType | None = None,
        fiscal_year: int | None = None,
    ) -> FilingPage: ...

    async def list_sections(self, accession_number: str) -> list[Section]: ...

    async def list_chunks(
        self,
        accession_number: str,
        limit: int,
        cursor: str | None,
        *,
        section_id: str | None = None,
    ) -> ChunkPage: ...

    async def list_facts(
        self, accession_number: str, limit: int, cursor: str | None, *, concept: str | None = None
    ) -> FactPage: ...

    async def search(
        self,
        q: str,
        limit: int,
        cursor: str | None,
        *,
        cik: int | None = None,
        fiscal_year: int | None = None,
    ) -> SearchPage:
        """ConflictError (409) when the cursor comes from another embedding index."""
        ...

    async def answer(self, request: AnswerRequest) -> Answer: ...

    async def stream_answer(
        self, request: AnswerRequest
    ) -> AsyncIterator[AnswerDelta | AnswerCompleted]:
        """Admit the request first, so errors here still get a status code; then return events."""
        ...


def get_backend(request: Request) -> Backend:
    return request.app.state.backend


BackendDep = Annotated[Backend, Depends(get_backend)]


class DiscoverQueue:
    """Queues discover tasks for the ingest worker, with publisher confirms."""

    def __init__(self, broker_url: str) -> None:
        self._celery = Celery("filinglens_api", broker=broker_url, set_as_current=False)
        self._celery.conf.update(
            broker_transport_options={"confirm_publish": True}, broker_connection_timeout=5
        )
        arguments = queues.QUEUE_ARGUMENTS[queues.DISCOVER]  # must match the worker's declaration
        self._queue = Queue(queues.DISCOVER, routing_key=queues.DISCOVER, queue_arguments=arguments)

    def publish(self, job_id: UUID, ciks: Sequence[int]) -> None:
        for cik in ciks:
            self._celery.send_task(
                queues.DISCOVER_TASK, args=[str(job_id), cik], queue=self._queue, confirm_timeout=5
            )


class LiveBackend:
    """Production backend: Postgres, RabbitMQ for ingest jobs, local models for search, and the
    answer pipeline. Scripts that only queue jobs pass neither settings nor an answerer."""

    def __init__(
        self,
        engine: AsyncEngine,
        discover: DiscoverQueue,
        settings: ApiSettings | None = None,
        answerer: Answerer | None = None,
    ) -> None:
        self._engine = engine
        self._discover = discover
        self._settings = settings
        self._answerer = answerer

    async def _rows[*Ts](self, query: Select[*Ts]) -> Sequence[Row[*Ts]]:
        async with self._engine.connect() as connection:
            return (await connection.execute(query)).all()

    async def list_companies(self, limit: int, cursor: str | None) -> CompanyPage:
        query = select(CompanyRow.cik, CompanyRow.ticker, CompanyRow.name)
        if cursor is not None:
            query = query.where(CompanyRow.cik > decode_cursor(cursor, CompanyKey).cik)
        rows = await self._rows(query.order_by(CompanyRow.cik).limit(limit + 1))
        companies = [Company(cik=row.cik, ticker=row.ticker, name=row.name) for row in rows]
        items, next_cursor = _page(companies, limit, lambda c: CompanyKey(cik=c.cik))
        return CompanyPage(items=items, next_cursor=next_cursor)

    async def create_ingest_job(self, request: IngestJobRequest, idempotency_key: str) -> UUID:
        ciks = sorted(set(request.ciks))
        insert_job = (
            insert(JobRow)
            .values(idempotency_key=idempotency_key, request=request.model_dump(mode="json"))
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
            .returning(JobRow.id)
        )
        async with self._engine.begin() as connection:
            job_id = (await connection.execute(insert_job)).scalar_one_or_none()
            if job_id is None:  # the key came before
                query = select(JobRow.id, JobRow.request, JobRow.status)
                job = (
                    await connection.execute(query.where(JobRow.idempotency_key == idempotency_key))
                ).one()
                if IngestJobRequest.model_validate(job.request) != request:
                    raise IdempotencyKeyReusedError(
                        "This Idempotency-Key came with a different body."
                    )
                job_id, queued = job.id, job.status == JobStatus.QUEUED
            else:
                rows = [{"job_id": job_id, "cik": cik} for cik in ciks]
                await connection.execute(insert(JobCompanyRow).values(rows))
                queued = True
        if queued:  # a retry queues again, in case the first request died before queueing
            try:
                await asyncio.to_thread(self._discover.publish, job_id, ciks)
            except (OperationalError, OSError) as exc:
                raise OverloadedError(
                    "Could not queue the job; retry with the same Idempotency-Key.",
                    retry_after_s=5,
                ) from exc
        return job_id

    async def get_ingest_job(self, job_id: UUID, limit: int, cursor: str | None) -> IngestJob:
        query = select(JobRow.request, JobRow.status, JobRow.created_at).where(JobRow.id == job_id)
        failures = (
            select(
                FilingRow.accession_number,
                FilingRow.cik,
                FilingRow.form_type,
                ItemRow.error,
                ItemRow.attempts,
                ItemRow.updated_at,
            )
            .join(FilingRow, FilingRow.id == ItemRow.filing_id)
            .where(ItemRow.job_id == job_id, ItemRow.status == ItemStatus.FAILED)
        )
        if cursor is not None:
            after = decode_cursor(cursor, FailureKey).accession_number
            failures = failures.where(FilingRow.accession_number > after)
        failures = failures.order_by(FilingRow.accession_number).limit(limit + 1)
        counts = select(ItemRow.status, func.count()).where(ItemRow.job_id == job_id)
        async with self._engine.connect() as connection:
            job = (await connection.execute(query)).one_or_none()
            if job is None:
                raise NotFoundError("No such ingest job.")
            by_status = {s: n for s, n in await connection.execute(counts.group_by(ItemRow.status))}
            rows = (await connection.execute(failures)).all()
        items, next_cursor = _page(
            [
                FilingFailure(
                    accession_number=row.accession_number,
                    cik=row.cik,
                    form_type=row.form_type,
                    error=row.error or "",
                    attempts=row.attempts,
                    failed_at=row.updated_at,
                )
                for row in rows
            ],
            limit,
            lambda f: FailureKey(accession_number=f.accession_number),
        )
        return IngestJob(
            job_id=job_id,
            status=job.status.value,
            request=IngestJobRequest.model_validate(job.request),
            created_at=job.created_at,
            counts=FilingCounts(**{s.value: by_status.get(s, 0) for s in ItemStatus}),
            failures=FailurePage(items=items, next_cursor=next_cursor),
        )

    async def list_filings(
        self,
        limit: int,
        cursor: str | None,
        *,
        cik: int | None = None,
        form_type: FormType | None = None,
        fiscal_year: int | None = None,
    ) -> FilingPage:
        query = select(
            FilingRow.accession_number,
            FilingRow.cik,
            FilingRow.form_type,
            FilingRow.filed_on,
            FilingRow.period_end,
            FilingRow.fiscal_year,
            FilingRow.fiscal_period,
            FilingRow.primary_document,
        ).where(FilingRow.status == FilingStatus.INDEXED)
        if cik is not None:
            query = query.where(FilingRow.cik == cik)
        if form_type is not None:
            query = query.where(FilingRow.form_type == form_type.value)
        if fiscal_year is not None:
            query = query.where(FilingRow.fiscal_year == fiscal_year)
        if cursor is not None:
            last = decode_cursor(cursor, FilingKey)
            position = tuple_(FilingRow.filed_on, FilingRow.accession_number)
            query = query.where(position < (last.filed_on, last.accession_number))
        newest_first = (FilingRow.filed_on.desc(), FilingRow.accession_number.desc())
        rows = await self._rows(query.order_by(*newest_first).limit(limit + 1))
        items, next_cursor = _page(
            [_filing(row) for row in rows],
            limit,
            lambda f: FilingKey(filed_on=f.filed_on, accession_number=f.accession_number),
        )
        return FilingPage(items=items, next_cursor=next_cursor)

    async def list_sections(self, accession_number: str) -> list[Section]:
        query = (
            select(SectionRow.id, SectionRow.item, SectionRow.title)
            .join(FilingRow, FilingRow.id == SectionRow.filing_id)
            .where(FilingRow.accession_number == accession_number)
            .order_by(SectionRow.char_start)
        )
        rows = await self._rows(query)
        return [Section(id=str(row.id), item=row.item, title=row.title) for row in rows]

    async def list_chunks(
        self,
        accession_number: str,
        limit: int,
        cursor: str | None,
        *,
        section_id: str | None = None,
    ) -> ChunkPage:
        query = (
            select(ChunkRow.id, ChunkRow.section_id, ChunkRow.text)
            .join(SectionRow, SectionRow.id == ChunkRow.section_id)
            .join(FilingRow, FilingRow.id == SectionRow.filing_id)
            .where(FilingRow.accession_number == accession_number)
        )
        if section_id is not None:  # an id that cannot exist matches nothing
            query = query.where(ChunkRow.section_id == _row_id(section_id))
        if cursor is not None:
            # The cursor holds only the chunk id, so look up where that chunk sits in the text.
            last = decode_cursor(cursor, ItemKey).id
            found = await self._rows(select(ChunkRow.char_start).where(ChunkRow.id == last))
            if not found:
                raise InvalidInputError(UNUSABLE_CURSOR)
            position = tuple_(ChunkRow.char_start, ChunkRow.id)
            query = query.where(position > (found[0].char_start, last))
        rows = await self._rows(query.order_by(ChunkRow.char_start, ChunkRow.id).limit(limit + 1))
        chunks = [Chunk(id=row.id, section_id=str(row.section_id), text=row.text) for row in rows]
        items, next_cursor = _page(chunks, limit, lambda c: ItemKey(id=c.id))
        return ChunkPage(items=items, next_cursor=next_cursor)

    async def list_facts(
        self, accession_number: str, limit: int, cursor: str | None, *, concept: str | None = None
    ) -> FactPage:
        query = select(
            FactRow.id,
            FactRow.taxonomy,
            FactRow.concept,
            FactRow.label,
            FactRow.value,
            FactRow.unit,
            FactRow.period_start,
            FactRow.period_end,
            FactRow.fiscal_year,
            FactRow.fiscal_period,
        ).where(FactRow.accession_number == accession_number)
        if concept is not None:
            taxonomy, _, name = concept.partition(":")  # the API names concepts us-gaap:Revenues
            query = query.where(FactRow.taxonomy == taxonomy, FactRow.concept == name)
        if cursor is not None:
            last = _row_id(decode_cursor(cursor, ItemKey).id)
            if last is None:
                raise InvalidInputError(UNUSABLE_CURSOR)
            query = query.where(FactRow.id > last)
        rows = await self._rows(query.order_by(FactRow.id).limit(limit + 1))
        facts = [
            FinancialFact(
                id=str(row.id),
                concept=f"{row.taxonomy}:{row.concept}",
                label=row.label,
                value=float(row.value),
                unit=row.unit,
                period_start=row.period_start,
                period_end=row.period_end,
                fiscal_year=row.fiscal_year,
                fiscal_period=row.fiscal_period,
                accession_number=accession_number,
            )
            for row in rows
        ]
        items, next_cursor = _page(facts, limit, lambda f: ItemKey(id=f.id))
        return FactPage(items=items, next_cursor=next_cursor)

    async def search(
        self,
        q: str,
        limit: int,
        cursor: str | None,
        *,
        cik: int | None = None,
        fiscal_year: int | None = None,
    ) -> SearchPage:
        """Pages of the reranked hits (filinglens_retrieval.search), recomputed for each page."""
        if self._settings is None:
            raise NotImplementedYetError("This backend has no search settings.")
        settings = self._settings
        index = settings.retrieval_embedding_column
        after = decode_cursor(cursor, SearchKey) if cursor is not None else None
        if after is not None and after.index_version != index:
            raise ConflictError(
                "The search index changed since this cursor was made; search again without one."
            )
        fused_order = after is not None and after.degraded
        ranking = await search(
            self._engine,
            q,
            embedding=index,
            scope=Scope(
                ciks=[cik] if cik is not None else None,
                fiscal_years=[fiscal_year] if fiscal_year is not None else None,
            ),
            rerank_model=settings.rerank_model,
            candidates=settings.rerank_candidates,
            max_tokens=settings.rerank_max_tokens,
            timeout_s=settings.rerank_timeout_ms / 1000,
            rerank_hits=not fused_order,
        )
        if after is not None and not after.degraded and ranking.degraded:
            # Fused scores cannot continue a reranked page; the cursor stays good for a retry.
            raise OverloadedError("The reranker is busy; retry this page shortly.", retry_after_s=1)
        hits = ranking.hits
        if after is not None:
            hits = [h for h in hits if (-h.score, h.chunk_id) > (-after.score, after.chunk_id)]
        items, next_cursor = _page(
            [_search_hit(hit) for hit in hits[: limit + 1]],
            limit,
            lambda hit: SearchKey(
                score=hit.score,
                chunk_id=hit.chunk_id,
                index_version=index,
                degraded=ranking.degraded,
            ),
        )
        return SearchPage(items=items, next_cursor=next_cursor, degraded=ranking.degraded)

    async def answer(self, request: AnswerRequest) -> Answer:
        async for event in await self.stream_answer(request):
            if isinstance(event, AnswerCompleted):
                return event.answer
        raise UpstreamError("The answer ended without a result.")

    async def stream_answer(
        self, request: AnswerRequest
    ) -> AsyncIterator[AnswerDelta | AnswerCompleted]:
        if self._answerer is None:
            raise AiUnavailableError("AI is switched off on this server (AI_ENABLED=false).")
        self._answerer.admit()
        return self._answerer.events(request)


def _search_hit(hit: Hit) -> SearchHit:
    folder = hit.accession_number.replace("-", "")
    filing = Filing(
        accession_number=hit.accession_number,
        cik=hit.cik,
        form_type=FormType(hit.form_type),
        filed_on=hit.filed_on,
        period_end=hit.period_end,
        fiscal_year=hit.fiscal_year,
        fiscal_period=FiscalPeriod(hit.fiscal_period),
        url=f"{SEC_ARCHIVES}/{hit.cik}/{folder}/{hit.primary_document}",
    )
    return SearchHit(
        chunk_id=hit.chunk_id, score=hit.score, text=hit.text, section=hit.item, filing=filing
    )
