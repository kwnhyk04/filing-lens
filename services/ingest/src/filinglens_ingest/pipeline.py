"""Ingest pipeline: discover, fetch, parse, chunk and embed each filing; facts once per company.

discover walks a company's EDGAR submissions and records the job's filings; fetch downloads each
one into the SEC cache; parse splits it into item sections; chunk cuts those into chunks and marks
the filing parsed; embed fills RETRIEVAL_EMBEDDING_COLUMN and marks it embedded, or indexed once
its fiscal year is known. Once discovery has walked every page, facts loads the company's XBRL
facts, sets its filings' fiscal year and period, and indexes the embedded ones. A stage that finds
its work done passes the filing on, so a new job carries a parsed filing on to embed. Every task is
idempotent: filings are keyed by accession number, sections by (filing, item), chunks by
chunk_id(), facts by their fact key and job items by (job, filing), so a redelivered message redoes
only what is missing. A task that fails for good writes a dead_letters row and is rejected into its
dead-letter queue (<queue>.dlq). A job item succeeds once its filing is embedded, a job company once
its facts are loaded; one bad filing fails only its item. A job finishes once every company and
filing settled: succeeded; partially_failed (the prompt's completed_with_errors) when a filing
succeeded beside a failure; failed otherwise.
"""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import date
from functools import cache, partial
from itertools import batched
from typing import Any, NoReturn, cast
from uuid import UUID

import structlog
from amqp.exceptions import MessageNacked
from celery import Task, shared_task
from celery.exceptions import Reject
from kombu.exceptions import OperationalError
from redis import Redis
from sqlalchemy import (
    String,
    TableClause,
    Update,
    and_,
    bindparam,
    case,
    column,
    func,
    literal,
    select,
    table,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from filinglens_core import queues
from filinglens_core.errors import FilingLensError, NotFoundError, TransientError, UpstreamError
from filinglens_core.settings import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODELS,
    EmbeddingColumn,
    IngestSettings,
    load_settings,
)
from filinglens_db import make_engine
from filinglens_db.models import (
    Chunk,
    Company,
    DeadLetter,
    Filing,
    FilingStatus,
    FinancialFact,
    FiscalSource,
    IngestJob,
    IngestJobCompany,
    IngestJobItem,
    ItemStatus,
    JobStatus,
    Section,
    Vector,
    chunk_id,
)
from filinglens_ingest import chunking, companyfacts, parsing
from filinglens_llm import embed as embed_texts
from filinglens_sec_client import ACCESSION, FILE_NAME, LimiterUnavailableError, SecClient

MAX_RETRIES = 6
QUEUE_FULL_BACKOFF_MAX_S = 60
LIMITER_PAUSE_S = 30  # without Redis no SEC request is allowed, so tasks check back this often
NEEDS_FETCH = (FilingStatus.DISCOVERED, FilingStatus.FAILED)  # anything else is at or past fetched
DONE = (FilingStatus.EMBEDDED, FilingStatus.INDEXED)  # vectors stored: a new job skips the filing
CHUNKED = (FilingStatus.PARSED, *DONE)  # sections and chunks stored
EMBED_BATCH = 64  # chunks per model call and per transaction
EMBED_PER_RUN = 512  # then embed queues itself again, well inside the 300 s task time limit
OPEN = (ItemStatus.PENDING, ItemStatus.RUNNING)
ROWS_PER_INSERT = 5_000
COLUMNS = ("accessionNumber", "filingDate", "reportDate", "form", "primaryDocument")
TASK_OPTIONS: dict[str, Any] = {
    "bind": True,
    "acks_late": True,
    "reject_on_worker_lost": True,
    "acks_on_failure_or_timeout": False,  # an unexpected failure dead-letters instead of acking
    "autoretry_for": (TransientError,),
    "retry_backoff": True,
    "retry_backoff_max": 300,
    "retry_jitter": True,
    "max_retries": MAX_RETRIES,
}
log = structlog.get_logger(__name__)

type Settle = Callable[[AsyncConnection, str], Awaitable[None]]


@cache
def _settings() -> IngestSettings:
    return load_settings(IngestSettings)


