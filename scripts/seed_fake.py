"""Fake data for load and pagination tests only: 200 companies, 2,000 filings, 100k chunks.

Each company comes from its own fixed seed, so a rerun skips the companies already loaded and
fills in any missing ones unchanged. Fake CIKs start at 9,000,000,000, above every real one.
Every embedding column the schema has gets random unit vectors (0003: `embedding`, head:
`embedding_v2`). Rows go in with COPY and the HNSW indexes are rebuilt once at the end, all in one
transaction that locks chunks: do not run it against a database that serves traffic.
Run with `make seed-fake`.
"""

import math
import random
import time
from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, LiteralString, cast

import psycopg
import structlog
from faker import Faker
from psycopg import sql
from sqlalchemy import make_url

from filinglens_core.settings import (
    EMBEDDING_DIMENSIONS,
    DatabaseSettings,
    EmbeddingColumn,
    load_settings,
)
from filinglens_db.models import chunk_id
from filinglens_telemetry import configure_logging

SEED = 42
CIK_BASE = 9_000_000_000
MODEL = "fake-random-unit-vector"
SESSION = "-c lock_timeout=5s -c statement_timeout=30min"  # an index rebuild takes minutes
SECTORS = [
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Financials",
    "Health Care",
    "Industrials",
    "Information Technology",
    "Materials",
    "Real Estate",
    "Utilities",
]
MDA = "Management's Discussion and Analysis"
MARKET_RISK = "Quantitative and Qualitative Disclosures About Market Risk"
SECTIONS = {
    "10-K": [
        ("1", "Business"),
        ("1A", "Risk Factors"),
        ("7", MDA),
        ("7A", MARKET_RISK),
        ("8", "Financial Statements and Supplementary Data"),
    ],
    "10-Q": [
        ("I-1", "Financial Statements"),
        ("I-2", MDA),
        ("I-3", MARKET_RISK),
        ("II-1", "Legal Proceedings"),
        ("II-1A", "Risk Factors"),
    ],
}
PERIODS = [("FY", 12, 31), ("Q3", 9, 30), ("Q2", 6, 30), ("Q1", 3, 31)]  # newest first
FACTS = [
    ("Revenues", "Revenues", "USD"),
    ("NetIncomeLoss", "Net Income (Loss)", "USD"),
    ("EarningsPerShareDiluted", "Earnings Per Share, Diluted", "USD/shares"),
]
FILING_COLUMNS = (
    "accession_number",
    "cik",
    "form_type",
    "fiscal_year",
    "fiscal_period",
    "filed_on",
    "period_end",
    "primary_document",
    "status",
)
FACT_COLUMNS = (
    "cik",
    "taxonomy",
    "concept",
    "label",
    "unit",
    "value",
    "period_start",
    "period_end",
    "fiscal_year",
    "fiscal_period",
    "form",
    "accession_number",
)
log = structlog.get_logger(__name__)


def unit_vector(rng: random.Random, dimensions: int) -> str:
    """A random unit vector in pgvector's text form."""
    vector = [rng.gauss(0, 1) for _ in range(dimensions)]
    norm = math.hypot(*vector)
    return "[" + ",".join([str(x / norm) for x in vector]) + "]"


def copy_rows(
    cursor: psycopg.Cursor[Any],
    table: str,
    columns: Sequence[str],
    rows: Iterable[Sequence[object]],
) -> None:
    statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
        sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, columns))
    )
    with cursor.copy(statement) as copy:
        for row in rows:
            copy.write_row(row)


