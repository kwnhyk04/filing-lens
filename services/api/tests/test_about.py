"""Answers about FilingLens itself: the router picks the intent, a fixed template writes the text
from the database's figures, and no answer model runs and no filing is cited."""

import asyncio
import json
import re
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NamedTuple, cast

import pytest
from alembic import command
from alembic.config import Config
from redis.asyncio import Redis
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import create_async_engine

from filinglens_api import about, graph
from filinglens_api.about import Collection, Covered
from filinglens_api.answering import NO_EVIDENCE, Answerer, Models, PostgresEvidence
from filinglens_api.backend import LiveBackend, Totals
from filinglens_api.schemas import Answer, AnswerCompleted, AnswerDelta, AnswerRequest
from filinglens_db.models import Company, Filing, FilingStatus, IngestJob, JobStatus
from filinglens_llm import router
from filinglens_llm.providers import Completion
from filinglens_retrieval import Ranking, Scope

PYPROJECT = Path(__file__).parents[3] / "pyproject.toml"
AAPL = Covered("AAPL", "Apple Inc.", ("10-K",), (2025,))
MSFT = Covered("MSFT", "MICROSOFT CORP", ("10-K",), (2025, 2026))
HELD = Collection((AAPL, MSFT), 3, loaded_on=date(2026, 10, 15), newest_filing=date(2026, 8, 1))
ROSTER = "The collection covers 2 companies: AAPL and MSFT."
FILINGS = "It holds 3 filings (10-K) for fiscal 2025 and 2026."
LOADED = "The data was last loaded on October 15, 2026."


class RouterModel:
    """A router with one reply, recording each call; an answer call fails the test."""

    name = "test:router"

    def __init__(self, route: str, **reply: Any) -> None:
        blank = {"tickers": [], "other_companies": [], "fiscal_years": [], "metric": None}
        self.reply = blank | {"route": route, "fiscal_period": None} | reply
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self, system: str, user: str, *, max_tokens: int, schema: Any = None
    ) -> Completion:
        self.calls.append({"system": system, "schema": schema})
        return Completion(self.name, json.dumps(self.reply), 900, 40, 0.1)

    def stream(self, system: str, user: str, *, max_tokens: int) -> Any:
        raise AssertionError("an answer about FilingLens calls no answer model")


class HeldEvidence:
    """The collection, and a filing side that holds no fact and finds no passage."""

    def __init__(self, held: Collection = HELD) -> None:
        self.held = held
        self.reads = 0

    async def collection(self) -> Collection:
        self.reads += 1
        return self.held

    async def tracked(self) -> dict[str, str]:
        return {company.ticker: company.name for company in self.held.companies}

    async def companies(self, tickers: Sequence[str]) -> dict[str, int]:
        return {ticker: n for n, ticker in enumerate(tickers, 1)}

    async def names(self, ciks: Sequence[int]) -> dict[int, str]:
        return {cik: f"Company {cik}" for cik in ciks}

    async def latest_fiscal_year(self, cik: int) -> int | None:
        return 2025

    async def fact(self, *_: Any) -> None:
        return None

    async def search(self, question: str, scope: Scope) -> Ranking:
        return Ranking([], False, None, {})


async def ask(
    question: str, model: RouterModel, evidence: HeldEvidence | None = None
) -> tuple[Answer, str]:
    """The completed answer and the joined deltas."""
    provider = cast(Any, model)
    redis = Redis.from_url("redis://0.0.0.0:1/0")  # down: usage is logged, not counted
    answerer = Answerer(
        cast(Any, evidence or HeldEvidence()),
        Models(provider, provider, provider),
        redis,
        max_inflight=1,
        allow_fallback=False,
    )
    answer, deltas = None, list[str]()
    async for event in answerer.events(AnswerRequest(question=question)):
        if isinstance(event, AnswerDelta):
            deltas.append(event.text)
        elif isinstance(event, AnswerCompleted):
            answer = event.answer
    assert answer is not None
    return answer, "".join(deltas)


def route_of(answer: Answer) -> str:
    assert answer.reading is not None
    return answer.reading.route


