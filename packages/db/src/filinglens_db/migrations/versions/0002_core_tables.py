"""Add companies.sector and the filing, chunk, fact, ingest, dead-letter and eval tables.

New tables only: their indexes beyond keys come concurrently in 0003. Chunks start on model A
(BAAI/bge-small-en-v1.5, 384 dimensions); 0004-0006 swap to model B.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-14
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from filinglens_db.models import Vector

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FILING_STATUS = sa.Enum(
    "discovered", "fetched", "parsed", "embedded", "indexed", "failed", name="filing_status"
)
JOB_STATUS = sa.Enum(
    "queued", "running", "succeeded", "partially_failed", "failed", name="ingest_job_status"
)
ITEM_STATUS = sa.Enum(
    "pending", "running", "succeeded", "failed", "skipped", name="ingest_item_status"
)


def _created_at() -> sa.Column[datetime]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    op.add_column("companies", sa.Column("sector", sa.String(length=100), nullable=True))
    op.create_table(
        "filings",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("accession_number", sa.String(length=20), nullable=False),
        sa.Column("cik", sa.BigInteger(), nullable=False),
        sa.Column("form_type", sa.String(length=20), nullable=False),
        sa.Column("fiscal_year", sa.SmallInteger(), nullable=True),
        sa.Column("fiscal_period", sa.String(length=2), nullable=True),
        sa.Column("filed_on", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("primary_document", sa.String(length=200), nullable=False),
        sa.Column("status", FILING_STATUS, server_default="discovered", nullable=False),
        sa.CheckConstraint(
            "status <> 'indexed' OR (fiscal_year IS NOT NULL AND fiscal_period IS NOT NULL)",
            name=op.f("ck_filings_indexed_has_fiscal_period"),
        ),
        sa.ForeignKeyConstraint(["cik"], ["companies.cik"], name=op.f("fk_filings_cik_companies")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_filings")),
        sa.UniqueConstraint("accession_number", name=op.f("uq_filings_accession_number")),
    )
    op.create_table(
        "sections",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("filing_id", sa.BigInteger(), nullable=False),
        sa.Column("item", sa.String(length=20), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["filing_id"],
            ["filings.id"],
            name=op.f("fk_sections_filing_id_filings"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sections")),
        sa.UniqueConstraint("filing_id", "item", name=op.f("uq_sections_filing_id")),
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("section_id", sa.BigInteger(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english'::regconfig, text)", persisted=True),
            nullable=False,
        ),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column("embedding_model", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["sections.id"],
            name=op.f("fk_chunks_section_id_sections"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunks")),
    )
    op.create_table(
        "financial_facts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("cik", sa.BigInteger(), nullable=False),
        sa.Column("taxonomy", sa.String(length=20), nullable=False),
        sa.Column("concept", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("fiscal_year", sa.SmallInteger(), nullable=False),
        sa.Column("fiscal_period", sa.String(length=2), nullable=False),
        sa.Column("form", sa.String(length=20), nullable=False),
        sa.Column("accession_number", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(
            ["cik"], ["companies.cik"], name=op.f("fk_financial_facts_cik_companies")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financial_facts")),
        sa.UniqueConstraint(
            "accession_number",
            "taxonomy",
            "concept",
            "unit",
            "period_start",
            "period_end",
            name=op.f("uq_financial_facts_accession_number"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_table(
        "ingest_jobs",
        sa.Column("id", sa.Uuid(), server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request", postgresql.JSONB(), nullable=False),
        sa.Column("status", JOB_STATUS, server_default="queued", nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingest_jobs")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_ingest_jobs_idempotency_key")),
    )
    op.create_table(
        "ingest_job_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("filing_id", sa.BigInteger(), nullable=False),
        sa.Column("status", ITEM_STATUS, server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["filing_id"], ["filings.id"], name=op.f("fk_ingest_job_items_filing_id_filings")
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["ingest_jobs.id"],
            name=op.f("fk_ingest_job_items_job_id_ingest_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingest_job_items")),
        sa.UniqueConstraint("job_id", "filing_id", name=op.f("uq_ingest_job_items_job_id")),
    )
    op.create_table(
        "dead_letters",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("task_name", sa.String(length=200), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dead_letters")),
        sa.UniqueConstraint("task_id", name=op.f("uq_dead_letters_task_id")),
    )
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("dataset_version", sa.String(length=50), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_runs")),
    )


def downgrade() -> None:
    for table in (
        "eval_runs",
        "dead_letters",
        "ingest_job_items",
        "ingest_jobs",
        "financial_facts",
        "chunks",
        "sections",
        "filings",
    ):
        op.drop_table(table)
    for enum in (ITEM_STATUS, JOB_STATUS, FILING_STATUS):
        enum.drop(op.get_bind())
    op.drop_column("companies", "sector")
