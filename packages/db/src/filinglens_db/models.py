"""ORM models; every schema change ships as an Alembic revision (see docs/migrations.md)."""

import hashlib
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql.base import (  # untyped dict[str, type]
    ischema_names,  # pyright: ignore[reportUnknownVariableType]
)
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

from filinglens_core.settings import EMBEDDING_DIMENSIONS


class Vector(UserDefinedType[list[float]]):
    """pgvector's vector(dim), sent and read in its text form, such as '[0.1,0.2]'."""

    cache_ok = True

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def get_col_spec(self, **_: Any) -> str:
        return f"vector({self.dim})"

    # The processors' return types are inferred: SQLAlchemy's protocol types for them are private.
    def bind_processor(self, dialect: Dialect):
        def process(value: Sequence[float] | None) -> str | None:
            return None if value is None else f"[{','.join(map(str, value))}]"

        return process

    def result_processor(self, dialect: Dialect, coltype: object):
        def process(value: str | None) -> list[float] | None:
            return None if value is None else [float(x) for x in value[1:-1].split(",")]

        return process


ischema_names["vector"] = Vector  # reflection (alembic check) reads vector(n) columns as Vector(n)


def chunk_id(accession_number: str, item: str, char_start: int) -> str:
    """sha256 of a chunk's filing, section and offset, so re-ingesting a filing is idempotent."""
    return hashlib.sha256(f"{accession_number}:{item}:{char_start}".encode()).hexdigest()


class FilingStatus(StrEnum):
    DISCOVERED = "discovered"
    FETCHED = "fetched"
    PARSED = "parsed"
    EMBEDDED = "embedded"
    INDEXED = "indexed"
    FAILED = "failed"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIALLY_FAILED = "partially_failed"
    FAILED = "failed"


class ItemStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


def _values(enum: type[StrEnum]) -> list[str]:
    return [member.value for member in enum]


def _pg_enum(enum: type[StrEnum], name: str) -> Enum:
    """A Postgres enum type that stores the members' values, not their names."""
    return Enum(enum, name=name, values_callable=_values)


class Base(DeclarativeBase):
    # Deterministic constraint names, so later migrations can rename or drop them.
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class Company(Base):
    """A company whose filings FilingLens ingests, keyed by SEC Central Index Key."""

    __tablename__ = "companies"

    cik: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    ticker: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(200))
    sector: Mapped[str | None] = mapped_column(String(100))


class Filing(Base):
    """A 10-K or 10-Q; status tracks it through the ingest pipeline."""

    __tablename__ = "filings"
    __table_args__ = (
        # The API lists indexed filings and needs their fiscal period.
        CheckConstraint(
            "status <> 'indexed' OR (fiscal_year IS NOT NULL AND fiscal_period IS NOT NULL)",
            name="indexed_has_fiscal_period",
        ),
        Index("ix_filings_filed_on_accession_number", "filed_on", "accession_number"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    accession_number: Mapped[str] = mapped_column(String(20), unique=True)
    cik: Mapped[int] = mapped_column(ForeignKey("companies.cik"))
    form_type: Mapped[str] = mapped_column(String(20))
    fiscal_year: Mapped[int | None] = mapped_column(SmallInteger)  # known once parsed
    fiscal_period: Mapped[str | None] = mapped_column(String(2))
    filed_on: Mapped[date]
    period_end: Mapped[date]
    primary_document: Mapped[str] = mapped_column(String(200))
    status: Mapped[FilingStatus] = mapped_column(
        _pg_enum(FilingStatus, "filing_status"), server_default=FilingStatus.DISCOVERED.value
    )


class Section(Base):
    """An item of a filing, such as Item 1A, as a character range of the filing text."""

    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("filing_id", "item"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filings.id", ondelete="CASCADE"))
    item: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int]
    char_end: Mapped[int]


class Chunk(Base):
    """A retrieval unit of section text. The embedding columns follow docs/migrations.md."""

    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_section_id_char_start", "section_id", "char_start"),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding_v2",
            "embedding_v2",
            postgresql_using="hnsw",
            postgresql_ops={"embedding_v2": "vector_cosine_ops"},
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # chunk_id()
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"))
    char_start: Mapped[int]  # offset in the filing text, so it also orders a filing's chunks
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int]
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english'::regconfig, text)", persisted=True)
    )
    # Deferred, so loading chunks also works at revision 0003, before these columns exist.
    embedding_v2: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS["embedding_v2"]), deferred=True
    )
    embedding_v2_model: Mapped[str | None] = mapped_column(String(100), deferred=True)


class FinancialFact(Base):
    """An XBRL fact as SEC's companyfacts API reports it: one row per filing that reported it."""

    __tablename__ = "financial_facts"
    __table_args__ = (
        # Upsert key: one row per concept, unit and period in a filing (instant facts: no start).
        UniqueConstraint(
            "accession_number",
            "taxonomy",
            "concept",
            "unit",
            "period_start",
            "period_end",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    cik: Mapped[int] = mapped_column(ForeignKey("companies.cik"))
    taxonomy: Mapped[str] = mapped_column(String(20))  # us-gaap, dei, ifrs-full
    concept: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(50))
    value: Mapped[Decimal] = mapped_column(Numeric)
    period_start: Mapped[date | None]
    period_end: Mapped[date]
    fiscal_year: Mapped[int] = mapped_column(SmallInteger)
    fiscal_period: Mapped[str] = mapped_column(String(2))
    form: Mapped[str] = mapped_column(String(20))
    accession_number: Mapped[str] = mapped_column(String(20))


class IngestJob(Base):
    """An admin request to ingest companies' filings; the Idempotency-Key makes retries safe."""

    __tablename__ = "ingest_jobs"
    __table_args__ = (Index("ix_ingest_jobs_created_at_id", "created_at", "id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    request: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[JobStatus] = mapped_column(
        _pg_enum(JobStatus, "ingest_job_status"), server_default=JobStatus.QUEUED.value
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IngestJobCompany(Base):
    """One company of an ingest job; discovery done for every company lets the job finish."""

    __tablename__ = "ingest_job_companies"

    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("ingest_jobs.id", ondelete="CASCADE"), primary_key=True
    )
    cik: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    status: Mapped[ItemStatus] = mapped_column(
        _pg_enum(ItemStatus, "ingest_item_status"), server_default=ItemStatus.PENDING.value
    )
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IngestJobItem(Base):
    """One filing of an ingest job, with its attempts and last error."""

    __tablename__ = "ingest_job_items"
    __table_args__ = (UniqueConstraint("job_id", "filing_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("ingest_jobs.id", ondelete="CASCADE"))
    filing_id: Mapped[int] = mapped_column(ForeignKey("filings.id"))
    status: Mapped[ItemStatus] = mapped_column(
        _pg_enum(ItemStatus, "ingest_item_status"), server_default=ItemStatus.PENDING.value
    )
    attempts: Mapped[int] = mapped_column(server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DeadLetter(Base):
    """A task message that used up its retries, kept for inspection and replay."""

    __tablename__ = "dead_letters"
    __table_args__ = (Index("ix_dead_letters_created_at_id", "created_at", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), unique=True)  # a redelivery is stored once
    task_name: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)  # the task's args and kwargs
    error: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvalRun(Base):
    """One eval harness run: dataset version, configuration and metrics."""

    __tablename__ = "eval_runs"
    __table_args__ = (Index("ix_eval_runs_created_at_id", "created_at", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    dataset_version: Mapped[str] = mapped_column(String(50))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
