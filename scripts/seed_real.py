"""Real data: the latest 10-K of the 30 golden-set companies, through the ingest pipeline.

Checks every CIK and ticker in evals/golden-companies.csv against SEC's company_tickers.json and
stops on any mismatch, showing the rows; it never guesses a fix. Then it finds each company's
latest original 10-K in its submissions and queues one ingest job per company through the API's
own job code (LiveBackend): form 10-K, filed on or after that date. The ingest worker (make dev)
runs discover, fetch, parse, chunk and facts. A company with only a 10-K/A stops the run before any
job, as the contract's FormType has no 10-K/A. Each run uses new Idempotency-Keys, so a rerun goes
through discover again and downloads only what the SEC cache lacks. Prints filings per status,
chunks per filing, facts per company, the SEC requests of the run and its wall time.
Run with `make seed-real`: it calls live SEC and needs SEC_USER_AGENT.
"""

import argparse
import asyncio
import csv
import statistics
import sys
import time
import uuid
from collections import defaultdict
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from filinglens_api.backend import DiscoverQueue, LiveBackend
from filinglens_api.schemas import FormType, IngestJobRequest
from filinglens_core.settings import IngestSettings, load_settings
from filinglens_db import make_engine
from filinglens_db.models import (
    Chunk,
    Company,
    Filing,
    FilingStatus,
    FinancialFact,
    IngestJob,
    IngestJobItem,
    ItemStatus,
    JobStatus,
    Section,
)
from filinglens_sec_client import REQUESTS_KEY, SecClient
from filinglens_telemetry import configure_logging

GOLDEN = Path(__file__).parents[1] / "evals" / "golden-companies.csv"
FINISHED = (JobStatus.SUCCEEDED, JobStatus.PARTIALLY_FAILED, JobStatus.FAILED)
POLL_S = 5


def mismatches(rows: list[dict[str, str]], tickers: dict[str, Any]) -> list[str]:
    """The CSV rows whose ticker SEC does not list under the same CIK, with what SEC lists."""
    cik_of = {entry["ticker"]: int(entry["cik_str"]) for entry in tickers.values()}
    tickers_of: defaultdict[int, list[str]] = defaultdict(list)
    for entry in tickers.values():
        tickers_of[int(entry["cik_str"])].append(entry["ticker"])
    return [
        f"{row['cik']},{row['ticker']},{row['name']}: SEC lists {row['ticker']} under CIK"
        f" {cik_of.get(row['ticker'], 'none')}, and CIK {row['cik']} with tickers"
        f" {tickers_of.get(int(row['cik']), [])}"
        for row in rows
        if cik_of.get(row["ticker"]) != int(row["cik"])
    ]


def latest_10k(sec: SecClient, cik: int) -> tuple[str, str, date] | None:
    """(form, accession number, filing date) of the latest original 10-K, else the latest 10-K/A."""
    main = sec.submissions(cik)

    def pages() -> Iterator[dict[str, Any]]:
        yield main["filings"]["recent"]
        older = sorted(main["filings"].get("files", []), key=lambda f: f["filingTo"], reverse=True)
        for file in older:  # heavy filers list last year's 10-K only in an older file
            yield sec.submissions_file(file["name"])

    amendment = None
    for page in pages():
        filings = zip(page["filingDate"], page["accessionNumber"], page["form"], strict=True)
        for filed, accession, form in sorted(filings, reverse=True):
            if form == "10-K":
                return form, accession, date.fromisoformat(filed)
            if form == "10-K/A" and amendment is None:
                amendment = form, accession, date.fromisoformat(filed)
    return amendment


def sec_requests(redis: Redis) -> dict[str, int]:
    counts = cast(dict[bytes, bytes], redis.hgetall(REQUESTS_KEY))
    return {kind.decode(): int(count) for kind, count in counts.items()}


async def queue_jobs(engine: AsyncEngine, broker_url: str, since: dict[int, date]) -> list[UUID]:
    backend = LiveBackend(engine, DiscoverQueue(broker_url))
    run = uuid.uuid4().hex[:12]
    return [
        await backend.create_ingest_job(
            IngestJobRequest(ciks=[cik], form_types=[FormType.FORM_10K], since=filed),
            f"seed-real:{run}:{cik}",
        )
        for cik, filed in since.items()
    ]


async def wait(engine: AsyncEngine, jobs: list[UUID], timeout_s: float) -> None:
    """Poll the jobs until each one finished; prints their statuses as they change."""
    deadline, shown = time.monotonic() + timeout_s, ""
    query = select(IngestJob.status, func.count()).where(IngestJob.id.in_(jobs))
    while True:
        async with engine.connect() as connection:
            rows = await connection.execute(query.group_by(IngestJob.status))
            counts = {status: count for status, count in rows}
        line = ", ".join(f"{status} {count}" for status, count in sorted(counts.items()))
        if line != shown:
            print(f"jobs: {line}", flush=True)
            shown = line
        if sum(counts.get(status, 0) for status in FINISHED) == len(jobs):
            return
        if time.monotonic() > deadline:
            raise SystemExit(f"Timed out after {timeout_s / 60:.0f} min; jobs: {line}")
        await asyncio.sleep(POLL_S)


