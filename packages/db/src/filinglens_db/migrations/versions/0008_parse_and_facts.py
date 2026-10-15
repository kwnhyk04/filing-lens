"""Columns for parse, chunk and facts, and a facts key that includes cik.

Expand: filings.fiscal_source and missing_items, sections.text and financial_facts.filed_on are
nullable without defaults, so each ALTER only changes the catalog. The new unique index on
financial_facts adds cik to the old key, so building it cannot fail on existing rows; it is built
concurrently. Then the old key goes: no code depends on it, and it would drop one registrant's
facts from a combined filing. It revises 0007, and 0004 now revises it: the embedding swap stays
last until the live swap (docs/migrations.md).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FISCAL_SOURCE = postgresql.ENUM(
    "companyfacts", "period_of_report", name="fiscal_source", create_type=False
)
FACT_KEY = "uq_financial_facts_cik"
FACT_KEY_COLUMNS = [
    "cik",
    "taxonomy",
    "concept",
    "unit",
    "period_end",
    "period_start",
    "accession_number",
]
OLD_FACT_KEY = "uq_financial_facts_accession_number"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        # A failed concurrent build leaves an invalid index; dropping it lets a rerun start clean.
        op.drop_index(
            FACT_KEY, table_name="financial_facts", postgresql_concurrently=True, if_exists=True
        )
        op.create_index(
            FACT_KEY,
            "financial_facts",
            FACT_KEY_COLUMNS,
            unique=True,
            postgresql_nulls_not_distinct=True,
            postgresql_concurrently=True,
        )
    FISCAL_SOURCE.create(op.get_bind(), checkfirst=True)
    op.add_column("filings", sa.Column("fiscal_source", FISCAL_SOURCE, nullable=True))
    op.add_column(
        "filings", sa.Column("missing_items", postgresql.ARRAY(sa.String(length=10)), nullable=True)
    )
    op.add_column("sections", sa.Column("text", sa.Text(), nullable=True))
    op.add_column("financial_facts", sa.Column("filed_on", sa.Date(), nullable=True))
    op.drop_constraint(OLD_FACT_KEY, "financial_facts", type_="unique")


def downgrade() -> None:
    # Fails while one filing reports the same fact for two CIKs; delete one of the pair first.
    op.create_unique_constraint(
        OLD_FACT_KEY,
        "financial_facts",
        ["accession_number", "taxonomy", "concept", "unit", "period_start", "period_end"],
        postgresql_nulls_not_distinct=True,
    )
    op.drop_column("financial_facts", "filed_on")
    op.drop_column("sections", "text")
    op.drop_column("filings", "missing_items")
    op.drop_column("filings", "fiscal_source")
    FISCAL_SOURCE.drop(op.get_bind(), checkfirst=True)
    with op.get_context().autocommit_block():
        op.drop_index(
            FACT_KEY, table_name="financial_facts", postgresql_concurrently=True, if_exists=True
        )
