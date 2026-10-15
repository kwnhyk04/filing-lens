"""Hybrid search (pgvector + full text), reciprocal rank fusion and the reranker interface."""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from fractions import Fraction

from sqlalchemy import Float, Select, String, column, select, table

from filinglens_core.settings import EmbeddingColumn
from filinglens_db.models import Vector

RRF_K = 60  # Cormack et al. (2009); a larger k flattens the lead of the top ranks


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


def nearest_chunks(
    vector: Sequence[float], limit: int, embedding: EmbeddingColumn
) -> Select[str, float]:
    """Chunk ids nearest to `vector` by cosine distance, served by the HNSW index on `embedding`.

    Callers pass RETRIEVAL_EMBEDDING_COLUMN on every query, so flipping it switches the index.
    """
    chunks = table("chunks", column("id", String), column(embedding, Vector(len(vector))))
    distance = chunks.c[embedding].op("<=>", return_type=Float())(vector)
    return select(chunks.c.id, distance.label("distance")).order_by(distance).limit(limit)
