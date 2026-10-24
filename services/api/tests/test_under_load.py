"""Reads stay correct and error-free while rows and the schema change under them (needs Docker).

Keyset pages over 100k chunks skip and repeat nothing while new chunks arrive, and the API serves
reads without a single failure through the whole embedding swap (docs/migrations.md).
"""

import asyncio
import random
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import httpx2
import pytest
from alembic import command
from alembic.config import Config
from seed_fake import seed_fake
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from filinglens_api import schemas
from filinglens_api.backend import DiscoverQueue, LiveBackend
from filinglens_core.settings import EMBEDDING_DIMENSIONS
from filinglens_db.models import Chunk, Company, Filing, Section, chunk_id
from filinglens_ingest.reembed import reembed_batch

pytestmark = pytest.mark.integration
PYPROJECT = Path(__file__).parents[3] / "pyproject.toml"
ACCESSION = "0000000001-26-000001"
CHUNKS = 100_000
SECTIONS = ("1", "1A", "7", "8")
SPAN = 2 * CHUNKS // len(SECTIONS)  # each section's characters; its chunks sit at even offsets
GRAPHQL = {
    "query": "{ filings(first: 3) { edges { node { accessionNumber sections { item }"
    " chunks(first: 20) { edges { node { id text } } }"
    " facts(first: 5) { edges { node { value } } } } } } }"
}


