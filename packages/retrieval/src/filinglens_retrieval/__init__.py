"""Hybrid search (pgvector + full text), reciprocal rank fusion and cross-encoder reranking."""

import asyncio
import threading
import time
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import Any

import structlog
from opentelemetry import trace
from opentelemetry.trace import StatusCode
from sqlalchemy import Float, Row, Select, String, cast, column, func, select, table, text
from sqlalchemy.dialects.postgresql import TSQUERY, TSVECTOR
from sqlalchemy.ext.asyncio import AsyncEngine

from filinglens_core.settings import EMBEDDING_MODELS, EmbeddingColumn
from filinglens_db.models import Chunk, Filing, FilingStatus, Section, Vector
from filinglens_llm.local import embed, rerank, reranker
from filinglens_telemetry import metrics

RRF_K = 60  # Cormack et al. (2009); a larger k flattens the lead of the top ranks
VECTOR_K = 50  # nearest chunks by embedding
TEXT_K = 50  # best full-text matches
SCORE_DIGITS = 6  # rounded, so a recomputed page compares equal to its cursor
log = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


def reciprocal_rank_fusion(
    rankings: Iterable[Sequence[str]], k: int = RRF_K
) -> list[tuple[str, float]]:
    """Fuse ranked lists of ids (each id at most once per list) into one, best first.

    An id scores the sum of 1 / (k + rank) over the lists that hold it, ranks counting from 1.
    Equal scores go by id, the order search pages in (score descending, then chunk id). The sums
    are exact, so equal scores are equal floats whatever the order of the lists.
    """
    scores: defaultdict[str, Fraction] = defaultdict(Fraction)
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] += Fraction(1, k + rank)
    fused = [(item, float(score)) for item, score in scores.items()]
    return sorted(fused, key=lambda pair: (-pair[1], pair[0]))


@dataclass(frozen=True)
class Scope:
    """Chunks a search may return: those of indexed filings, of these companies and fiscal years."""

    ciks: Sequence[int] | None = None
    fiscal_years: Sequence[int] | None = None


def _scoped[*Ts](query: Select[*Ts], section_id: Any, scope: Scope | None) -> Select[*Ts]:
    """Filter in SQL, before ranking; None leaves the query unscoped (any chunk, indexed or not)."""
    if scope is None:
        return query
    query = (
        query.join(Section, Section.id == section_id)
        .join(Filing, Filing.id == Section.filing_id)
        .where(Filing.status == FilingStatus.INDEXED)
    )
    if scope.ciks is not None:
        query = query.where(Filing.cik.in_(scope.ciks))
    if scope.fiscal_years is not None:
        query = query.where(Filing.fiscal_year.in_(scope.fiscal_years))
    return query


def nearest_chunks(
    vector: Sequence[float], limit: int, embedding: EmbeddingColumn, scope: Scope | None = None
) -> Select[str, float]:
    """Chunk ids nearest to `vector` by cosine distance, served by the HNSW index on `embedding`.

    Callers pass RETRIEVAL_EMBEDDING_COLUMN on every query, so flipping it switches the index.
    """
    chunks = table(
        "chunks", column("id", String), column("section_id"), column(embedding, Vector(len(vector)))
    )
    distance = chunks.c[embedding].op("<=>", return_type=Float())(vector)
    query = select(chunks.c.id, distance.label("distance"))
    return _scoped(query, chunks.c.section_id, scope).order_by(distance).limit(limit)


def matching_chunks(q: str, limit: int, scope: Scope | None = None) -> Select[str, float]:
    """Chunk ids whose text holds any word of `q`, best ts_rank_cd first (GIN index on tsv)."""
    chunks = table("chunks", column("id", String), column("section_id"), column("tsv", TSVECTOR))
    # plainto_tsquery ANDs the words, and a question seldom matches all of them; OR them instead.
    words = cast(
        func.replace(cast(func.plainto_tsquery("english", q), String), " & ", " | "), TSQUERY
    )
    rank = func.ts_rank_cd(chunks.c.tsv, words, type_=Float())
    query = select(chunks.c.id, rank.label("rank")).where(chunks.c.tsv.op("@@")(words))
    return (
        _scoped(query, chunks.c.section_id, scope).order_by(rank.desc(), chunks.c.id).limit(limit)
    )


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    score: float  # cross-encoder relevance, or the RRF score when degraded
    text: str
    item: str
    accession_number: str
    cik: int
    form_type: str
    filed_on: date
    period_end: date
    fiscal_year: int
    fiscal_period: str
    primary_document: str


@dataclass(frozen=True)
class Ranking:
    hits: list[Hit]  # score descending, then chunk id
    degraded: bool  # the reranker timed out or was skipped, so hits keep their fused order
    similarity: float | None  # cosine similarity of the nearest chunk, if any
    timings_ms: dict[str, float]


