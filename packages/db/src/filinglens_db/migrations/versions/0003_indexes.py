"""Build the retrieval and keyset indexes concurrently.

HNSW (cosine) on chunks.embedding, GIN on chunks.tsv, reading order for chunks, newest-first
filings, and (created_at, id) keyset indexes for the ingest, dead-letter and eval lists.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-14
"""

from collections.abc import Sequence
from typing import Any

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEXES: list[tuple[str, str, list[str], dict[str, Any]]] = [
    ("ix_filings_filed_on_accession_number", "filings", ["filed_on", "accession_number"], {}),
    ("ix_chunks_section_id_char_start", "chunks", ["section_id", "char_start"], {}),
    ("ix_chunks_tsv", "chunks", ["tsv"], {"postgresql_using": "gin"}),
    (
        "ix_chunks_embedding",
        "chunks",
        ["embedding"],
        {"postgresql_using": "hnsw", "postgresql_ops": {"embedding": "vector_cosine_ops"}},
    ),
    ("ix_ingest_jobs_created_at_id", "ingest_jobs", ["created_at", "id"], {}),
    ("ix_dead_letters_created_at_id", "dead_letters", ["created_at", "id"], {}),
    ("ix_eval_runs_created_at_id", "eval_runs", ["created_at", "id"], {}),
]


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for name, table, columns, options in INDEXES:
            # A failed concurrent build leaves an invalid index; drop it so a rerun starts clean.
            op.drop_index(name, table_name=table, postgresql_concurrently=True, if_exists=True)
            op.create_index(name, table, columns, postgresql_concurrently=True, **options)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, table, _, _ in reversed(INDEXES):
            op.drop_index(name, table_name=table, postgresql_concurrently=True, if_exists=True)
