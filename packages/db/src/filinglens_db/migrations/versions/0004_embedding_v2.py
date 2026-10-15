"""Expand: add chunks.embedding_v2 for model B (BAAI/bge-base-en-v1.5, 768 dimensions).

Nullable with no default, so the ALTER only changes the catalog. Running code ignores the new
columns until the reembed task fills them. Runbook: docs/migrations.md. The swap stays at the end
of the chain until the live swap: a new revision slots in before this one.

Revision ID: 0004
Revises: 0008
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from filinglens_db.models import Vector

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("embedding_v2", Vector(768), nullable=True))
    op.add_column("chunks", sa.Column("embedding_v2_model", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("chunks", "embedding_v2_model")
    op.drop_column("chunks", "embedding_v2")
