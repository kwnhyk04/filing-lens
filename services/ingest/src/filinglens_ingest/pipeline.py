"""Ingest pipeline: discover walks a company's EDGAR submissions, fetch downloads each filing.

Both tasks are idempotent: filings are keyed by accession number and job items by (job, filing),
so a redelivered message redoes only what is missing. A task that fails for good writes a
dead_letters row and is rejected into its dead-letter queue (fetch.dlq or discover.dlq). A job
finishes once discovery walked every company and every filing settled: succeeded; partially_failed
(the prompt's completed_with_errors) when a filing succeeded beside a failure; failed otherwise.
Parse, chunk and facts follow fetch in step 4b.
"""

import asyncio
import random
from collections.abc import Awaitable, Callable, Sequence
from datetime import date
from functools import cache, partial
from typing import Any, NoReturn, cast
from uuid import UUID

import structlog
from amqp.exceptions import MessageNacked
from celery import Task, shared_task
from celery.exceptions import Reject
from kombu.exceptions import OperationalError
from redis import Redis
from sqlalchemy import Update, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from filinglens_core import queues
from filinglens_core.errors import TransientError, UpstreamError
from filinglens_core.settings import IngestSettings, load_settings
from filinglens_db import make_engine
from filinglens_db.models import (
    Company,
    DeadLetter,
    Filing,
    FilingStatus,
    IngestJob,
    IngestJobCompany,
    IngestJobItem,
    ItemStatus,
    JobStatus,
)
from filinglens_sec_client import ACCESSION, FILE_NAME, SecClient

MAX_RETRIES = 6
QUEUE_FULL_BACKOFF_MAX_S = 60
NEEDS_FETCH = (FilingStatus.DISCOVERED, FilingStatus.FAILED)  # anything else is at or past fetched
OPEN = (ItemStatus.PENDING, ItemStatus.RUNNING)
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
    """Download a filing's primary document into the SEC cache, then mark the filing fetched.

    Retries go to fetch.retry, which has no length limit, so a full fetch queue cannot drop them.
    """
    job = UUID(job_id) if job_id else None
    settle = partial(_fail_filing, filing_id=filing_id, job_id=job)
    try:
        _run(partial(_fetch, filing_id=filing_id, job_id=job))
    except TransientError as exc:
        if self.request.retries < MAX_RETRIES:
            raise  # autoretry_for queues the next attempt with backoff
        _give_up(self, exc, settle)
    except Exception as exc:
        _give_up(self, exc, settle)


FETCH = cast(Task, fetch)  # Celery's decorators are untyped


@shared_task(**TASK_OPTIONS)
def discover(
    self: Task, job_id: str, cik: int, files: list[str] | None = None, backoffs: int = 0
) -> None:
    """Walk one page of a company's submissions, then queue the next page.

    Records the page's filings, queues fetch for those not yet fetched and, when RabbitMQ refuses a
    publish because the fetch queue is full, queues itself again after a backoff. `files` lists
    the older pages still to walk; None means the main submissions file.
    """
    job = UUID(job_id)
    settle = partial(_fail_company, job_id=job, cik=cik)
    try:
        _discover(self, job, cik, files, backoffs)
    except TransientError as exc:
        if self.request.retries < MAX_RETRIES:
            raise
        _give_up(self, exc, settle)
    except Exception as exc:
        _give_up(self, exc, settle)


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
        _run(partial(_finish_company, job_id=job, cik=cik))


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
                "status": ItemStatus.PENDING if row.status in NEEDS_FETCH else ItemStatus.SKIPPED,
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


async def _finish_company(engine: AsyncEngine, *, job_id: UUID, cik: int) -> None:
    async with engine.begin() as connection:
        change = _company(job_id, cik).values(status=ItemStatus.SUCCEEDED, error=None)
        await _settle(connection, job_id, change)


async def _fetch(engine: AsyncEngine, *, filing_id: int, job_id: UUID | None) -> None:
    async with engine.connect() as connection:
        query = select(
            Filing.cik, Filing.accession_number, Filing.primary_document, Filing.status
        ).where(Filing.id == filing_id)
        filing = (await connection.execute(query)).one_or_none()
    if filing is None:
        log.warning("fetch skipped: no such filing", filing_id=filing_id)
        return
    if filing.status in NEEDS_FETCH:  # otherwise a redelivery or another job got here first
        if job_id is not None:
            async with engine.begin() as connection:
                await connection.execute(
                    _item(job_id, [filing_id])
                    .where(IngestJobItem.status.in_((*OPEN, ItemStatus.FAILED)))
                    .values(status=ItemStatus.RUNNING, attempts=IngestJobItem.attempts + 1)
                )
        sec = _sec()
        await asyncio.to_thread(
            sec.document, filing.cik, filing.accession_number, filing.primary_document
        )
    async with engine.begin() as connection:
        await connection.execute(
            update(Filing)
            .where(Filing.id == filing_id, Filing.status.in_(NEEDS_FETCH))
            .values(status=FilingStatus.FETCHED)
        )
        if job_id is not None:
            change = _item(job_id, [filing_id]).values(status=ItemStatus.SUCCEEDED, error=None)
            await _settle(connection, job_id, change)


async def _fail_filing(
    connection: AsyncConnection, error: str, *, filing_id: int, job_id: UUID | None
) -> None:
    await connection.execute(
        update(Filing)
        .where(Filing.id == filing_id, Filing.status == FilingStatus.DISCOVERED)
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