async def report(engine: AsyncEngine, jobs: list[UUID], ciks: list[int]) -> bool:
    """Print what the jobs left in the database; True when every filing is parsed."""
    mine = select(IngestJobItem.filing_id).where(IngestJobItem.job_id.in_(jobs))
    async with engine.connect() as connection:
        rows = await connection.execute(
            select(Filing.status, func.count()).where(Filing.id.in_(mine)).group_by(Filing.status)
        )
        statuses = {status: count for status, count in rows}
        rows = await connection.execute(
            select(func.count(Chunk.id))
            .select_from(Filing)
            .outerjoin(Section, Section.filing_id == Filing.id)
            .outerjoin(Chunk, Chunk.section_id == Section.id)
            .where(Filing.id.in_(mine))
            .group_by(Filing.id)
        )
        chunks = sorted(rows.scalars())
        facts = (
            await connection.execute(
                select(Company.ticker, func.count(FinancialFact.id))
                .outerjoin(FinancialFact, FinancialFact.cik == Company.cik)
                .where(Company.cik.in_(ciks))
                .group_by(Company.ticker)
                .order_by(Company.ticker)
            )
        ).all()
        sources = (
            await connection.execute(
                select(Filing.fiscal_source, func.count())
                .where(Filing.id.in_(mine))
                .group_by(Filing.fiscal_source)
            )
        ).all()
        gaps = (
            await connection.execute(
                select(Company.ticker, Filing.accession_number, Filing.missing_items)
                .join(Company, Company.cik == Filing.cik)
                .where(Filing.id.in_(mine), func.cardinality(Filing.missing_items) > 0)
            )
        ).all()
        failures = (
            await connection.execute(
                select(Company.ticker, Filing.accession_number, IngestJobItem.error)
                .join(Filing, Filing.id == IngestJobItem.filing_id)
                .join(Company, Company.cik == Filing.cik)
                .where(IngestJobItem.job_id.in_(jobs), IngestJobItem.status == ItemStatus.FAILED)
            )
        ).all()
    print("filings: " + ", ".join(f"{status} {n}" for status, n in sorted(statuses.items())))
    if chunks:
        print(
            f"chunks per filing: min {chunks[0]}, median {statistics.median(chunks):g},"
            f" max {chunks[-1]} ({sum(chunks):,} in all)"
        )
    print(
        "facts per company: "
        + ", ".join(f"{ticker} {n:,}" for ticker, n in facts)
        + f" ({sum(n for _, n in facts):,} in all)"
    )
    print("fiscal year and period from: " + ", ".join(f"{s} {n}" for s, n in sources))
    print("filings missing a required item: " + ("none" if not gaps else ""))
    for ticker, accession, missing in gaps:
        print(f"  {ticker} {accession}: {', '.join(missing or [])}")
    for ticker, accession, error in failures:
        print(f"failed: {ticker} {accession}: {error}")
    return set(statuses) == {FilingStatus.PARSED} and sum(statuses.values()) == len(jobs)


async def ingest(settings: IngestSettings, since: dict[int, date], timeout_s: float) -> bool:
    engine = make_engine(settings)
    try:
        jobs = await queue_jobs(engine, str(settings.broker_url.get_secret_value()), since)
        print(f"queued {len(jobs)} ingest jobs; waiting for the ingest worker", flush=True)
        await wait(engine, jobs, timeout_s)
        return await report(engine, jobs, list(since))
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest the golden-set companies' latest 10-K.")
    parser.add_argument("--timeout-min", type=float, default=60, help="how long to wait for jobs")
    args = parser.parse_args()
    started = time.perf_counter()
    settings = load_settings(IngestSettings)
    configure_logging("seed-real", settings.log_level)
    redis = Redis.from_url(
        str(settings.redis_url.get_secret_value()), socket_timeout=5, socket_connect_timeout=5
    )
    before = sec_requests(redis)
    sec = SecClient(
        user_agent=settings.sec_user_agent,
        www_url=str(settings.sec_www_url),
        data_url=str(settings.sec_data_url),
        cache_dir=settings.sec_cache_dir,
        redis=redis,
    )
    rows = list(csv.DictReader(GOLDEN.open(encoding="utf-8")))
    if problems := mismatches(rows, sec.company_tickers()):
        lines = "\n".join(problems)
        raise SystemExit(f"CIK and ticker mismatches in {GOLDEN.name}; nothing ingested:\n{lines}")
    since: dict[int, date] = {}
    unsupported: list[str] = []
    for row in rows:
        found = latest_10k(sec, int(row["cik"]))
        if found is not None and found[0] == "10-K":
            since[int(row["cik"])] = found[2]
        else:
            what = f"only {found[0]} {found[1]}" if found else "no 10-K"
            unsupported.append(f"{row['cik']},{row['ticker']},{row['name']}: {what}")
    sec.close()
    if unsupported:
        lines = "\n".join(unsupported)
        raise SystemExit(f"No original 10-K (FormType has no 10-K/A); nothing ingested:\n{lines}")

    complete = asyncio.run(ingest(settings, since, args.timeout_min * 60))
    after = sec_requests(redis)
    made = {kind: after[kind] - before.get(kind, 0) for kind in sorted(after)}
    print(
        f"SEC requests: {sum(made.values())} ("
        + ", ".join(f"{kind} {n}" for kind, n in made.items())
        + f"); documents downloaded: {made.get('document', 0)}"
    )
    print(f"wall time: {time.perf_counter() - started:.0f} s")
    sys.exit(0 if complete else 1)


if __name__ == "__main__":
    main()
