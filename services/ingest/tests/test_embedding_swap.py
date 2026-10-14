"""Embedding swap end to end: expand, reembed, index, flag, contract (docs/migrations.md)."""

import asyncio
import math
import random
from collections.abc import Awaitable, Callable, Sequence
from functools import partial
from pathlib import Path
from typing import Any, cast

import pytest
from alembic import command
from alembic.config import Config
from celery import Task
from sqlalchemy import Select, bindparam, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.compiler import SQLCompiler
from sqlalchemy.sql.expression import ClauseElement, Executable

from filinglens_core.settings import EMBEDDING_DIMENSIONS, EMBEDDING_MODELS, EmbeddingColumn
from filinglens_db.models import Vector, chunk_id
from filinglens_ingest import reembed as reembed_module
from filinglens_ingest.reembed import reembed_batch
from filinglens_retrieval import nearest_chunks

pytestmark = pytest.mark.integration
REEMBED = cast(Task, reembed_module.reembed)  # Celery's decorators are untyped
PYPROJECT = Path(__file__).parents[3] / "pyproject.toml"
ACCESSION = "0000000001-25-000001"


class Explain(Executable, ClauseElement):
    """EXPLAIN of a statement, bound parameters included."""

    inherit_cache = False

    def __init__(self, statement: Select[*tuple[Any, ...]]) -> None:
        self.statement = statement


@compiles(Explain)
def _compile_explain(element: Explain, compiler: SQLCompiler, **kw: Any) -> str:
    return "EXPLAIN " + compiler.process(element.statement, **kw)


def unit_vector(seed: str, dimensions: int) -> list[float]:
    rng = random.Random(seed)  # noqa: S311 - test vectors, not security
    vector = [rng.gauss(0, 1) for _ in range(dimensions)]
    norm = math.hypot(*vector)
    return [x / norm for x in vector]


def fake_embed(texts: Sequence[str], model: str) -> list[list[float]]:
    """Model B stand-in: each text gets its own fixed vector."""
    return [unit_vector(text, EMBEDDING_DIMENSIONS["embedding_v2"]) for text in texts]


def run[T](url: str, work: Callable[[AsyncEngine], Awaitable[T]]) -> T:
    async def main() -> T:
        engine = create_async_engine(url)
        try:
            return await work(engine)
        finally:
            await engine.dispose()

    return asyncio.run(main())


async def add_chunks(engine: AsyncEngine, first: int, count: int) -> None:
    """Chunks `first` to `first + count - 1` of one filing section, texts "chunk <n>"."""
    async with engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO companies VALUES (1, 'TEST', 'Test Inc.') ON CONFLICT DO NOTHING")
        )
        await connection.execute(
            text(
                "INSERT INTO filings (accession_number, cik, form_type, filed_on, period_end,"
                " primary_document) VALUES (:a, 1, '10-K', '2025-02-01', '2024-12-31', 'a.htm')"
                " ON CONFLICT DO NOTHING"
            ),
            {"a": ACCESSION},
        )
        await connection.execute(
            text(
                "INSERT INTO sections (filing_id, item, title, char_start, char_end)"
                " VALUES ((SELECT id FROM filings), '7', 'MD&A', 0, 1000) ON CONFLICT DO NOTHING"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO chunks (id, section_id, char_start, text, token_count)"
                " VALUES (:id, (SELECT id FROM sections), :start, :text, 2)"
            ),
            [
                {"id": chunk_id(ACCESSION, "7", n), "start": n, "text": f"chunk {n}"}
                for n in range(first, first + count)
            ],
        )


async def embed_with_model_a(engine: AsyncEngine) -> None:
    statement = text(
        "UPDATE chunks SET embedding = :vector, embedding_model = :model WHERE id = :id"
    ).bindparams(bindparam("vector", type_=Vector(EMBEDDING_DIMENSIONS["embedding"])))
    async with engine.begin() as connection:
        rows = (await connection.execute(text("SELECT id, text FROM chunks"))).all()
        params = [
            {
                "id": row.id,
                "vector": unit_vector(row.text, EMBEDDING_DIMENSIONS["embedding"]),
                "model": EMBEDDING_MODELS["embedding"],
            }
            for row in rows
        ]
        await connection.execute(statement, params)


async def reembed_all(engine: AsyncEngine) -> None:
    after = await reembed_batch(engine, fake_embed, None)
    while after is not None:
        after = await reembed_batch(engine, fake_embed, after)