@cache
def _sec() -> SecClient:
    """One client per worker process, made on first use (after the prefork)."""
    settings = _settings()
    redis = Redis.from_url(
        str(settings.redis_url.get_secret_value()), socket_timeout=5, socket_connect_timeout=5
    )
    return SecClient(
        user_agent=settings.sec_user_agent,
        www_url=str(settings.sec_www_url),
        data_url=str(settings.sec_data_url),
        cache_dir=settings.sec_cache_dir,
        redis=redis,
    )


def _run[T](work: Callable[[AsyncEngine], Awaitable[T]]) -> T:
    """Run one database step on its own engine and event loop."""

    async def main() -> T:
        engine = make_engine(_settings())
        try:
            return await work(engine)
        finally:
            await engine.dispose()

    return asyncio.run(main())


@shared_task(**TASK_OPTIONS, retry_kwargs={"queue": queues.FETCH_RETRY})
def fetch(self: Task, filing_id: int, job_id: str | None = None) -> None:
    """Download a filing's primary document into the SEC cache, mark it fetched, queue parse.

    Retries go to fetch.retry, which has no length limit, so a full fetch queue cannot drop them.
    """
    job = UUID(job_id) if job_id else None

    def work() -> None:
        if _run(partial(_fetch, filing_id=filing_id, job_id=job)):
            _queue(PARSE, filing_id, job_id)

    settle = partial(_fail_filing, filing_id=filing_id, job_id=job, stage=FilingStatus.DISCOVERED)
    _attempt(self, work, settle, queues.FETCH_RETRY)


@shared_task(**TASK_OPTIONS)
def parse(self: Task, filing_id: int, job_id: str | None = None) -> None:
    """Split a fetched filing into item sections, then queue chunk."""
    job = UUID(job_id) if job_id else None

    def work() -> None:
        if _run(partial(_parse, filing_id=filing_id, job_id=job)):
            _queue(CHUNK, filing_id, job_id)

    settle = partial(_fail_filing, filing_id=filing_id, job_id=job, stage=FilingStatus.FETCHED)
    _attempt(self, work, settle, queues.PARSE)


@shared_task(**TASK_OPTIONS)
def chunk(self: Task, filing_id: int, job_id: str | None = None) -> None:
    """Cut a filing's sections into chunks and mark it parsed, then queue embed."""
    job = UUID(job_id) if job_id else None

    def work() -> None:
        if _run(partial(_chunk, filing_id=filing_id, job_id=job)):
            _queue(EMBED, filing_id, job_id)

    settle = partial(_fail_filing, filing_id=filing_id, job_id=job, stage=FilingStatus.FETCHED)
    _attempt(self, work, settle, queues.CHUNK)


@shared_task(**TASK_OPTIONS)
def embed(self: Task, filing_id: int, job_id: str | None = None) -> None:
    """Embed the filing's chunks that lack a vector, EMBED_PER_RUN at a time, then settle it."""
    job = UUID(job_id) if job_id else None

    def work() -> None:
        if _run(partial(_embed, filing_id=filing_id, job_id=job)):
            _queue(EMBED, filing_id, job_id)  # chunks are left: the next run picks them up

    settle = partial(_fail_filing, filing_id=filing_id, job_id=job, stage=FilingStatus.PARSED)
    _attempt(self, work, settle, queues.EMBED)


@shared_task(**TASK_OPTIONS)
def facts(self: Task, job_id: str, cik: int) -> None:
    """Load a company's XBRL facts and its filings' fiscal periods, then finish the company."""
    job = UUID(job_id)
    settle = partial(_fail_company, job_id=job, cik=cik)
    _attempt(self, lambda: _run(partial(_facts, job_id=job, cik=cik)), settle, queues.FACTS)


# Celery's decorators are untyped.
FETCH, PARSE, CHUNK, EMBED, FACTS = (
    cast(Task, task) for task in (fetch, parse, chunk, embed, facts)
)


@shared_task(**TASK_OPTIONS)
def discover(
    self: Task, job_id: str, cik: int, files: list[str] | None = None, backoffs: int = 0
) -> None:
    """Walk one page of a company's submissions, then queue the next page, or facts after the last.

    Records the page's filings, queues fetch for those not yet chunked and, when RabbitMQ refuses a
    publish because the fetch queue is full, queues itself again after a backoff. `files` lists
    the older pages still to walk; None means the main submissions file.
    """
    job = UUID(job_id)
    settle = partial(_fail_company, job_id=job, cik=cik)
    _attempt(self, partial(_discover, self, job, cik, files, backoffs), settle, queues.DISCOVER)