async def search(
    engine: AsyncEngine,
    q: str,
    *,
    embedding: EmbeddingColumn,
    scope: Scope,
    rerank_model: str,
    candidates: int,
    max_tokens: int,
    timeout_s: float,
    rerank_hits: bool = True,
) -> Ranking:
    """Vector top VECTOR_K and full-text top TEXT_K within `scope`, fused by RRF; the fused top
    `candidates` reranked by the cross-encoder, or left in fused order (degraded) when it misses
    `timeout_s` or `rerank_hits` is False."""
    timings: dict[str, float] = {}
    started = clock = time.perf_counter()
    clock_ns = time.time_ns()

    def lap(stage: str) -> None:
        """A finished phase: its time, its histogram and a span under the search's."""
        nonlocal clock, clock_ns
        now, now_ns = time.perf_counter(), time.time_ns()
        timings[stage] = round((now - clock) * 1000, 1)
        phase = stage.removesuffix("_ms")
        tracer.start_span(phase, start_time=clock_ns).end(end_time=now_ns)
        metrics.SEARCH.record(now - clock, {"phase": phase})
        clock, clock_ns = now, now_ns

    # Not the query: SQL errors quote their parameters, so neither the exception nor its message.
    with tracer.start_as_current_span(
        "search", record_exception=False, set_status_on_exception=False
    ) as span:
        try:
            [vector] = await asyncio.to_thread(embed, [q], EMBEDDING_MODELS[embedding], query=True)
            lap("embed_ms")
            nearest, matching = await asyncio.gather(
                _nearest(engine, vector, embedding, scope),
                _ids(engine, matching_chunks(q, TEXT_K, scope)),
            )
            lap("sql_ms")
            fused = reciprocal_rank_fusion([[row.id for row in nearest], matching])[:candidates]
            rows = await _rows(engine, [chunk_id for chunk_id, _ in fused])
            lap("load_ms")
            scores = [score for _, score in fused]
            reranked = None
            if rerank_hits and fused:
                texts = [rows[chunk_id].text for chunk_id, _ in fused]
                reranked = await _rerank(q, texts, rerank_model, max_tokens, timeout_s)
                lap("rerank_ms")
        except Exception as exc:
            span.set_status(StatusCode.ERROR)
            span.set_attribute("error.type", type(exc).__qualname__)
            raise
        hits = sorted(
            (
                _hit(rows[chunk_id], score)
                for (chunk_id, _), score in zip(fused, reranked or scores, strict=True)
            ),
            key=lambda hit: (-hit.score, hit.chunk_id),
        )
        degraded = bool(fused) and reranked is None
        span.set_attributes(
            {"filinglens.search.degraded": degraded, "filinglens.search.hits": len(hits)}
        )
    metrics.SEARCH.record(time.perf_counter() - started, {"phase": "total"})
    log.info(
        "search",
        vector_hits=len(nearest),
        text_hits=len(matching),
        fused=len(fused),
        degraded=degraded,
        **timings,
    )
    similarity = 1 - nearest[0].distance if nearest else None
    return Ranking(hits=hits, degraded=degraded, similarity=similarity, timings_ms=timings)


async def _nearest(
    engine: AsyncEngine, vector: Sequence[float], embedding: EmbeddingColumn, scope: Scope
) -> list[Row[str, float]]:
    async with engine.begin() as connection:
        # pgvector returns at most ef_search rows (default 40) per scan; the iterative scan keeps
        # going when the scope filters some out. Its relaxed order is sorted again below.
        await connection.execute(text("SET LOCAL hnsw.ef_search = 100"))
        await connection.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
        rows = (await connection.execute(nearest_chunks(vector, VECTOR_K, embedding, scope))).all()
    return sorted(rows, key=lambda row: row.distance)


async def _ids(engine: AsyncEngine, query: Select[str, float]) -> list[str]:
    async with engine.connect() as connection:
        return [row[0] for row in await connection.execute(query)]


async def _rows(engine: AsyncEngine, chunk_ids: list[str]) -> dict[str, Row[*tuple[Any, ...]]]:
    query = (
        select(
            Chunk.id,
            Chunk.text,
            Section.item,
            Filing.accession_number,
            Filing.cik,
            Filing.form_type,
            Filing.filed_on,
            Filing.period_end,
            Filing.fiscal_year,
            Filing.fiscal_period,
            Filing.primary_document,
        )
        .join(Section, Section.id == Chunk.section_id)
        .join(Filing, Filing.id == Section.filing_id)
        .where(Chunk.id.in_(chunk_ids))
    )
    async with engine.connect() as connection:
        return {row.id: row for row in await connection.execute(query)}


def _hit(row: Row[*tuple[Any, ...]], score: float) -> Hit:
    return Hit(
        chunk_id=row.id,
        score=round(score, SCORE_DIGITS),
        text=row.text,
        item=row.item,
        accession_number=row.accession_number,
        cik=row.cik,
        form_type=row.form_type,
        filed_on=row.filed_on,
        period_end=row.period_end,
        fiscal_year=row.fiscal_year,
        fiscal_period=row.fiscal_period,
        primary_document=row.primary_document,
    )


async def _rerank(
    q: str, texts: list[str], model: str, max_tokens: int, timeout_s: float
) -> list[float] | None:
    """Cross-encoder scores, or None past `timeout_s`; the first call loads the model untimed."""
    await asyncio.to_thread(reranker, model, max_tokens)
    abandoned = threading.Event()
    try:
        async with asyncio.timeout(timeout_s):
            return await asyncio.to_thread(
                rerank, q, texts, model=model, max_tokens=max_tokens, abandoned=abandoned
            )
    except TimeoutError:
        abandoned.set()  # still queued: it will skip the model; already running: result dropped
        metrics.RERANK_TIMEOUTS.add(1)
        log.warning("reranker timed out, fused order kept", timeout_s=timeout_s, texts=len(texts))
        return None
