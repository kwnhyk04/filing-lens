"""Parse filings again: python -m filinglens_ingest.reparse ACCESSION...

Each filing's sections are replaced from today's parser, and its chunks go with them (they
cascade); chunk then runs as in the pipeline, and embed is queued for the embed worker, which
fills RETRIEVAL_EMBEDDING_COLUMN and indexes the filing again. The document comes from the SEC
cache alone, so no request goes to SEC: a filing whose document is not cached stops the run before
that filing changes. A failure after its sections are replaced (chunk, or queueing embed) leaves
it fetched or parsed; running it again finishes it, as chunk ids are fixed. Run it in the ingest
container, which has the settings:
docker compose exec ingest python -m filinglens_ingest.reparse 0001628280-26-008131
"""

import argparse
import asyncio
import gzip
from collections.abc import Sequence
from pathlib import Path

import structlog
from celery import Celery
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from filinglens_core import queues
from filinglens_core.errors import FilingLensError, NotFoundError
from filinglens_core.settings import IngestSettings, load_settings
from filinglens_db import make_engine
from filinglens_db.models import Filing, FilingStatus, Section
from filinglens_ingest import parsing, topology
from filinglens_ingest.pipeline import _chunk, _store
from filinglens_telemetry import configure_logging

log = structlog.get_logger(__name__)


async def reparse(engine: AsyncEngine, accession_number: str, cache_dir: Path) -> int:
    """Replace one filing's sections and chunks from its cached document; returns its id."""
    query = select(Filing.id, Filing.cik, Filing.primary_document, Filing.form_type).where(
        Filing.accession_number == accession_number
    )
    async with engine.connect() as connection:
        filing = (await connection.execute(query)).one_or_none()
    if filing is None:
        raise NotFoundError(f"No filing {accession_number}.")
    folder, name = accession_number.replace("-", ""), f"{filing.primary_document}.gz"
    cached = cache_dir / "Archives/edgar/data" / str(filing.cik) / folder / name  # SecClient's path
    if not cached.is_file():
        raise FilingLensError(
            f"{accession_number} is not in the SEC cache; reparse asks SEC nothing."
        )
    document = gzip.decompress(cached.read_bytes())
    parsed = parsing.parse_filing(parsing.decode(document), filing.form_type)
    async with engine.begin() as connection:
        await connection.execute(delete(Section).where(Section.filing_id == filing.id))
        stage = update(Filing).where(Filing.id == filing.id).values(status=FilingStatus.FETCHED)
        await connection.execute(stage)
        await _store(connection, filing.id, parsed)
    await _chunk(engine, filing_id=filing.id, job_id=None)
    return filing.id


def queue_embed(broker_url: str, filing_ids: Sequence[int]) -> None:
    """Queue embed for each filing, with publisher confirms, where the embed worker reads it."""
    app = Celery("filinglens_reparse", broker=broker_url, set_as_current=False)
    app.conf.update(broker_transport_options={"confirm_publish": True}, broker_connection_timeout=5)
    for filing_id in filing_ids:
        queue = topology.WORK_QUEUES[queues.EMBED]
        app.send_task(queues.EMBED_TASK, args=[filing_id], queue=queue, confirm_timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse filings again from the SEC cache.")
    parser.add_argument("accessions", nargs="+", metavar="ACCESSION")
    args = parser.parse_args()
    settings = load_settings(IngestSettings)
    configure_logging("reparse", settings.log_level)
    broker_url = str(settings.broker_url.get_secret_value())

    async def run() -> None:
        engine = make_engine(settings)
        try:
            for accession in args.accessions:  # each one done, embed queued, before the next
                filing_id = await reparse(engine, accession, settings.sec_cache_dir)
                queue_embed(broker_url, [filing_id])
                log.info("filing parsed again; embed queued", accession_number=accession)
        finally:
            await engine.dispose()

    asyncio.run(run())


if __name__ == "__main__":
    main()
