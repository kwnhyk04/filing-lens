"""Expand: ingest_job_companies, so an ingest job knows when discovery has walked every company.

It revises 0003, and 0004 now revises it: the embedding swap (0004-0006) stays at the end of the
chain until the live swap, so dev can apply this revision without the swap (docs/migrations.md).

Revision ID: 0007
Revises: 0003
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ITEM_STATUS: sa.Enum = postgresql.ENUM(
    "pending",
    "running",
    "succeeded",
    "failed",
    "skipped",
    name="ingest_item_status",
    create_type=False,  # 0002 created it for ingest_job_items
)


def upgrade() -> None:
    op.create_table(
        "ingest_job_companies",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("cik", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("status", ITEM_STATUS, server_default="pending", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["ingest_jobs.id"],
            name=op.f("fk_ingest_job_companies_job_id_ingest_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("job_id", "cik", name=op.f("pk_ingest_job_companies")),
    )


def downgrade() -> None:
    op.drop_table("ingest_job_companies")