def _discover(task: Task, job: UUID, cik: int, files: list[str] | None, backoffs: int) -> None:
    company: dict[str, str] | None = None
    if files is None:
        main = _sec().submissions(cik)
        page, older = main["filings"]["recent"], main["filings"].get("files", [])
        tickers = main.get("tickers") or [""]
        company = {"name": str(main.get("name") or cik)[:200], "ticker": str(tickers[0])[:10]}
    else:
        page, older = _sec().submissions_file(files[0]), []
    since, pending = _run(partial(_record_page, job_id=job, cik=cik, page=page, company=company))
    queued = _queue_fetches(job, pending)
    if queued:
        _run(partial(_mark_queued, job_id=job, filing_ids=queued))
    if len(queued) < len(pending):  # the fetch queue is full
        delay = random.uniform(0, min(QUEUE_FULL_BACKOFF_MAX_S, 2**backoffs))  # noqa: S311 - jitter
        log.info(
            "fetch queue full, discover backs off",
            job_id=str(job),
            cik=cik,
            waiting=len(pending) - len(queued),
            delay_s=round(delay, 1),
        )
        task.apply_async((str(job), cik, files), {"backoffs": backoffs + 1}, countdown=delay)
        return
    # Older files whose newest filing predates the job's start date hold nothing it wants.
    remaining = files[1:] if files else [f["name"] for f in older if f["filingTo"] >= str(since)]
    if remaining:
        task.apply_async((str(job), cik, remaining))
    else:
        _queue(FACTS, str(job), cik)  # facts settles the company


def _queue_fetches(job: UUID, filing_ids: Sequence[int]) -> list[int]:
    """Queue fetch for each filing until RabbitMQ refuses one; returns the filings queued."""
    queued: list[int] = []
    for filing_id in filing_ids:
        try:
            FETCH.apply_async((filing_id, str(job)), retry=False)  # confirmed, or nacked when full
        except OperationalError as exc:  # Celery wraps the broker's errors, a nack included
            if isinstance(exc.__cause__, MessageNacked):
                break
            raise UpstreamError("RabbitMQ did not take the fetch message.") from exc
        queued.append(filing_id)
    return queued


def _queue(task: Task, *args: object) -> None:
    """Queue the next stage; a broker failure is transient, so the calling task retries."""
    try:
        task.apply_async(args, retry=False)
    except OperationalError as exc:
        raise UpstreamError(f"RabbitMQ did not take the {task.name} message.") from exc


def _attempt(task: Task, work: Callable[[], None], settle: Settle, queue: str) -> None:
    """Run a task's work: pause without Redis, retry transient errors, dead-letter the rest."""
    try:
        work()
    except LimiterUnavailableError:
        _pause(task, queue)
    except TransientError as exc:
        if task.request.retries < MAX_RETRIES:
            raise  # autoretry_for queues the next attempt with backoff
        _give_up(task, exc, settle)
    except Exception as exc:
        _give_up(task, exc, settle)


def _pause(task: Task, queue: str) -> None:
    """Send the task again after a pause, with its retry count unchanged: nothing reached SEC."""
    delay = LIMITER_PAUSE_S * random.uniform(0.5, 1.5)  # noqa: S311 - jitter
    log.warning(
        "SEC rate limiter unavailable, task paused",
        task=task.name,
        task_id=task.request.id,
        delay_s=round(delay, 1),
    )
    task.apply_async(
        task.request.args,
        task.request.kwargs,
        task_id=task.request.id,
        countdown=delay,
        retries=task.request.retries,
        queue=queue,
    )


def _give_up(task: Task, exc: Exception, settle: Settle) -> NoReturn:
    """Record a final failure, then reject the message into its dead-letter queue."""
    error = f"{type(exc).__name__}: {exc}"
    log.error("task failed for good", task=task.name, task_id=task.request.id, error=error)
    payload = {"args": list(task.request.args or ()), "kwargs": dict(task.request.kwargs or {})}
    _run(
        partial(
            _record_failure,
            task_id=task.request.id,
            task_name=str(task.name),
            payload=payload,
            error=error,
            settle=settle,
        )
    )
    raise Reject(error, requeue=False) from exc