@pytest.mark.parametrize("question", ["What is this app?", "What can you do?", "How does it work?"])
async def test_an_app_question_gets_the_overview_and_calls_no_answer_model(question: str) -> None:
    answer, streamed = await ask(question, RouterModel("about_app"))
    assert answer.answer == about.APP_ANSWER == streamed
    assert answer.answer.startswith(about.OVERVIEW)
    assert not answer.refused and answer.citations == [] and answer.checks == []
    assert answer.own_data and answer.reading is None  # the contract lists no about route
    assert (answer.usage.input_tokens, answer.usage.output_tokens) == (900, 40)  # the router only


@pytest.mark.parametrize(
    "question", ["Who created this app?", "Who built this?", "Who's behind FilingLens?"]
)
async def test_who_made_it_gets_the_app_answer_with_its_maker_and_its_link(question: str) -> None:
    answer, _ = await ask(question, RouterModel("about_app"))
    assert "FilingLens was built by Gab as a portfolio project." in answer.answer
    assert answer.answer.endswith("https://github.com/kwnhyk04/filing-lens")
    assert answer.own_data and answer.citations == []


def test_the_overview_is_three_or_four_sentences_with_no_figure_to_go_stale() -> None:
    sentences = re.split(r"(?<=\.)\s+", about.OVERVIEW)
    assert 3 <= len(sentences) <= 4
    for words in ("FilingLens", "SEC", "10-K", "cit", "XBRL", "says so"):
        assert words in about.OVERVIEW
    assert not re.search(r"\d", about.OVERVIEW.replace("10-K", ""))


@pytest.mark.parametrize(
    "question",
    [
        "How many companies do you have?",
        "Which companies?",
        "What years do you cover?",
        "What filings are included?",
        "When was the data last updated?",
    ],
)
async def test_a_collection_question_gets_every_figure_from_the_database(question: str) -> None:
    evidence = HeldEvidence()
    answer, streamed = await ask(question, RouterModel("about_collection"), evidence)
    assert answer.answer == f"{ROSTER} {FILINGS} {LOADED}" == streamed
    assert not answer.refused and answer.citations == [] and answer.checks == []
    assert answer.own_data and answer.reading is None and evidence.reads == 1
    assert graph.Answer.of(answer).own_data  # GraphQL says so too


async def test_each_answer_reads_the_database_again() -> None:
    evidence, model = HeldEvidence(), RouterModel("about_collection")
    await ask("How many filings do you have?", model, evidence)
    evidence.held = replace(HELD, filings=4)
    answer, _ = await ask("How many filings do you have?", model, evidence)
    assert "It holds 4 filings" in answer.answer and evidence.reads == 2


async def test_a_company_in_the_collection_gets_its_own_forms_and_years() -> None:
    model = RouterModel("about_collection", tickers=["MSFT"])
    answer, _ = await ask("Do you have Microsoft?", model)
    assert answer.answer == (
        f"MICROSOFT CORP (MSFT) is in the collection, with its 10-K for fiscal 2025 and 2026."
        f" {LOADED}"
    )
    assert not answer.refused


async def test_a_company_not_in_the_collection_gets_a_clear_answer_listing_what_is() -> None:
    model = RouterModel("about_collection", other_companies=["Netflix"])
    answer, _ = await ask("Do you have Netflix?", model)
    assert answer.answer == (
        f"FilingLens has no filings for Netflix: it is not in the collection."
        f" {ROSTER} {FILINGS} {LOADED}"
    )
    assert not answer.refused and answer.citations == []


async def test_one_company_held_and_two_not_are_each_answered() -> None:
    model = RouterModel("about_collection", tickers=["AAPL"], other_companies=["Netflix", "Oracle"])
    answer, _ = await ask("Do you have Apple, Netflix or Oracle?", model)
    assert answer.answer == (
        "Apple Inc. (AAPL) is in the collection, with its 10-K for fiscal 2025."
        " FilingLens has no filings for Netflix and Oracle: they are not in the collection."
        f" {ROSTER} {FILINGS} {LOADED}"
    )


async def test_a_filing_question_about_a_company_not_held_stays_refused_and_lists_what_is() -> None:
    model = RouterModel("numeric", other_companies=["Netflix"], metric="revenue")
    evidence = HeldEvidence()
    answer, streamed = await ask("What was Netflix's revenue in fiscal 2025?", model, evidence)
    assert answer.refused and route_of(answer) == "numeric"
    assert answer.answer == (
        f"FilingLens has no filings for Netflix: it is not in the collection. {ROSTER}"
    )
    assert streamed == answer.answer and evidence.reads == 0  # the tracked list already holds it