@pytest.fixture
def db(database_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """A fresh database at head, migrated before the test's event loop starts (Alembic runs its
    own)."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(Config(toml_file=PYPROJECT), "head")
    return database_url


async def add_filing_with_chunks(engine: AsyncEngine) -> None:
    """One filing with CHUNKS chunks at the offsets 0, 2, 4, ...; a chunk's text is its offset."""
    async with engine.begin() as connection:
        await connection.execute(insert(Company).values(cik=1, ticker="ONE", name="One Corp"))
        filing_id = await connection.scalar(
            insert(Filing)
            .values(
                accession_number=ACCESSION,
                cik=1,
                form_type="10-K",
                filed_on=date(2026, 2, 1),
                period_end=date(2025, 12, 31),
                primary_document="one.htm",
            )
            .returning(Filing.id)
        )
        sections = [
            {"filing_id": filing_id, "item": item, "title": item}
            | {"char_start": n * SPAN, "char_end": (n + 1) * SPAN}
            for n, item in enumerate(SECTIONS)
        ]
        await connection.execute(insert(Section), sections)
        await connection.execute(
            text(
                "INSERT INTO chunks (id, section_id, char_start, text, token_count)"
                " SELECT encode(sha256(convert_to(concat_ws(':', CAST(:accession AS text),"
                " s.item, o), 'UTF8')), 'hex'), s.id, o, o::text, 1"
                " FROM generate_series(0, CAST(:last AS integer), 2) AS o"
                " JOIN sections AS s ON o >= s.char_start AND o < s.char_end"
            ),
            {"accession": ACCESSION, "last": 2 * (CHUNKS - 1)},
        )


async def page_through(backend: LiveBackend) -> list[schemas.Chunk]:
    """Every chunk of the filing, 100 a page: the API's largest page."""
    seen: list[schemas.Chunk] = []
    cursor: str | None = None
    while True:
        page = await backend.list_chunks(ACCESSION, 100, cursor)
        seen += page.items
        if page.next_cursor is None:
            return seen
        cursor = page.next_cursor


async def insert_until_done(engine: AsyncEngine, reader: asyncio.Task[object]) -> set[str]:
    """Insert chunks at random odd offsets, ahead of the reader and behind it, until it ends."""
    query = select(Section.id, Section.item).order_by(Section.char_start)
    async with engine.connect() as connection:
        sections = (await connection.execute(query)).all()
    rng = random.Random(5)  # noqa: S311 - test data, not security
    inserted: set[str] = set()
    while not reader.done():
        rows = [
            {
                "id": chunk_id(ACCESSION, sections[offset // SPAN].item, offset),
                "section_id": sections[offset // SPAN].id,
                "char_start": offset,
                "text": str(offset),
                "token_count": 1,
            }
            for offset in {2 * rng.randrange(CHUNKS) + 1 for _ in range(10)}
        ]
        async with engine.begin() as connection:
            await connection.execute(insert(Chunk).on_conflict_do_nothing(), rows)
        inserted |= {row["id"] for row in rows}
        await asyncio.sleep(0.05)
    return inserted


async def test_keyset_pages_over_100k_chunks_skip_and_repeat_nothing_while_chunks_arrive(
    db: str,
) -> None:
    engine = create_async_engine(db)
    try:
        await add_filing_with_chunks(engine)
        backend = LiveBackend(engine, DiscoverQueue("amqp://unused:unused@127.0.0.1:1//"))
        reader = asyncio.create_task(page_through(backend))
        inserted = await insert_until_done(engine, reader)
        seen = await reader
    finally:
        await engine.dispose()
    offsets = [int(chunk.text) for chunk in seen]
    assert len(set(offsets)) == len(offsets)  # no chunk twice
    assert offsets == sorted(offsets)  # reading order throughout
    assert set(range(0, 2 * CHUNKS, 2)) <= set(offsets)  # no chunk that was there skipped
    ids = {chunk.id for chunk in seen}
    assert inserted & ids  # inserts ahead of the reader showed up
    assert inserted - ids  # and those behind it did not


@dataclass
class Reads:
    """What the read loop has seen so far; it runs in another thread."""

    done: int = 0
    failures: list[str] = field(default_factory=list[str])


def read_until(url: str, api_key: str, stop: threading.Event, reads: Reads) -> None:
    """Read companies, filings, sections, chunks and facts over REST and GraphQL until `stop`."""
    with httpx2.Client(base_url=url, headers={"X-API-Key": api_key}, timeout=30) as client:
        while not stop.is_set():
            for response in (
                client.get("/v1/companies", params={"limit": 100}),
                client.get("/v1/filings", params={"limit": 100}),
                client.post("/graphql", json=GRAPHQL),
            ):
                reads.done += 1
                if response.status_code != 200 or "errors" in response.json():
                    request = response.request
                    reads.failures.append(
                        f"{request.method} {request.url}: {response.status_code} {response.text}"
                    )


def fake_embed(texts: Sequence[str], model: str) -> list[list[float]]:
    """Model B stand-in: one unit vector for every text serves reads well enough."""
    return [[1.0] + [0.0] * (EMBEDDING_DIMENSIONS["embedding_v2"] - 1) for _ in texts]


async def backfill(url: str) -> None:
    """The reembed task's batches, run inline until every chunk has model B."""
    engine = create_async_engine(url)
    try:
        after = await reembed_batch(engine, fake_embed, None)
        while after is not None:
            after = await reembed_batch(engine, fake_embed, after)
    finally:
        await engine.dispose()


def test_the_api_serves_reads_without_one_failure_through_the_embedding_swap(
    database_url: str,
    env: pytest.MonkeyPatch,
    serve: Callable[[], AbstractContextManager[str]],
    api_key: str,
) -> None:
    env.setenv("DATABASE_URL", database_url)
    config = Config(toml_file=PYPROJECT)
    command.upgrade(config, "0008")  # the dev path: model A only
    size = {"companies": 4, "filings_per_company": 5, "chunks_per_section": 20}
    assert seed_fake(database_url, **size) == 4  # 2,000 chunks, embedded by model A
    reads, stop = Reads(), threading.Event()
    with serve() as url, ThreadPoolExecutor(1) as pool:
        reader = pool.submit(read_until, url, api_key, stop, reads)
        try:
            command.upgrade(config, "0004")  # expand
            before = reads.done
            asyncio.run(backfill(database_url))  # migrate
            during = reads.done - before
            command.upgrade(config, "0005")  # index
            command.upgrade(config, "0006")  # contract; refuses while a chunk lacks model B
        finally:
            stop.set()
            reader.result()  # raises whatever stopped the loop
    assert reads.failures == []
    assert during > 0  # reads went on during the backfill