def _filings(page: dict[str, Any], cik: int, forms: set[str], since: date) -> list[dict[str, Any]]:
    """The page's filings that the job wants, as filings rows; SEC lists them column by column."""
    rows: list[dict[str, Any]] = []
    for accession, filed, period, form, document in zip(*(page[c] for c in COLUMNS), strict=True):
        if form not in forms or not period or date.fromisoformat(filed) < since:
            continue
        if not ACCESSION.fullmatch(accession) or not FILE_NAME.fullmatch(document):
            log.warning("filing skipped: unexpected name", accession=accession, document=document)
            continue
        rows.append(
            {
                "accession_number": accession,
                "cik": cik,
                "form_type": form,
                "filed_on": date.fromisoformat(filed),
                "period_end": date.fromisoformat(period),
                "primary_document": document,
            }
        )
    return rows


async def _record_page(
    engine: AsyncEngine,
    *,
    job_id: UUID,
    cik: int,
    page: dict[str, Any],
    company: dict[str, str] | None,
) -> tuple[date, list[int]]:
    """Store the page's filings and job items; returns the job's start date and filings to queue."""
    async with engine.begin() as connection:
        query = select(IngestJob.request).where(IngestJob.id == job_id)
        request = (await connection.execute(query)).scalar_one()
        forms, since = set(request["form_types"]), date.fromisoformat(request["since"])
        await connection.execute(
            update(IngestJob)
            .where(IngestJob.id == job_id, IngestJob.status == JobStatus.QUEUED)
            .values(status=JobStatus.RUNNING)
        )
        await connection.execute(
            _company(job_id, cik)
            .where(IngestJobCompany.status == ItemStatus.PENDING)
            .values(status=ItemStatus.RUNNING)
        )
        if company is not None:
            await connection.execute(
                insert(Company).values(cik=cik, **company).on_conflict_do_nothing()
            )
        filings = _filings(page, cik, forms, since)
        if not filings:
            return since, []
        await connection.execute(
            insert(Filing)
            .values(filings)
            .on_conflict_do_nothing(index_elements=["accession_number"])
        )
        accessions = [filing["accession_number"] for filing in filings]
        query = select(Filing.id, Filing.status).where(Filing.accession_number.in_(accessions))
        found = (await connection.execute(query)).all()
        items = [
            {
                "job_id": job_id,
                "filing_id": row.id,
                "status": ItemStatus.SKIPPED if row.status in DONE else ItemStatus.PENDING,
            }
            for row in found
        ]
        await connection.execute(
            insert(IngestJobItem)
            .values(items)
            .on_conflict_do_nothing(index_elements=["job_id", "filing_id"])
        )
        pending = await connection.execute(
            select(IngestJobItem.filing_id)
            .where(
                IngestJobItem.job_id == job_id,
                IngestJobItem.status == ItemStatus.PENDING,
                IngestJobItem.filing_id.in_([row.id for row in found]),
            )
            .order_by(IngestJobItem.filing_id)
        )
        return since, list(pending.scalars())


async def _mark_queued(engine: AsyncEngine, *, job_id: UUID, filing_ids: list[int]) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            _item(job_id, filing_ids)
            .where(IngestJobItem.status == ItemStatus.PENDING)
            .values(status=ItemStatus.RUNNING)
        )


async def _fetch(engine: AsyncEngine, *, filing_id: int, job_id: UUID | None) -> bool:
    """Download the document unless the filing is past that; False when the filing is gone."""
    async with engine.connect() as connection:
        query = select(
            Filing.cik, Filing.accession_number, Filing.primary_document, Filing.status
        ).where(Filing.id == filing_id)
        filing = (await connection.execute(query)).one_or_none()
    if filing is None:
        log.warning("fetch skipped: no such filing", filing_id=filing_id)
        return False
    if filing.status not in NEEDS_FETCH:  # a redelivery, or another job got here first
        return True
    if job_id is not None:  # a replayed item is in progress again
        await _reopen(engine, job_id, filing_id)
    try:
        await asyncio.to_thread(
            _sec().document, filing.cik, filing.accession_number, filing.primary_document
        )
    except LimiterUnavailableError:
        raise  # a pause: nothing went to SEC, so it is no attempt
    except Exception:
        await _count_attempt(engine, job_id, filing_id)
        raise
    async with engine.begin() as connection:
        await connection.execute(
            update(Filing)
            .where(Filing.id == filing_id, Filing.status.in_(NEEDS_FETCH))
            .values(status=FilingStatus.FETCHED)
        )
        if job_id is not None:
            change = _item(job_id, [filing_id]).values(
                attempts=IngestJobItem.attempts + 1, error=None
            )
            await connection.execute(change)
    return True