async def search(engine: AsyncEngine, column: EmbeddingColumn, text_: str) -> tuple[str, str]:
    """The query plan and the nearest chunk id for the vector of `text_` in `column`."""
    statement = nearest_chunks(unit_vector(text_, EMBEDDING_DIMENSIONS[column]), 3, column)
    async with engine.begin() as connection:
        # With a few hundred rows a sequential scan is cheaper. Ruling it out leaves the index,
        # which the planner can use only if the query has the shape the index serves.
        await connection.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join((await connection.execute(Explain(statement))).scalars())
        nearest = (await connection.execute(statement)).scalars().first()
    assert nearest is not None
    return plan, nearest


async def chunk_columns(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as connection:
        found = await connection.run_sync(lambda sync: inspect(sync).get_columns("chunks"))
    return {column["name"] for column in found}


async def alembic_version(engine: AsyncEngine) -> str | None:
    async with engine.connect() as connection:
        return await connection.scalar(text("SELECT version_num FROM alembic_version"))


async def count_model_b(engine: AsyncEngine) -> int:
    async with engine.connect() as connection:
        query = text("SELECT count(*) FROM chunks WHERE embedding_v2_model = :model")
        return await connection.scalar(query, {"model": EMBEDDING_MODELS["embedding_v2"]}) or 0


def test_swap_keeps_search_on_an_hnsw_index_from_expand_to_contract(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(toml_file=PYPROJECT)
    command.upgrade(config, "0003")  # chunks embedded by model A only
    run(database_url, partial(add_chunks, first=0, count=300))
    run(database_url, embed_with_model_a)

    command.upgrade(config, "0004")  # expand
    command.downgrade(config, "0003")  # rolling the expand step back leaves model A intact
    assert "embedding_v2" not in run(database_url, chunk_columns)
    _, nearest = run(database_url, partial(search, column="embedding", text_="chunk 5"))
    assert nearest == chunk_id(ACCESSION, "7", 5)
    command.upgrade(config, "0004")

    # A stray upgrade to head stops at the contract: 0005 (HNSW on embedding_v2) commits, then
    # 0006 refuses to drop model A while chunks lack embedding_v2.
    with pytest.raises(RuntimeError, match="300 chunks have no embedding_v2"):
        command.upgrade(config, "head")
    assert run(database_url, alembic_version) == "0005"
    assert "embedding" in run(database_url, chunk_columns)

    run(database_url, reembed_all)
    columns: tuple[EmbeddingColumn, ...] = ("embedding", "embedding_v2")
    for column in columns:  # RETRIEVAL_EMBEDDING_COLUMN picks the index per query
        plan, nearest = run(database_url, partial(search, column=column, text_="chunk 7"))
        assert f"Index Scan using ix_chunks_{column} on chunks" in plan
        assert nearest == chunk_id(ACCESSION, "7", 7)

    command.upgrade(config, "0006")  # contract
    assert {"embedding", "embedding_model"}.isdisjoint(run(database_url, chunk_columns))
    plan, nearest = run(database_url, partial(search, column="embedding_v2", text_="chunk 9"))
    assert "Index Scan using ix_chunks_embedding_v2 on chunks" in plan
    assert nearest == chunk_id(ACCESSION, "7", 9)


def test_reembed_runs_in_batches_resumes_and_catches_up(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(Config(toml_file=PYPROJECT), "head")
    run(database_url, partial(add_chunks, first=0, count=600))
    batches: list[int] = []

    def embed(texts: Sequence[str], model: str) -> list[list[float]]:
        assert model == EMBEDDING_MODELS["embedding_v2"]
        batches.append(len(texts))
        return fake_embed(texts, model)

    monkeypatch.setattr(reembed_module, "embed", embed)
    monkeypatch.setitem(REEMBED.app.conf, "task_always_eager", True)  # .delay() runs inline
    monkeypatch.setitem(REEMBED.app.conf, "task_eager_propagates", True)

    # A worker that dies after one batch: the task resumes from the cursor that batch returned.
    after = run(database_url, partial(reembed_batch, embed=embed, after=None))
    REEMBED.apply(args=[after])
    assert batches == [256, 256, 88]
    assert run(database_url, count_model_b) == 600

    # A fresh start skips finished rows and catches up a chunk ingested meanwhile.
    run(database_url, partial(add_chunks, first=600, count=1))
    REEMBED.apply()
    assert batches[3:] == [1]
    assert run(database_url, count_model_b) == 601
