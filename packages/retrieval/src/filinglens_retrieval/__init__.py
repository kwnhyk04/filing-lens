"""Hybrid search (pgvector + full text), reciprocal rank fusion and the reranker interface."""

from collections.abc import Sequence

from sqlalchemy import Float, Select, String, column, select, table

from filinglens_core.settings import EmbeddingColumn
from filinglens_db.models import Vector


def nearest_chunks(
    vector: Sequence[float], limit: int, embedding: EmbeddingColumn
) -> Select[str, float]:
    """Chunk ids nearest to `vector` by cosine distance, served by the HNSW index on `embedding`.

    Callers pass RETRIEVAL_EMBEDDING_COLUMN on every query, so flipping it switches the index.
    """
    chunks = table("chunks", column("id", String), column(embedding, Vector(len(vector))))
    distance = chunks.c[embedding].op("<=>", return_type=Float())(vector)
    return select(chunks.c.id, distance.label("distance")).order_by(distance).limit(limit)