async def _parse(engine: AsyncEngine, *, filing_id: int, job_id: UUID | None) -> bool:
    """Store the filing's sections and missing items; returns whether chunk should follow."""
    async with engine.connect() as connection:
        query = select(
            Filing.cik,
            Filing.accession_number,
            Filing.primary_document,
            Filing.form_type,
            Filing.status,
        ).where(Filing.id == filing_id)
        filing = (await connection.execute(query)).one_or_none()
    if filing is None:
        log.warning("parse skipped: no such filing", filing_id=filing_id)
        return False
    if filing.status in CHUNKED:  # a redelivery or an earlier job: chunk passes it on to embed
        return True
    if job_id is not None:  # a replayed item is in progress again
        await _reopen(engine, job_id, filing_id)
    document = await asyncio.to_thread(  # the cached copy, unless the cache lost it
        _sec().document, filing.cik, filing.accession_number, filing.primary_document
    )
    parsed = parsing.parse_filing(parsing.decode(document), filing.form_type)
    sections = [
        {
            "filing_id": filing_id,
            "item": section.item,
            "title": section.title,
            "char_start": section.start,
            "char_end": section.end,
            "text": parsed.text[section.start : section.end],
        }
        for section in parsed.sections
    ]
    async with engine.begin() as connection:
        await connection.execute(
            insert(Section)
            .values(sections)
            .on_conflict_do_nothing(index_elements=["filing_id", "item"])
        )
        await connection.execute(
            update(Filing).where(Filing.id == filing_id).values(missing_items=parsed.missing)
        )
    if parsed.missing:
        log.warning(
            "filing lacks required items",
            accession_number=filing.accession_number,
            missing=parsed.missing,
        )
    return True


async def _chunk(engine: AsyncEngine, *, filing_id: int, job_id: UUID | None) -> bool:
    """Store the filing's chunks and mark it parsed; returns whether embed should follow."""
    async with engine.connect() as connection:
        query = select(Filing.accession_number, Filing.status).where(Filing.id == filing_id)
        filing = (await connection.execute(query)).one_or_none()
        query = select(Section.id, Section.item, Section.char_start, Section.text).where(
            Section.filing_id == filing_id
        )
        sections = (await connection.execute(query)).all()
    if filing is None:
        log.warning("chunk skipped: no such filing", filing_id=filing_id)
        return False
    if filing.status in CHUNKED:  # a redelivery or an earlier job
        return True
    if not any(section.text for section in sections):
        raise FilingLensError(f"Filing {filing.accession_number} has no section text to chunk.")
    rows = [
        {
            "id": chunk_id(filing.accession_number, section.item, section.char_start + piece.start),
            "section_id": section.id,
            "char_start": section.char_start + piece.start,
            "text": section.text[piece.start : piece.end],
            "token_count": piece.token_count,
        }
        for section in sections
        if section.text
        for piece in chunking.split(section.text)
    ]
    async with engine.begin() as connection:
        for batch in batched(rows, ROWS_PER_INSERT):
            await connection.execute(insert(Chunk).on_conflict_do_nothing(), list(batch))
        await connection.execute(
            update(Filing)
            .where(Filing.id == filing_id, Filing.status.not_in(CHUNKED))
            .values(status=FilingStatus.PARSED)
        )
    return True


def _vectors(name: EmbeddingColumn) -> TableClause:
    """chunks with the embedding column `name` and its model column, at any revision."""
    return table(
        "chunks",
        column("id", String),
        column("section_id"),
        column("text", String),
        column(name, Vector(EMBEDDING_DIMENSIONS[name])),
        column(f"{name}_model", String),
    )


