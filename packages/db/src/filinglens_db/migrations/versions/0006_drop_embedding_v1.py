"""Contract: drop chunks.embedding (model A) and its index.

Ships in a later release than 0004 and 0005: only once search reads embedding_v2 everywhere
(RETRIEVAL_EMBEDDING_COLUMN=embedding_v2) and no running code reads the old column. It refuses
to run while any chunk lacks embedding_v2, so a stray `upgrade head` cannot drop model A data.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from filinglens_db.models import Vector

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "ix_chunks_embedding"


def upgrade() -> None:
    query = sa.text("SELECT count(*) FROM chunks WHERE embedding_v2 IS NULL")
    missing = op.get_bind().scalar(query)
    if missing:
        raise RuntimeError(
            f"{missing} chunks have no embedding_v2; finish the reembed backfill before 0006"
            " (docs/migrations.md)."
        )
    with op.get_context().autocommit_block():
        op.drop_index(INDEX, table_name="chunks", postgresql_concurrently=True, if_exists=True)
    op.drop_column("chunks", "embedding_model")
    op.drop_column("chunks", "embedding")


def downgrade() -> None:
    # Restores the shape only: the old vectors are gone, so re-embed with model A before using it.
    op.add_column("chunks", sa.Column("embedding", Vector(384), nullable=True))
    op.add_column("chunks", sa.Column("embedding_model", sa.String(length=100), nullable=True))
    with op.get_context().autocommit_block():
        op.drop_index(INDEX, table_name="chunks", postgresql_concurrently=True, if_exists=True)
        op.create_index(
            INDEX,
            "chunks",
            ["embedding"],
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_concurrently=True,
        )
