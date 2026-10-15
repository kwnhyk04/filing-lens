"""XBRL companyfacts as financial_facts rows, and each filing's fiscal year and period.

Rows keep what SEC published: units, periods, values and forms (10-K/A included), unscaled.
Entries without a fiscal year or with a fiscal period outside FY and Q1-Q4 (8-K and prospectus
facts, mostly) are skipped: the columns and the API's FiscalPeriod need one of those.
"""

from collections import Counter, defaultdict
from collections.abc import Iterator
from datetime import date
from typing import Any

FISCAL_PERIODS = frozenset({"FY", "Q1", "Q2", "Q3", "Q4"})


def _entries(data: dict[str, Any]) -> Iterator[tuple[str, str, str, str, dict[str, Any]]]:
    """(taxonomy, concept, label, unit, entry) for every reported value."""
    for taxonomy, concepts in data.get("facts", {}).items():
        for concept, fact in concepts.items():
            label = fact.get("label") or concept
            for unit, entries in fact.get("units", {}).items():
                for entry in entries:
                    if entry.get("fy") is not None and entry.get("fp") in FISCAL_PERIODS:
                        yield taxonomy, concept, label, unit, entry


def fact_rows(data: dict[str, Any], cik: int) -> Iterator[dict[str, Any]]:
    """financial_facts rows of one company's companyfacts JSON."""
    for taxonomy, concept, label, unit, entry in _entries(data):
        start = entry.get("start")
        yield {
            "cik": cik,
            "taxonomy": taxonomy,
            "concept": concept,
            "label": label,
            "unit": unit,
            "value": entry["val"],
            "period_start": date.fromisoformat(start) if start else None,
            "period_end": date.fromisoformat(entry["end"]),
            "fiscal_year": entry["fy"],
            "fiscal_period": entry["fp"],
            "form": entry["form"],
            "accession_number": entry["accn"],
            "filed_on": date.fromisoformat(entry["filed"]),
        }


def fiscal_by_accession(data: dict[str, Any]) -> dict[str, tuple[int, str]]:
    """Each filing's fiscal year and period, as its companyfacts entries report them."""
    seen: defaultdict[str, Counter[tuple[int, str]]] = defaultdict(Counter)
    for *_, entry in _entries(data):
        seen[entry["accn"]][(entry["fy"], entry["fp"])] += 1
    return {accession: counts.most_common(1)[0][0] for accession, counts in seen.items()}


def fiscal_from_period(form: str, period_end: date, year_end: str | None) -> tuple[int, str]:
    """Fiscal year and period from the period of report, for filings companyfacts lacks.

    `year_end` is the company's fiscalYearEnd from its submissions, such as "0928"; unknown means
    December. A 10-K covers the fiscal year ending at period_end; a 10-Q one of its first three
    quarters. Approximate: companies whose 52-53 week year ends in early January may name it by
    the year before.
    """
    if form.startswith("10-K"):
        return period_end.year, "FY"
    month = int(year_end[:2]) if year_end else 12
    quarter = min(max(round((period_end.month - month) % 12 / 3), 1), 3)
    return period_end.year + (period_end.month > month), f"Q{quarter}"