async def _embed(engine: AsyncEngine, *, filing_id: int, job_id: UUID | None) -> bool:
    """Embed up to EMBED_PER_RUN of the filing's chunks without a vector; True when more are left.

    Once none is left, the filing is indexed if its fiscal year is known (facts sets it), else
    embedded, and its job item succeeds.
    """
    name = _settings().retrieval_embedding_column
    model, chunks = EMBEDDING_MODELS[name], _vectors(name)
    query = (
        select(chunks.c.id, chunks.c.text)
        .join(Section, Section.id == chunks.c.section_id)
        .where(Section.filing_id == filing_id, chunks.c[name].is_(None))
        .order_by(chunks.c.id)
        .limit(EMBED_PER_RUN + 1)
    )
    any_chunk = (
        select(chunks.c.id)
        .join(Section, Section.id == chunks.c.section_id)
        .where(Section.filing_id == filing_id)
        .limit(1)
    )
    async with engine.connect() as connection:
        status = await connection.scalar(select(Filing.status).where(Filing.id == filing_id))
        stored = await connection.scalar(any_chunk)
        rows = (await connection.execute(query)).all()
    if status is None:
        log.warning("embed skipped: no such filing", filing_id=filing_id)
        return False
    if stored is None:
        raise FilingLensError(f"Filing {filing_id} has no chunks to embed.")
    if job_id is not None:  # a replayed item is in progress again
        await _reopen(engine, job_id, filing_id)
    statement = (
        update(chunks)
        .where(chunks.c.id == bindparam("chunk_id"))
        .values({name: bindparam("vector"), f"{name}_model": model})
    )
    started = time.perf_counter()
    for batch in batched(rows[:EMBED_PER_RUN], EMBED_BATCH):
        vectors = await asyncio.to_thread(embed_texts, [row.text for row in batch], model)
        params = [
            {"chunk_id": row.id, "vector": vector}
            for row, vector in zip(batch, vectors, strict=True)
        ]
        async with engine.begin() as connection:
            await connection.execute(statement, params)
    if rows:
        log.info(
            "chunks embedded",
            filing_id=filing_id,
            chunks=len(rows[:EMBED_PER_RUN]),
            seconds=round(time.perf_counter() - started, 2),
            column=name,
        )
    if len(rows) > EMBED_PER_RUN:
        return True
    known = and_(Filing.fiscal_year.is_not(None), Filing.fiscal_period.is_not(None))
    status = Filing.status.type  # typed literals: a bare CASE of parameters is text to Postgres
    searchable = case(
        (known, literal(FilingStatus.INDEXED, status)),
        else_=literal(FilingStatus.EMBEDDED, status),
    )
    async with engine.begin() as connection:
        await connection.execute(
            update(Filing)
            .where(Filing.id == filing_id, Filing.status.not_in(DONE))
            .values(status=searchable)
        )
        if job_id is not None:
            change = _item(job_id, [filing_id]).values(status=ItemStatus.SUCCEEDED, error=None)
            await _settle(connection, job_id, change)
    return False


async def _facts(engine: AsyncEngine, *, job_id: UUID, cik: int) -> None:
    sec = _sec()
    try:
        data = await asyncio.to_thread(sec.companyfacts, cik)
    except NotFoundError:
        data = {}  # SEC has no XBRL facts for this company
    fiscal = companyfacts.fiscal_by_accession(data)
    async with engine.connect() as connection:
        query = select(
            Filing.id, Filing.accession_number, Filing.form_type, Filing.period_end
        ).where(Filing.cik == cik)
        filings = (await connection.execute(query)).all()
    year_end: str | None = None
    if any(filing.accession_number not in fiscal for filing in filings):
        year_end = (await asyncio.to_thread(sec.submissions, cik)).get("fiscalYearEnd")
    async with engine.begin() as connection:
        for batch in batched(companyfacts.fact_rows(data, cik), ROWS_PER_INSERT):
            await connection.execute(insert(FinancialFact).on_conflict_do_nothing(), list(batch))
        for filing in filings:
            if filing.accession_number in fiscal:
                (year, period), source = fiscal[filing.accession_number], FiscalSource.COMPANYFACTS
            else:
                year, period = companyfacts.fiscal_from_period(
                    filing.form_type, filing.period_end, year_end
                )
                source = FiscalSource.PERIOD_OF_REPORT
            await connection.execute(
                update(Filing)
                .where(Filing.id == filing.id)
                .values(fiscal_year=year, fiscal_period=period, fiscal_source=source)
            )
        # Filings embedded before their fiscal period was known become searchable now.
        await connection.execute(
            update(Filing)
            .where(Filing.cik == cik, Filing.status == FilingStatus.EMBEDDED)
            .where(Filing.fiscal_year.is_not(None), Filing.fiscal_period.is_not(None))
            .values(status=FilingStatus.INDEXED)
        )
        change = _company(job_id, cik).values(status=ItemStatus.SUCCEEDED, error=None)
        await _settle(connection, job_id, change)


