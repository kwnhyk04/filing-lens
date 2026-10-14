"""Build the HNSW (cosine) index on chunks.embedding_v2 concurrently.

Run after the reembed task has filled the column: one build is faster than row-by-row upkeep.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "ix_chunks_embedding_v2"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        # A failed concurrent build leaves an invalid index; dropping it lets a rerun start clean.
        op.drop_index(INDEX, table_name="chunks", postgresql_concurrently=True, if_exists=True)
        op.create_index(
            INDEX,
            "chunks",
            ["embedding_v2"],
            postgresql_using="hnsw",
            postgresql_ops={"embedding_v2": "vector_cosine_ops"},
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(INDEX, table_name="chunks", postgresql_concurrently=True, if_exists=True)
