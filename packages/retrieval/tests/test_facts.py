"""get_financial_fact on Postgres: the latest-filed rule (docs/memory.md, step 4b)."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from filinglens_db.models import Company, FinancialFact
from filinglens_retrieval.facts import get_financial_fact, latest_fiscal_year

pytestmark = pytest.mark.integration
PYPROJECT = Path(__file__).parents[3] / "pyproject.toml"
APPLE = 320193
FY24, FY25 = (date(2023, 10, 1), date(2024, 9, 28)), (date(2024, 9, 29), date(2025, 9, 27))
K24, K25 = "0000320193-24-000123", "0000320193-25-000079"
type Query = Callable[[Callable[[AsyncConnection], Awaitable[Any]]], Any]


def fact(
    value: int, period: tuple[date | None, date], fy: int, accession: str, filed: date
) -> dict[str, object]:
    concept = "Revenues" if period[0] else "Assets"
    return {
        "cik": APPLE,
        "taxonomy": "us-gaap",
        "concept": concept,
        "label": concept,
        "unit": "USD",
        "value": Decimal(value),
        "period_start": period[0],
        "period_end": period[1],
        "fiscal_year": fy,
        "fiscal_period": "FY",
        "form": "10-K",
        "accession_number": accession,
        "filed_on": filed,
    }


ROWS = [
    # The fiscal 2024 10-K: its year and a comparative.
    fact(391, FY24, 2024, K24, date(2024, 11, 1)),
    fact(383, (date(2022, 9, 25), date(2023, 9, 30)), 2024, K24, date(2024, 11, 1)),
    # The fiscal 2025 10-K: its year, a restated fiscal 2024 and a year-end balance.
    fact(416, FY25, 2025, K25, date(2025, 10, 31)),
    fact(392, FY24, 2025, K25, date(2025, 10, 31)),
    fact(359, (None, date(2025, 9, 27)), 2025, K25, date(2025, 10, 31)),
]


@pytest.fixture
def query(database_url: str, monkeypatch: pytest.MonkeyPatch) -> Query:
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(Config(toml_file=PYPROJECT), "head")

    async def seed() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as connection:
            await connection.execute(insert(Company).values(cik=APPLE, ticker="AAPL", name="Apple"))
            await connection.execute(insert(FinancialFact), ROWS)
        await engine.dispose()

    asyncio.run(seed())

    def run(work: Callable[[AsyncConnection], Awaitable[Any]]) -> Any:
        async def main() -> Any:
            engine = create_async_engine(database_url)
            try:
                async with engine.connect() as connection:
                    return await work(connection)
            finally:
                await engine.dispose()

        return asyncio.run(main())

    return run


def value(query: Query, concepts: list[str], **period: Any) -> tuple[Any, ...] | None:
    found = query(lambda c: get_financial_fact(c, APPLE, concepts, "USD", **period))
    return None if found is None else (found.value, found.period_end, found.accession_number)


def test_a_year_reads_its_own_period_and_a_restatement_wins(query: Query) -> None:
    revenues = ["us-gaap:Revenues"]
    assert value(query, revenues, fiscal_year=2025) == (416, FY25[1], K25)
    # Fiscal 2024: the fiscal 2025 10-K restated it, and the later filing wins.
    assert value(query, revenues, fiscal_year=2024) == (392, FY24[1], K25)
    assert value(query, revenues) == (416, FY25[1], K25)  # no year: the latest
    assert value(query, ["us-gaap:Nope", *revenues], fiscal_year=2025) == (416, FY25[1], K25)
    assert value(query, revenues, fiscal_year=2027) is None
    assert value(query, ["us-gaap:Assets"], fiscal_year=2025) == (359, FY25[1], K25)  # an instant


def test_the_latest_fiscal_year_comes_from_annual_reports(query: Query) -> None:
    assert query(lambda c: latest_fiscal_year(c, APPLE)) == 2025
    assert query(lambda c: latest_fiscal_year(c, 1)) is None
