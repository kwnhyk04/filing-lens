"""Embedding swap, migrate step: fill chunks.embedding_v2 with model B (docs/migrations.md)."""

import asyncio
from collections.abc import Callable, Sequence

from celery import Task, shared_task
from sqlalchemy import bindparam, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from filinglens_core.settings import EMBEDDING_MODELS, DatabaseSettings, load_settings
from filinglens_db import make_engine
from filinglens_db.models import Chunk
from filinglens_llm import embed

BATCH_SIZE = 256
MODEL = EMBEDDING_MODELS["embedding_v2"]
# Celery rate limits are per worker; this task queues its own next batch, so one runs at a time.
RATE_LIMIT = "60/m"

type Embed = Callable[[Sequence[str], str], list[list[float]]]


async def reembed_batch(engine: AsyncEngine, embed: Embed, after: str | None) -> str | None:
    """Embed the next BATCH_SIZE chunks after chunk id `after` that MODEL has not embedded.

    Returns the batch's last chunk id, where the next batch resumes, or None when none are left.
    """
    query = select(Chunk.id, Chunk.text).where(Chunk.embedding_v2_model.is_distinct_from(MODEL))
    if after is not None:
        query = query.where(Chunk.id > after)
    async with engine.connect() as connection:
        rows = (await connection.execute(query.order_by(Chunk.id).limit(BATCH_SIZE))).all()
    if not rows:
        return None
    vectors = embed([row.text for row in rows], MODEL)  # outside any transaction: it is slow
    statement = (
        update(Chunk)
        .where(Chunk.id == bindparam("chunk_id"))
        .values(embedding_v2=bindparam("vector"), embedding_v2_model=MODEL)
    )
    params = [
        {"chunk_id": row.id, "vector": vector} for row, vector in zip(rows, vectors, strict=True)
    ]
    async with engine.begin() as connection:
        await connection.execute(statement, params)
    return rows[-1].id


async def _reembed_batch(after: str | None) -> str | None:
    engine = make_engine(load_settings(DatabaseSettings))
    try:
        return await reembed_batch(engine, embed, after)
    finally:
        await engine.dispose()


@shared_task(bind=True, rate_limit=RATE_LIMIT)
def reembed(self: Task, after: str | None = None) -> None:
    """Embed one batch, then queue the next. A redelivered message skips rows already done."""
    last = asyncio.run(_reembed_batch(after))
    if last is not None:
        self.delay(last)