def load_company(
    cursor: psycopg.Cursor[Any],
    fake: Faker,
    rng: random.Random,
    n: int,
    embeddings: Sequence[EmbeddingColumn],
    filings_per_company: int,
    chunks_per_section: int,
) -> None:
    """Generate company n from its own seed, then COPY its rows."""
    cik = CIK_BASE + n
    fake.seed_instance(f"{SEED}:{n}")
    rng.seed(f"{SEED}:{n}")
    company = (cik, fake.lexify("????").upper(), fake.company(), rng.choice(SECTORS))
    filings: list[tuple[object, ...]] = []
    sections: list[tuple[str, str, str, int, int]] = []  # accession, item, title, start, end
    chunks: list[tuple[str, str, tuple[object, ...]]] = []  # accession, item, row
    facts: list[tuple[object, ...]] = []
    for k in range(filings_per_company):
        period, month, day = PERIODS[k % 4]
        year = 2025 - k // 4
        form = "10-K" if period == "FY" else "10-Q"
        accession = f"{cik:010d}-{year % 100:02d}-{k:06d}"
        period_end = date(year, month, day)
        filed_on = period_end + timedelta(days=rng.randint(20, 60))
        primary_document = f"fake-{k}.htm"
        filings.append(
            (accession, cik, form, year, period, filed_on, period_end, primary_document, "indexed")
        )
        offset = 0  # chunk offsets run through the whole filing text
        for item, title in SECTIONS[form]:
            start = offset
            for _ in range(chunks_per_section):
                text = fake.paragraph(nb_sentences=8)
                vectors = [
                    value
                    for column in embeddings
                    for value in (unit_vector(rng, EMBEDDING_DIMENSIONS[column]), MODEL)
                ]
                row = (chunk_id(accession, item, offset), offset, text, len(text.split()), *vectors)
                chunks.append((accession, item, row))
                offset += len(text) + 1
            sections.append((accession, item, title, start, offset))
        period_start = date(year, 1 if period == "FY" else month - 2, 1)
        for concept, label, unit in FACTS:
            value = rng.randint(10**6, 10**11) if unit == "USD" else round(rng.uniform(-5, 20), 2)
            facts.append(
                (
                    cik,
                    "us-gaap",
                    concept,
                    label,
                    unit,
                    Decimal(str(value)),
                    period_start,
                    period_end,
                    year,
                    period,
                    form,
                    accession,
                )
            )

    copy_rows(cursor, "companies", ("cik", "ticker", "name", "sector"), [company])
    copy_rows(cursor, "filings", FILING_COLUMNS, filings)
    filing_query = "SELECT accession_number, id FROM filings WHERE cik = %s"
    filing_ids = {a: filing_id for a, filing_id in cursor.execute(filing_query, (cik,))}
    copy_rows(
        cursor,
        "sections",
        ("filing_id", "item", "title", "char_start", "char_end"),
        [(filing_ids[a], item, title, start, end) for a, item, title, start, end in sections],
    )
    section_query = "SELECT filing_id, item, id FROM sections WHERE filing_id = ANY(%s)"
    section_ids = {
        (filing_id, item): section_id
        for filing_id, item, section_id in cursor.execute(
            section_query, (list(filing_ids.values()),)
        )
    }
    columns = ["id", "section_id", "char_start", "text", "token_count"]
    for column in embeddings:
        columns += [column, f"{column}_model"]
    copy_rows(
        cursor,
        "chunks",
        columns,
        [(row[0], section_ids[filing_ids[a], item], *row[1:]) for a, item, row in chunks],
    )
    copy_rows(cursor, "financial_facts", FACT_COLUMNS, facts)


def seed_fake(
    database_url: str,
    companies: int = 200,
    filings_per_company: int = 10,
    chunks_per_section: int = 10,
) -> int:
    """COPY in the fake companies that are missing; returns how many it loaded."""
    url = make_url(database_url).set(drivername="postgresql")
    conninfo = url.render_as_string(hide_password=False)
    with psycopg.connect(conninfo, autocommit=True, connect_timeout=5, options=SESSION) as db:
        loaded = db.execute("SELECT cik FROM companies WHERE cik >= %s", (CIK_BASE,)).fetchall()
        present = {cik for (cik,) in loaded}
        missing = [n for n in range(companies) if CIK_BASE + n not in present]
        if not missing:
            return 0
        embeddings: list[EmbeddingColumn] = [
            name
            for (name,) in db.execute(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema = current_schema() AND table_name = 'chunks'"
                " AND column_name = ANY(%s) ORDER BY column_name",
                (list(EMBEDDING_DIMENSIONS),),
            )
        ]
        fake = Faker()
        rng = random.Random()  # noqa: S311 - test data, not security
        with db.transaction(), db.cursor() as cursor:
            # One HNSW build beats updating the index row by row. The DROP is part of the
            # transaction, so a failed load leaves the index as it was.
            indexes = cursor.execute(
                "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = current_schema()"
                " AND tablename = 'chunks' AND indexdef LIKE '%USING hnsw%'"
            ).fetchall()
            for name, _ in indexes:
                cursor.execute(sql.SQL("DROP INDEX {}").format(sql.Identifier(name)))
            for done, n in enumerate(missing, 1):
                load_company(
                    cursor, fake, rng, n, embeddings, filings_per_company, chunks_per_section
                )
                if done % 20 == 0:
                    log.info("seeding fake data", companies=done)
            # Serial, so the whole graph (about 400 MB for 100k 768-dimension vectors) stays in
            # local memory; a parallel build would hold it in /dev/shm, capped at 256 MB.
            cursor.execute("SET LOCAL max_parallel_maintenance_workers = 0")
            cursor.execute("SET LOCAL maintenance_work_mem = '512MB'")
            for name, definition in indexes:
                cursor.execute(cast(LiteralString, definition))  # verbatim from pg_indexes
                log.info("rebuilt index", index=name)
    return len(missing)


def main() -> None:
    settings = load_settings(DatabaseSettings)
    configure_logging("seed-fake", settings.log_level)
    started = time.monotonic()
    loaded = seed_fake(str(settings.database_url.get_secret_value()))
    log.info("seeded fake data", companies=loaded, seconds=round(time.monotonic() - started))


if __name__ == "__main__":
    main()