async def _reopen(engine: AsyncEngine, job_id: UUID, filing_id: int) -> None:
    """Put a failed item back in progress: its message was replayed from a dead-letter queue."""
    async with engine.begin() as connection:
        await connection.execute(
            _item(job_id, [filing_id])
            .where(IngestJobItem.status.in_((ItemStatus.PENDING, ItemStatus.FAILED)))
            .values(status=ItemStatus.RUNNING)
        )


async def _count_attempt(engine: AsyncEngine, job_id: UUID | None, filing_id: int) -> None:
    if job_id is not None:
        async with engine.begin() as connection:
            change = _item(job_id, [filing_id]).values(attempts=IngestJobItem.attempts + 1)
            await connection.execute(change)


async def _fail_filing(
    connection: AsyncConnection,
    error: str,
    *,
    filing_id: int,
    job_id: UUID | None,
    stage: FilingStatus,
) -> None:
    """Fail the filing, if it is still at the stage that failed, and its job item."""
    await connection.execute(
        update(Filing)
        .where(Filing.id == filing_id, Filing.status == stage)
        .values(status=FilingStatus.FAILED)
    )
    if job_id is not None:
        change = _item(job_id, [filing_id]).values(status=ItemStatus.FAILED, error=error)
        await _settle(connection, job_id, change)


async def _fail_company(connection: AsyncConnection, error: str, *, job_id: UUID, cik: int) -> None:
    change = _company(job_id, cik).values(status=ItemStatus.FAILED, error=error)
    await _settle(connection, job_id, change)


async def _record_failure(
    engine: AsyncEngine,
    *,
    task_id: str,
    task_name: str,
    payload: dict[str, Any],
    error: str,
    settle: Settle,
) -> None:
    """Store the dead letter (once per task id) and settle the job in one transaction."""
    statement = insert(DeadLetter).values(
        task_id=task_id, task_name=task_name, payload=payload, error=error
    )
    statement = statement.on_conflict_do_update(
        index_elements=["task_id"],
        set_={"error": statement.excluded.error, "created_at": func.now()},
    )
    async with engine.begin() as connection:
        await connection.execute(statement)
        await settle(connection, error)


def _item(job_id: UUID, filing_ids: list[int]) -> Update:
    return update(IngestJobItem).where(
        IngestJobItem.job_id == job_id, IngestJobItem.filing_id.in_(filing_ids)
    )


def _company(job_id: UUID, cik: int) -> Update:
    return update(IngestJobCompany).where(
        IngestJobCompany.job_id == job_id, IngestJobCompany.cik == cik
    )


async def _settle(connection: AsyncConnection, job_id: UUID, change: Update) -> None:
    """Apply a terminal change under the job's row lock, then close the job if nothing is open.

    Every terminal change takes the lock first, so the last one to commit sees all the others.
    """
    await connection.execute(select(IngestJob.id).where(IngestJob.id == job_id).with_for_update())
    await connection.execute(change)
    items = await _counts(connection, IngestJobItem, job_id)
    companies = await _counts(connection, IngestJobCompany, job_id)
    if any(items.get(status) or companies.get(status) for status in OPEN):
        return
    failed = items.get(ItemStatus.FAILED, 0) + companies.get(ItemStatus.FAILED, 0)
    done = items.get(ItemStatus.SUCCEEDED, 0) + items.get(ItemStatus.SKIPPED, 0)
    status = (
        JobStatus.SUCCEEDED
        if not failed
        else JobStatus.PARTIALLY_FAILED
        if done
        else JobStatus.FAILED
    )
    await connection.execute(update(IngestJob).where(IngestJob.id == job_id).values(status=status))


async def _counts(
    connection: AsyncConnection, table: type[IngestJobItem] | type[IngestJobCompany], job_id: UUID
) -> dict[ItemStatus, int]:
    query = select(table.status, func.count()).where(table.job_id == job_id).group_by(table.status)
    return {status: count for status, count in await connection.execute(query)}
