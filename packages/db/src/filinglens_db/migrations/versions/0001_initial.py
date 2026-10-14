"""Enable pgvector and create companies.

Revision ID: 0001
Revises:
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "companies",
        sa.Column("cik", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint("cik", name=op.f("pk_companies")),
    )


def downgrade() -> None:
    op.drop_table("companies")
    op.execute("DROP EXTENSION IF EXISTS vector")