def test_a_long_list_is_cut_short_and_says_how_many_more() -> None:
    tickers = [f"T{n:03}" for n in range(about.LIST_MAX + 5)]
    text = about.roster(tickers)
    assert text.startswith(f"The collection covers {about.LIST_MAX + 5} companies: T000, T001,")
    assert text.endswith(f"T{about.LIST_MAX - 1:03} and 5 more.")
    assert f"T{about.LIST_MAX:03}" not in text


def test_one_company_reads_in_the_singular() -> None:
    assert about.roster(["AAPL"]) == "The collection covers 1 company: AAPL."
    held = Collection((AAPL,), 1, loaded_on=date(2026, 10, 15), newest_filing=date(2026, 8, 1))
    assert "It holds 1 filing (10-K) for fiscal 2025." in about.collection_answer(held, [], [])


def test_no_load_on_record_says_so_and_gives_the_newest_filing_instead() -> None:
    text = about.collection_answer(replace(HELD, loaded_on=None), [], [])
    newest = "the newest filing was filed on August 1, 2026."
    assert text.endswith(f"No load date is on record; {newest}") and "last loaded" not in text


def test_an_empty_collection_says_so_and_claims_no_figure() -> None:
    assert about.collection_answer(Collection((), 0, None, None), [], []) == (
        "The collection holds no filings yet."
    )
    assert about.collection_answer(Collection((), 0, None, None), [], ["Netflix"]) == (
        "FilingLens has no filings for Netflix: it is not in the collection."
        " The collection holds no filings yet."
    )


class Row(NamedTuple):
    ticker: str
    name: str
    form_type: str
    fiscal_year: int
    filed_on: date


class Connection:
    """The two reads read_collection makes; the integration test below runs them on Postgres."""

    def __init__(self, rows: list[Row], loaded: datetime | None) -> None:
        self.rows, self.loaded = rows, loaded

    async def execute(self, query: Any) -> SimpleNamespace:
        return SimpleNamespace(all=lambda: self.rows)

    async def scalar(self, query: Any) -> datetime | None:
        return self.loaded


async def test_the_collection_gathers_each_companys_filings_under_its_ticker() -> None:
    rows = [
        Row("MSFT", "MICROSOFT CORP", "10-K", 2026, date(2026, 8, 1)),
        Row("AAPL", "Apple Inc.", "10-K", 2025, date(2025, 10, 31)),
        Row("AAPL", "Apple Inc.", "10-K", 2024, date(2024, 11, 1)),
    ]
    connection = Connection(rows, datetime(2026, 10, 15, 23, 0, tzinfo=UTC))
    assert await about.read_collection(cast(Any, connection)) == Collection(
        (
            Covered("AAPL", "Apple Inc.", ("10-K",), (2024, 2025)),
            Covered("MSFT", "MICROSOFT CORP", ("10-K",), (2026,)),
        ),
        3,
        loaded_on=date(2026, 10, 15),
        newest_filing=date(2026, 8, 1),
    )


async def test_no_filing_and_no_finished_job_read_as_nothing_on_record() -> None:
    connection = Connection([], None)
    assert await about.read_collection(cast(Any, connection)) == Collection((), 0, None, None)


async def test_the_about_routes_reach_the_router_only_for_about_wording() -> None:
    plain, wide = RouterModel("textual"), RouterModel("about_app")
    await ask("What does Apple say about tariffs?", plain)
    await ask("What can you do?", wide)
    enum = plain.calls[0]["schema"]["properties"]["route"]["enum"]
    assert enum == list(router.ROUTES) and "about_app" not in plain.calls[0]["system"]
    enum = wide.calls[0]["schema"]["properties"]["route"]["enum"]
    assert enum == [*router.ROUTES, *router.ABOUT] and "about_app" in wide.calls[0]["system"]


