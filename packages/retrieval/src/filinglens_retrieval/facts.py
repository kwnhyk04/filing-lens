"""XBRL facts for answers: one value per concept and period, by the latest-filed rule."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncConnection

from filinglens_db.models import FinancialFact

ANNUAL_FORMS = ("10-K", "10-K/A")
QUARTERLY_FORMS = ("10-Q", "10-Q/A")
ANNUAL_DAYS = (350, 380)  # a 52-53 week or calendar year
QUARTER_DAYS = (80, 100)


@dataclass(frozen=True)
class Fact:
    id: int
    cik: int
    concept: str  # taxonomy:name, such as us-gaap:Revenues
    label: str
    value: Decimal
    unit: str
    period_start: date | None  # None for an instant, such as a balance on period_end
    period_end: date
    fiscal_year: int  # of the filing that reported it
    fiscal_period: str
    form: str
    accession_number: str
    filed_on: date | None


async def get_financial_fact(
    connection: AsyncConnection,
    cik: int,
    concepts: Sequence[str],
    unit: str,
    *,
    fiscal_year: int | None = None,
    fiscal_period: str = "FY",
) -> Fact | None:
    """The value of the first of `concepts` that has one for the period (docs/memory.md, 4b).

    The period is the latest period end that the fiscal year's own reports (10-K for FY, 10-Q for
    a quarter) give the concept, as a duration of that length or as an instant; fiscal_year None
    means the latest. A comparative carries its filing's later year, so the latest period end is
    the year's own. The value comes from the latest-filed filing reporting exactly that period
    (filed_on, then accession number), so restatements win: durations from the same form family,
    instants from any of the four forms.
    """
    forms = ANNUAL_FORMS if fiscal_period == "FY" else QUARTERLY_FORMS
    shortest, longest = ANNUAL_DAYS if fiscal_period == "FY" else QUARTER_DAYS
    days = FinancialFact.period_end - FinancialFact.period_start  # an integer for two dates
    for concept in concepts:
        taxonomy, _, name = concept.partition(":")
        same = (
            FinancialFact.cik == cik,
            FinancialFact.taxonomy == taxonomy,
            FinancialFact.concept == name,
            FinancialFact.unit == unit,
        )
        period = select(FinancialFact.period_start, FinancialFact.period_end).where(
            *same,
            FinancialFact.fiscal_period == fiscal_period,
            FinancialFact.form.in_(forms),
            or_(FinancialFact.period_start.is_(None), days.between(shortest, longest)),
        )
        if fiscal_year is not None:
            period = period.where(FinancialFact.fiscal_year == fiscal_year)
        latest = period.order_by(FinancialFact.period_end.desc()).limit(1)
        found = (await connection.execute(latest)).one_or_none()
        if found is None:
            continue
        reporting = ANNUAL_FORMS + QUARTERLY_FORMS if found.period_start is None else forms
        query = (
            select(FinancialFact)
            .where(
                *same,
                FinancialFact.period_end == found.period_end,
                FinancialFact.period_start.is_not_distinct_from(found.period_start),
                FinancialFact.form.in_(reporting),
            )
            .order_by(
                FinancialFact.filed_on.desc().nulls_last(), FinancialFact.accession_number.desc()
            )
            .limit(1)
        )
        row = (await connection.execute(query)).one()
        return Fact(
            id=row.id,
            cik=row.cik,
            concept=f"{row.taxonomy}:{row.concept}",
            label=row.label,
            value=row.value,
            unit=row.unit,
            period_start=row.period_start,
            period_end=row.period_end,
            fiscal_year=row.fiscal_year,
            fiscal_period=row.fiscal_period,
            form=row.form,
            accession_number=row.accession_number,
            filed_on=row.filed_on,
        )
    return None


async def latest_fiscal_year(connection: AsyncConnection, cik: int) -> int | None:
    """The fiscal year of the company's latest annual report among its facts, if any."""
    query = select(func.max(FinancialFact.fiscal_year)).where(
        FinancialFact.cik == cik,
        FinancialFact.fiscal_period == "FY",
        FinancialFact.form.in_(ANNUAL_FORMS),
    )
    return await connection.scalar(query)
