"""Answers about FilingLens itself, which no model writes: a fixed overview of the app, and the
collection's figures as the database holds them at answer time, by Coverage's rule that a company
counts once it has an indexed filing."""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection

from filinglens_db.models import Company, Filing, FilingStatus, IngestJob, JobStatus

LIST_MAX = 50  # tickers one answer names; a longer list gives a count of the rest
OVERVIEW = (
    "FilingLens is a research tool for the SEC filings of US public companies."
    " It answers questions from their 10-K filings and cites the passages and figures it used."
    " Quotes and amounts are checked against the passages and XBRL facts it cites."
    " When the filings don't answer a question, it says so instead of guessing."
)
MADE_BY = "FilingLens was built by Gab as a portfolio project."
REPOSITORY = "https://github.com/kwnhyk04/filing-lens"
APP_ANSWER = f"{OVERVIEW} {MADE_BY} {REPOSITORY}"


@dataclass(frozen=True)
class Covered:
    """A company with an indexed filing, and those filings' forms and fiscal years."""

    ticker: str
    name: str
    forms: tuple[str, ...]
    fiscal_years: tuple[int, ...]


@dataclass(frozen=True)
class Collection:
    companies: tuple[Covered, ...]  # by ticker
    filings: int  # indexed
    loaded_on: date | None  # the last finished ingest job's day; a restored corpus records none
    newest_filing: date | None


async def read_collection(connection: AsyncConnection) -> Collection:
    query = (
        select(
            func.upper(Company.ticker),
            Company.name,
            Filing.form_type,
            Filing.fiscal_year,
            Filing.filed_on,
        )
        .join(Filing, Filing.cik == Company.cik)
        .where(Filing.status == FilingStatus.INDEXED)
    )
    rows = (await connection.execute(query)).all()
    names: dict[str, str] = {}
    forms: defaultdict[str, set[str]] = defaultdict(set)
    years: defaultdict[str, set[int]] = defaultdict(set)
    for ticker, name, form, year, _ in rows:
        names[ticker] = name
        forms[ticker].add(form)
        years[ticker].add(cast(int, year))  # constraint indexed_has_fiscal_period
    finished = (JobStatus.SUCCEEDED, JobStatus.PARTIALLY_FAILED)
    loaded = await connection.scalar(
        select(func.max(IngestJob.created_at)).where(IngestJob.status.in_(finished))
    )
    return Collection(
        tuple(
            Covered(
                ticker, names[ticker], tuple(sorted(forms[ticker])), tuple(sorted(years[ticker]))
            )
            for ticker in sorted(names)
        ),
        len(rows),
        loaded.date() if loaded else None,
        max((row.filed_on for row in rows), default=None),
    )


def _listed(items: Sequence[str]) -> str:
    """ "a", "a and b", "a, b and c"."""
    return items[0] if len(items) < 2 else f"{', '.join(items[:-1])} and {items[-1]}"


def _years(years: Iterable[int]) -> str:
    return _listed([str(year) for year in sorted(years)])


def _day(day: date) -> str:
    return f"{day:%B} {day.day}, {day.year}"


def roster(tickers: Iterable[str]) -> str:
    """The collection's companies by ticker, cut to LIST_MAX and a count of the rest."""
    named = sorted(tickers)
    if not named:
        return "The collection holds no filings yet."
    rest = [f"{len(named) - LIST_MAX} more"] if len(named) > LIST_MAX else []
    count = "1 company" if len(named) == 1 else f"{len(named)} companies"
    return f"The collection covers {count}: {_listed([*named[:LIST_MAX], *rest])}."


def not_held(names: Sequence[str], tickers: Iterable[str]) -> str:
    """That the collection lacks these companies, and what it has: a collection answer's words,
    and the refusal's for a filing question about such a company."""
    are = "it is" if len(names) == 1 else "they are"
    lacks = f"FilingLens has no filings for {_listed(names)}: {are} not in the collection."
    return f"{lacks} {roster(tickers)}"


def _loaded(held: Collection) -> list[str]:
    if held.loaded_on:
        return [f"The data was last loaded on {_day(held.loaded_on)}."]
    if held.newest_filing:
        newest = _day(held.newest_filing)
        return [f"No load date is on record; the newest filing was filed on {newest}."]
    return []


def collection_answer(held: Collection, tickers: Sequence[str], others: Sequence[str]) -> str:
    """The answer from `held` alone: each company the question names, and the whole collection
    when it names none or one the collection lacks."""
    covered = {company.ticker: company for company in held.companies}
    named = [covered[ticker] for ticker in tickers if ticker in covered]
    missing = [*others, *(ticker for ticker in tickers if ticker not in covered)]
    lines = [
        f"{c.name} ({c.ticker}) is in the collection, with its {_listed(c.forms)} for fiscal"
        f" {_years(c.fiscal_years)}."
        for c in named
    ]
    if missing:
        lines.append(not_held(missing, covered))
    elif not named:
        lines.append(roster(covered))
    if held.companies and (missing or not named):
        forms = _listed(sorted({form for company in held.companies for form in company.forms}))
        years = _years({year for company in held.companies for year in company.fiscal_years})
        count = "1 filing" if held.filings == 1 else f"{held.filings} filings"
        lines.append(f"It holds {count} ({forms}) for fiscal {years}.")
    return " ".join([*lines, *_loaded(held)])
