"""Parse filings again: python -m filinglens_ingest.reparse ACCESSION...

Each filing's sections are replaced from today's parser, and its chunks go with them (they
cascade); chunk then runs as in the pipeline, and embed is queued for the embed worker, which
fills RETRIEVAL_EMBEDDING_COLUMN and indexes the filing again. The document comes from the SEC
cache alone, so no request goes to SEC: a filing whose document is not cached stops the run before
that filing changes. A failure after its sections are replaced (chunk, or queueing embed) leaves
it fetched or parsed; running it again finishes it, as chunk ids are fixed. Run it in the ingest
container, which has the settings:
docker compose exec ingest python -m filinglens_ingest.reparse 0001628280-26-008131

--audit changes nothing: it lists every stored filing today's parser would change, with each stored
chunk it would replace (--json FILE keeps the ids). --affected re-parses the filings it lists. A
filing leaves search from its re-parse until embed indexes it again, and offsets are part of chunk
ids, so a change above a chunk gives it a new id even when its text stays.
"""

import argparse
import asyncio
import gzip
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import structlog
from celery import Celery
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from filinglens_core import queues
from filinglens_core.errors import FilingLensError, NotFoundError
from filinglens_core.settings import IngestSettings, load_settings
from filinglens_db import make_engine
from filinglens_db.models import Chunk, Filing, FilingStatus, Section, chunk_id
from filinglens_ingest import chunking, parsing, topology
from filinglens_ingest.pipeline import CHUNKED, _chunk, _store
from filinglens_telemetry import configure_logging

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class Audit:
    """What today's parser would change in a filing's stored chunks."""

    accession_number: str
    kept: int  # stored chunks it would cut the same, by id and text
    changed: list[str]  # stored chunks it would replace
    added: int  # chunks only it would store
    digits: int  # digits it would hold beyond the stored chunks

    @property
    def affected(self) -> bool:
        return bool(self.changed or self.added)


def fresh_chunks(parsed: parsing.Parsed, accession_number: str) -> dict[str, str]:
    """Chunk id to text, as the chunk stage would store them from `parsed`."""
    chunks: dict[str, str] = {}
    for section in parsed.sections:
        text = parsed.text[section.start : section.end]
        for piece in chunking.split(text):
            chunk = chunk_id(accession_number, section.item, section.start + piece.start)
            chunks[chunk] = text[piece.start : piece.end]
    return chunks


def compare(accession_number: str, stored: Mapping[str, str], parsed: parsing.Parsed) -> Audit:
    """A filing's stored chunks against what today's parser cuts from its document."""
    fresh = fresh_chunks(parsed, accession_number)
    changed = [chunk for chunk, text in stored.items() if fresh.get(chunk) != text]

    def digits(chunks: Mapping[str, str]) -> int:
        return sum(c.isdigit() for text in chunks.values() for c in text)

    return Audit(
        accession_number,
        len(stored) - len(changed),
        changed,
        len(fresh.keys() - stored.keys()),
        digits(fresh) - digits(stored),
    )


def _cached(cache_dir: Path, cik: int, accession_number: str, document: str) -> Path:
    folder = accession_number.replace("-", "")
    return cache_dir / "Archives/edgar/data" / str(cik) / folder / f"{document}.gz"  # SecClient's


def _read(path: Path, form_type: str) -> parsing.Parsed:
    return parsing.parse_filing(parsing.decode(gzip.decompress(path.read_bytes())), form_type)


async def audit(engine: AsyncEngine, cache_dir: Path) -> tuple[list[Audit], list[str]]:
    """Every stored filing today's parser would change, and those it cannot check, not cached.
    Reads only."""
    query = (
        select(
            Filing.id, Filing.cik, Filing.accession_number, Filing.primary_document,
            Filing.form_type,
        )
        .where(Filing.status.in_(CHUNKED))
        .order_by(Filing.accession_number)
    )  # fmt: skip
    affected: list[Audit] = []
    uncached: list[str] = []
    async with engine.connect() as connection:
        for filing in (await connection.execute(query)).all():
            path = _cached(cache_dir, filing.cik, filing.accession_number, filing.primary_document)
            if not path.is_file():
                uncached.append(filing.accession_number)
                continue
            rows = select(Chunk.id, Chunk.text).join(Section).where(Section.filing_id == filing.id)
            stored = {row.id: row.text for row in await connection.execute(rows)}
            found = compare(filing.accession_number, stored, _read(path, filing.form_type))
            if found.affected:
                affected.append(found)
    return affected, uncached


async def reparse(engine: AsyncEngine, accession_number: str, cache_dir: Path) -> int:
    """Replace one filing's sections and chunks from its cached document; returns its id."""
    query = select(Filing.id, Filing.cik, Filing.primary_document, Filing.form_type).where(
        Filing.accession_number == accession_number
    )
    async with engine.connect() as connection:
        filing = (await connection.execute(query)).one_or_none()
    if filing is None:
        raise NotFoundError(f"No filing {accession_number}.")
    cached = _cached(cache_dir, filing.cik, accession_number, filing.primary_document)
    if not cached.is_file():
        raise FilingLensError(
            f"{accession_number} is not in the SEC cache; reparse asks SEC nothing."
        )
    parsed = _read(cached, filing.form_type)
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


def report(affected: Sequence[Audit], uncached: Sequence[str]) -> None:
    """The audit's table and totals, then the filings it could not check."""
    for found in affected:
        print(
            f"{found.accession_number}  chunks replaced {len(found.changed):>4}"
            f"  added {found.added:>4}  unchanged {found.kept:>4}  digits {found.digits:+,}"
        )
    print(
        f"{len(affected)} filings affected: {sum(len(a.changed) for a in affected)} stored chunks"
        f" replaced, {sum(a.added for a in affected)} added, {sum(a.digits for a in affected):+,}"
        " digits."
    )
    if uncached:
        print(f"Not in the SEC cache, not checked: {' '.join(uncached)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse filings again from the SEC cache.")
    parser.add_argument("accessions", nargs="*", metavar="ACCESSION")
    parser.add_argument("--audit", action="store_true", help="list what would change; change none")
    parser.add_argument("--json", type=Path, help="with --audit: write every chunk id to this file")
    parser.add_argument("--affected", action="store_true", help="re-parse what --audit lists")
    args = parser.parse_args()
    if not (args.accessions or args.audit or args.affected):
        parser.error("name a filing, or use --audit or --affected")
    settings = load_settings(IngestSettings)
    configure_logging("reparse", settings.log_level)
    broker_url = str(settings.broker_url.get_secret_value())

    async def run() -> None:
        engine = make_engine(settings)
        try:
            accessions = list(args.accessions)
            if args.audit or args.affected:
                affected, uncached = await audit(engine, settings.sec_cache_dir)
                report(affected, uncached)
                if args.json:
                    rows = [asdict(found) for found in affected]
                    args.json.write_text(json.dumps(rows, indent=1), encoding="utf-8")
                if args.audit:
                    return
                accessions = [found.accession_number for found in affected]
            for accession in accessions:  # each one done, embed queued, before the next
                filing_id = await reparse(engine, accession, settings.sec_cache_dir)
                queue_embed(broker_url, [filing_id])
                log.info("filing parsed again; embed queued", accession_number=accession)
        finally:
            await engine.dispose()

    asyncio.run(run())


if __name__ == "__main__":
    main()