@pytest.mark.parametrize(
    ("question", "route", "reply", "read_as"),
    [
        (
            "Do you have Apple's revenue?",
            "about_collection",
            {"tickers": ["AAPL"], "metric": "revenue"},
            "numeric",
        ),
        ("What can you tell me about Apple?", "about_app", {"tickers": ["AAPL"]}, "textual"),
        ("What can you tell me about risks?", "textual", {}, "textual"),
    ],
)
async def test_a_filing_question_in_about_wording_goes_to_the_filings(
    question: str, route: str, reply: dict[str, Any], read_as: str
) -> None:
    evidence = HeldEvidence()
    answer, _ = await ask(question, RouterModel(route, **reply), evidence)
    assert route_of(answer) == read_as and evidence.reads == 0
    assert answer.refused and answer.answer == NO_EVIDENCE  # this evidence holds no passage


@pytest.mark.parametrize(
    "question",
    ["Can you recommend a stock?", "Do you know who won the World Cup?", "What do you think?"],
)
async def test_anything_else_in_about_wording_stays_refused(question: str) -> None:
    answer, _ = await ask(question, RouterModel("out_of_scope"))
    assert answer.refused and "SEC filings cannot answer" in answer.answer


COMPANIES = [
    {"cik": 320193, "ticker": "aapl", "name": "Apple Inc."},
    {"cik": 789019, "ticker": "MSFT", "name": "MICROSOFT CORP"},
    {"cik": 1318605, "ticker": "TSLA", "name": "Tesla, Inc."},  # nothing indexed: not covered
]


def filing(cik: int, n: int, status: FilingStatus, year: int, filed_on: date) -> dict[str, Any]:
    return {
        "accession_number": f"0000000000-25-{n:06}",
        "cik": cik,
        "form_type": "10-K",
        "fiscal_year": year,
        "fiscal_period": "FY",
        "filed_on": filed_on,
        "period_end": date(year, 6, 30),
        "primary_document": "main.htm",
        "status": status,
    }


FILINGS_ROWS = [
    filing(320193, 1, FilingStatus.INDEXED, 2024, date(2024, 11, 1)),
    filing(320193, 2, FilingStatus.INDEXED, 2025, date(2025, 10, 31)),
    filing(320193, 3, FilingStatus.FAILED, 2023, date(2026, 9, 1)),  # newer, but never indexed
    filing(789019, 4, FilingStatus.INDEXED, 2026, date(2026, 8, 1)),
    filing(1318605, 5, FilingStatus.PARSED, 2025, date(2026, 1, 30)),
]
JOBS = [
    {"status": JobStatus.SUCCEEDED, "day": datetime(2026, 10, 1, tzinfo=UTC)},
    {"status": JobStatus.PARTIALLY_FAILED, "day": datetime(2026, 10, 15, 23, 0, tzinfo=UTC)},
    {"status": JobStatus.FAILED, "day": datetime(2026, 10, 20, tzinfo=UTC)},  # loaded nothing
    {"status": JobStatus.RUNNING, "day": datetime(2026, 10, 21, tzinfo=UTC)},  # not done
]


@pytest.mark.integration
def test_the_figures_match_the_database(env: pytest.MonkeyPatch, database_url: str) -> None:
    env.setenv("DATABASE_URL", database_url)
    command.upgrade(Config(toml_file=PYPROJECT), "0008")

    async def read() -> tuple[Collection, Totals]:
        engine = create_async_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(insert(Company), COMPANIES)
                await connection.execute(insert(Filing), FILINGS_ROWS)
                for n, job in enumerate(JOBS):
                    row = {"idempotency_key": str(n), "request": {}, "status": job["status"]}
                    await connection.execute(insert(IngestJob).values(**row, created_at=job["day"]))
            held = await PostgresEvidence(engine, cast(Any, None)).collection()
            return held, await LiveBackend(engine, cast(Any, None)).totals()
        finally:
            await engine.dispose()

    held, totals = asyncio.run(read())
    assert held == Collection(
        (
            Covered("AAPL", "Apple Inc.", ("10-K",), (2024, 2025)),
            Covered("MSFT", "MICROSOFT CORP", ("10-K",), (2026,)),
        ),
        3,
        loaded_on=date(2026, 10, 15),
        newest_filing=date(2026, 8, 1),
    )
    assert (len(held.companies), held.filings) == (totals.companies, totals.filings)  # Coverage's
