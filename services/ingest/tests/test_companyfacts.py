"""companyfacts rows and fiscal periods, on a trimmed copy of Apple's real companyfacts JSON.

The fixture keeps five concepts for Apple's fiscal 2025 10-K and one 10-Q, plus an 8-K entry
without a fiscal year and a 10-K/A entry.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from filinglens_ingest.companyfacts import fact_rows, fiscal_by_accession, fiscal_from_period

FIXTURES = Path(__file__).with_name("fixtures")
APPLE = 320193
TEN_K, TEN_Q = "0000320193-25-000079", "0000320193-25-000073"


def companyfacts() -> dict[str, Any]:
    """Parsed as SecClient.companyfacts parses it: decimals stay Decimal."""
    raw = (FIXTURES / "aapl-companyfacts.json").read_text(encoding="utf-8")
    return json.loads(raw, parse_float=Decimal)


def test_rows_keep_what_sec_published() -> None:
    rows = list(fact_rows(companyfacts(), APPLE))
    assert len(rows) == 28  # 29 entries less the 8-K one, which has no fiscal year
    assert {row["form"] for row in rows} == {"10-K", "10-Q", "10-K/A"}
    assert {row["unit"] for row in rows} == {"USD", "USD/shares", "shares"}
    assert all(row["cik"] == APPLE and isinstance(row["filed_on"], date) for row in rows)
    eps = [row["value"] for row in rows if row["concept"] == "EarningsPerShareBasic"]
    assert all(
        isinstance(value, Decimal) and value == value.quantize(Decimal("0.01")) for value in eps
    )
    assets = [row for row in rows if row["concept"] == "Assets"]
    assert assets and all(row["period_start"] is None for row in assets)  # instants
    # A comparative carries the year of the filing that reported it, not of its own period.
    comparative = next(
        row
        for row in rows
        if row["accession_number"] == TEN_K and row["period_end"] == date(2023, 9, 30)
    )
    assert (comparative["fiscal_year"], comparative["fiscal_period"]) == (2025, "FY")


def test_fiscal_year_and_period_come_from_each_filings_entries() -> None:
    fiscal = fiscal_by_accession(companyfacts())
    assert fiscal[TEN_K] == (2025, "FY")
    assert fiscal[TEN_Q] == (2025, "Q3")
    assert "0001193125-15-023732" not in fiscal  # the 8-K entry has no fiscal year


@pytest.mark.parametrize(
    ("form", "period_end", "year_end", "expected"),
    [
        ("10-K", date(2025, 9, 27), "0927", (2025, "FY")),
        ("10-Q", date(2024, 12, 28), "0927", (2025, "Q1")),  # Apple: fiscal 2025 starts in October
        ("10-Q", date(2025, 6, 28), "0927", (2025, "Q3")),
        ("10-Q", date(2025, 3, 31), "1231", (2025, "Q1")),
        ("10-Q", date(2025, 9, 30), None, (2025, "Q3")),  # unknown means a December year end
        ("10-Q", date(2025, 4, 30), "0131", (2026, "Q1")),  # Walmart
        ("10-Q", date(2025, 9, 30), "0630", (2026, "Q1")),  # Microsoft
    ],
)
def test_fiscal_period_from_the_period_of_report(
    form: str, period_end: date, year_end: str | None, expected: tuple[int, str]
) -> None:
    assert fiscal_from_period(form, period_end, year_end) == expected
