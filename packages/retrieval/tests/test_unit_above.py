"""with_unit_above on Postgres: the unit a table states above the chunk that holds its rows."""

import asyncio
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import create_async_engine

from filinglens_db.models import Chunk, Company, Filing, FilingStatus, Section, chunk_id
from filinglens_retrieval import UNIT_REACH, Hit, with_unit_above

pytestmark = pytest.mark.integration
PYPROJECT = Path(__file__).parents[3] / "pyproject.toml"
ACCESSION = "0000320193-25-000079"
SECTION_START = 1_000  # offsets count from the filing's text, a section's text from its own start
TEXT = (
    "(in thousands)\nFirst | 1\n(dollars in millions)\nCash | 4,121\n"
    + "x" * UNIT_REACH
    + "\nRevenue | 9,000"
)


def hit(chunk: str) -> Hit:
    day = date(2025, 10, 31)
    return Hit(chunk, 1.0, "", "7", ACCESSION, 320193, "10-K", day, day, 2025, "FY", "a.htm")


async def run(url: str) -> list[Hit]:
    engine = create_async_engine(url)
    filing = insert(Filing).values(
        accession_number=ACCESSION,
        cik=320193,
        form_type="10-K",
        fiscal_year=2025,
        fiscal_period="FY",
        filed_on=date(2025, 10, 31),
        period_end=date(2025, 9, 27),
        primary_document="a.htm",
        status=FilingStatus.INDEXED,
    )
    offsets = {"top": 0, "near": TEXT.index("Cash"), "far": TEXT.index("Revenue")}
    ids = {name: chunk_id(ACCESSION, "7", SECTION_START + at) for name, at in offsets.items()}
    async with engine.begin() as connection:
        await connection.execute(insert(Company).values(cik=320193, ticker="AAPL", name="Apple"))
        filing_id = (await connection.execute(filing.returning(Filing.id))).scalar_one()
        section = insert(Section).values(
            filing_id=filing_id,
            item="7",
            title="MD&A",
            char_start=SECTION_START,
            char_end=SECTION_START + len(TEXT),
            text=TEXT,
        )
        section_id = (await connection.execute(section.returning(Section.id))).scalar_one()
        rows = [
            {
                "id": ids[name],
                "section_id": section_id,
                "char_start": SECTION_START + at,
                "text": "chunk",
                "token_count": 1,
            }
            for name, at in offsets.items()
        ]
        await connection.execute(insert(Chunk), rows)
    try:
        return await with_unit_above(engine, [hit(ids["near"]), hit(ids["far"]), hit(ids["top"])])
    finally:
        await engine.dispose()


def test_each_hit_takes_the_nearest_unit_stated_above_it_within_reach(
    monkeypatch: pytest.MonkeyPatch, database_url: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(Config(toml_file=PYPROJECT), "0008")
    near, far, top = asyncio.run(run(database_url))
    assert near.unit_above == "in millions"
    assert far.unit_above == ""  # past UNIT_REACH
    assert top.unit_above == ""
