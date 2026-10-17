"""API fixtures: settings env, an in-memory Backend, and the app served by uvicorn on 127.0.0.1."""

import asyncio
import threading
import time
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import uvicorn
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from filing_lens_api_client import AuthenticatedClient
from filing_lens_graphql_client import Client as GraphqlClient
from pydantic import BaseModel

from filinglens_api.backend import (
    AnswerEvents,
    Backend,
    CompanyKey,
    FailureKey,
    FilingKey,
    ItemKey,
    SearchKey,
    decode_cursor,
    encode_cursor,
    get_backend,
)
from filinglens_api.limits import answer_limits, answer_limits_for, rate_limit
from filinglens_api.main import app
from filinglens_api.schemas import (
    Answer,
    AnswerCompleted,
    AnswerDelta,
    AnswerRequest,
    Chunk,
    ChunkPage,
    Citation,
    Company,
    CompanyPage,
    FactPage,
    FailurePage,
    Filing,
    FilingCounts,
    FilingFailure,
    FilingPage,
    FinancialFact,
    FiscalPeriod,
    FormType,
    IngestJob,
    IngestJobRequest,
    SearchHit,
    SearchPage,
    Section,
    Usage,
)
from filinglens_core.errors import IdempotencyKeyReusedError, InvalidInputError, NotFoundError
from filinglens_core.settings import DatabaseSettings, load_settings
from filinglens_db import make_engine
from filinglens_db.seed import seed

API_KEY = "k" * 32
ADMIN_KEY = "a" * 32
PYPROJECT = Path(__file__).parents[3] / "pyproject.toml"

# Synthetic records for the fake backend, each list in the order its route returns it.
URL = "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/"
COMPANIES = [
    Company(cik=320193, ticker="AAPL", name="Apple Inc."),
    Company(cik=789019, ticker="MSFT", name="Microsoft Corporation"),
    Company(cik=1045810, ticker="NVDA", name="NVIDIA Corporation"),
]


def _filing(
    number: str, cik: int, form: FormType, filed: date, end: date, period: FiscalPeriod
) -> Filing:
    return Filing(
        accession_number=number,
        cik=cik,
        form_type=form,
        filed_on=filed,
        period_end=end,
        fiscal_year=2025,
        fiscal_period=period,
        url=URL,
    )


FILINGS = [  # newest first
    _filing(
        "0000320193-25-000079",
        320193,
        FormType.FORM_10K,
        date(2025, 10, 31),
        date(2025, 9, 27),
        FiscalPeriod.FY,
    ),
    _filing(
        "0000320193-25-000073",
        320193,
        FormType.FORM_10Q,
        date(2025, 8, 1),
        date(2025, 6, 28),
        FiscalPeriod.Q3,
    ),
    _filing(
        "0000789019-25-000073",
        789019,
        FormType.FORM_10K,
        date(2025, 7, 30),
        date(2025, 6, 30),
        FiscalPeriod.FY,
    ),
]
SECTIONS = [
    Section(id="s-1a", item="1A", title="Risk Factors"),
    Section(id="s-7", item="7", title="Management's Discussion and Analysis"),
]
CHUNKS = [
    Chunk(id="c-1", section_id="s-1a", text="We depend on a small number of suppliers."),
    Chunk(id="c-2", section_id="s-7", text="Net sales rose on higher services revenue."),
    Chunk(id="c-3", section_id="s-7", text="Gross margin was flat."),
]
FACTS = [
    FinancialFact(
        id="f-1",
        concept="us-gaap:Revenues",
        label="Revenues",
        value=100_000_000_000.0,
        unit="USD",
        period_start=date(2024, 9, 29),
        period_end=date(2025, 9, 27),
        fiscal_year=2025,
        fiscal_period=FiscalPeriod.FY,
        accession_number="0000320193-25-000079",
    ),
    FinancialFact(
        id="f-2",
        concept="us-gaap:EarningsPerShareDiluted",
        label="Diluted earnings per share",
        value=6.5,
        unit="USD/shares",
        period_start=date(2024, 9, 29),
        period_end=date(2025, 9, 27),
        fiscal_year=2025,
        fiscal_period=FiscalPeriod.FY,
        accession_number="0000320193-25-000079",
    ),
]
HITS = [  # score descending, then chunk id
    SearchHit(chunk_id="c-1", score=0.91, text=CHUNKS[0].text, section="1A", filing=FILINGS[0]),
    SearchHit(chunk_id="c-2", score=0.85, text=CHUNKS[1].text, section="7", filing=FILINGS[0]),
    SearchHit(chunk_id="c-3", score=0.85, text=CHUNKS[2].text, section="7", filing=FILINGS[0]),
]
ANSWER = Answer(
    answer="Revenue was $100.0 billion [f-1]; supplier concentration is a key risk [c-1].",
    citations=[
        Citation(fact_id="f-1", quote="Revenues 100,000", filing_url=URL),
        Citation(chunk_id="c-1", quote="We depend on a small number of suppliers.", filing_url=URL),
    ],
    degraded=False,
    usage=Usage(input_tokens=1200, output_tokens=60, cost_usd=0.0),
)
FAILURES = [
    FilingFailure(
        accession_number=f"0000320193-25-00000{n}",
        cik=320193,
        form_type=FormType.FORM_10Q,
        error="SEC returned 503 five times.",
        attempts=5,
        failed_at=datetime(2026, 10, 14, tzinfo=UTC),
    )
    for n in (1, 2, 3)
]


def _page[T](
    items: Sequence[T],
    key: Callable[[T], BaseModel],
    key_type: type[BaseModel],
    limit: int,
    cursor: str | None,
) -> tuple[list[T], str | None]:
    """Keyset paging over a list that is already in sort order."""
    start = 0
    if cursor is not None:
        last = decode_cursor(cursor, key_type)
        start = next((i + 1 for i, item in enumerate(items) if key(item) == last), -1)
        if start < 0:
            raise InvalidInputError("Unusable cursor; start again without one")
    page = list(items[start : start + limit])
    return page, encode_cursor(key(page[-1])) if start + limit < len(items) else None


def _filing_key(filing: Filing) -> FilingKey:
    return FilingKey(filed_on=filing.filed_on, accession_number=filing.accession_number)


def _item_key(item: Chunk | FinancialFact) -> ItemKey:
    return ItemKey(id=item.id)


class FakeBackend:
    """In-memory Backend. Set fail_with to make every call raise, fail_mid_stream for streams."""

    def __init__(self) -> None:
        self.fail_with: Exception | None = None
        self.fail_mid_stream: Exception | None = None
        self.delay_s = 0.0  # answers wait this long before each part
        self.answered = 0  # answers that passed the limits and reached the backend
        self.jobs: dict[UUID, IngestJobRequest] = {}
        self.job_ids: dict[str, UUID] = {}  # by Idempotency-Key

    def _admit(self) -> None:
        if self.fail_with is not None:
            raise self.fail_with

    async def create_ingest_job(self, request: IngestJobRequest, idempotency_key: str) -> UUID:
        self._admit()
        job_id = self.job_ids.setdefault(idempotency_key, uuid4())
        if self.jobs.setdefault(job_id, request) != request:
            raise IdempotencyKeyReusedError("This Idempotency-Key came with a different body.")
        return job_id

    async def get_ingest_job(self, job_id: UUID, limit: int, cursor: str | None) -> IngestJob:
        self._admit()
        if job_id not in self.jobs:
            raise NotFoundError("No such ingest job.")
        items, next_cursor = _page(
            FAILURES,
            lambda f: FailureKey(accession_number=f.accession_number),
            FailureKey,
            limit,
            cursor,
        )
        return IngestJob(
            job_id=job_id,
            status="partially_failed",
            request=self.jobs[job_id],
            created_at=datetime(2026, 10, 14, tzinfo=UTC),
            counts=FilingCounts(pending=0, running=0, succeeded=7, failed=3, skipped=2),
            failures=FailurePage(items=items, next_cursor=next_cursor),
        )

    async def list_companies(self, limit: int, cursor: str | None) -> CompanyPage:
        self._admit()
        items, next_cursor = _page(
            COMPANIES, lambda c: CompanyKey(cik=c.cik), CompanyKey, limit, cursor
        )
        return CompanyPage(items=items, next_cursor=next_cursor)

    async def list_filings(
        self,
        limit: int,
        cursor: str | None,
        *,
        cik: int | None = None,
        form_type: FormType | None = None,
        fiscal_year: int | None = None,
    ) -> FilingPage:
        self._admit()
        matching = [
            f
            for f in FILINGS
            if cik in (None, f.cik)
            and form_type in (None, f.form_type)
            and fiscal_year in (None, f.fiscal_year)
        ]
        items, next_cursor = _page(matching, _filing_key, FilingKey, limit, cursor)
        return FilingPage(items=items, next_cursor=next_cursor)

    async def list_sections(self, accession_number: str) -> list[Section]:
        self._admit()
        return SECTIONS

    async def list_chunks(
        self,
        accession_number: str,
        limit: int,
        cursor: str | None,
        *,
        section_id: str | None = None,
    ) -> ChunkPage:
        self._admit()
        matching = [c for c in CHUNKS if section_id in (None, c.section_id)]
        items, next_cursor = _page(matching, _item_key, ItemKey, limit, cursor)
        return ChunkPage(items=items, next_cursor=next_cursor)

    async def list_facts(
        self, accession_number: str, limit: int, cursor: str | None, *, concept: str | None = None
    ) -> FactPage:
        self._admit()
        matching = [f for f in FACTS if concept in (None, f.concept)]
        items, next_cursor = _page(matching, _item_key, ItemKey, limit, cursor)
        return FactPage(items=items, next_cursor=next_cursor)

    async def search(
        self,
        q: str,
        limit: int,
        cursor: str | None,
        *,
        cik: int | None = None,
        fiscal_year: int | None = None,
    ) -> SearchPage:
        self._admit()
        items, next_cursor = _page(
            [h for h in HITS if cik in (None, h.filing.cik)],
            lambda h: SearchKey(score=h.score, chunk_id=h.chunk_id, index_version="fake-v1"),
            SearchKey,
            limit,
            cursor,
        )
        return SearchPage(items=items, next_cursor=next_cursor, degraded=False)

    async def answer(self, request: AnswerRequest) -> Answer:
        self._admit()
        self.answered += 1
        await asyncio.sleep(self.delay_s)
        return ANSWER

    async def stream_answer(self, request: AnswerRequest) -> AnswerEvents:
        self._admit()  # before the stream, so the route can still answer with a status code
        self.answered += 1
        failure, delay_s = self.fail_mid_stream, self.delay_s

        async def events() -> AsyncGenerator[AnswerDelta | AnswerCompleted, None]:
            text = ANSWER.answer
            for start in range(0, len(text), 20):
                await asyncio.sleep(delay_s)
                yield AnswerDelta(text=text[start : start + 20])
                if failure is not None:
                    raise failure
            yield AnswerCompleted(answer=ANSWER)

        return events()


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Nothing answers on 0.0.0.0:1, so every dependency check fails, and at once: a closed
    # 127.0.0.1 port takes 2 s to refuse a connection on Windows.
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@0.0.0.0:1/app")
    monkeypatch.setenv("REDIS_URL", "redis://0.0.0.0:1/0")
    monkeypatch.setenv("BROKER_URL", "amqp://app:app@0.0.0.0:1//")
    monkeypatch.setenv("API_KEY", API_KEY)
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    _set_env(monkeypatch)
    return monkeypatch


@pytest.fixture
def api_key() -> str:
    return API_KEY


@pytest.fixture
def admin_key() -> str:
    return ADMIN_KEY


async def _no_limit() -> None:
    """Stands in for the Redis-backed limits, which test_limits.py covers against real Redis."""


def _no_limit_for() -> Callable[[], Awaitable[None]]:
    return _no_limit


UNLIMITED: dict[Callable[..., object], Callable[..., object]] = {
    rate_limit: _no_limit,
    answer_limits: _no_limit,
    answer_limits_for: _no_limit_for,  # GraphQL's answer limits
}


@pytest.fixture
def client(env: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The app with its real backend, in process, without the Redis-backed limits."""
    app.dependency_overrides.update(UNLIMITED)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@contextmanager
def _serve(access_log: bool = False) -> Iterator[str]:
    """Run the app with uvicorn on a free 127.0.0.1 port in a background thread."""
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_config=None, access_log=access_log)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise RuntimeError("the API server did not start")
        time.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture
def fake() -> FakeBackend:
    return FakeBackend()


@pytest.fixture(scope="module")
def _served() -> Iterator[tuple[str, dict[str, Backend]]]:
    """The app served once per test module, without the Redis-backed limits; each test plugs in
    its own backend. Starting and stopping uvicorn for every test took 0.3 s each.

    The fixtures that run the app themselves (client, live, postgres_user, serve) share the one
    app object, so a module must not use them after a test that used this one.
    """
    current: dict[str, Backend] = {}
    with pytest.MonkeyPatch.context() as monkeypatch:
        _set_env(monkeypatch)
        app.dependency_overrides[get_backend] = lambda: current["backend"]
        app.dependency_overrides.update(UNLIMITED)
        try:
            with _serve() as url:
                yield url, current
        finally:
            app.dependency_overrides.clear()


@pytest.fixture
def server_url(_served: tuple[str, dict[str, Backend]], fake: FakeBackend) -> str:
    """The app over this test's in-memory backend, served over HTTP."""
    url, current = _served
    current["backend"] = fake  # pyright checks that the fake matches the protocol
    return url


@pytest.fixture
def serve(env: pytest.MonkeyPatch) -> Iterator[Callable[..., AbstractContextManager[str]]]:
    """Serves the app with its real backend, without the Redis-backed limits, over HTTP on
    127.0.0.1 (serve(access_log=True) logs each request). Set DATABASE_URL through `env` first."""
    app.dependency_overrides.update(UNLIMITED)
    try:
        yield _serve
    finally:
        app.dependency_overrides.clear()


def _rest_client(url: str, key: str | None) -> AuthenticatedClient:
    # Without a key, the token goes into a header the API ignores, so X-API-Key is absent.
    return AuthenticatedClient(
        base_url=url,
        token=key or "",
        prefix="",
        auth_header_name="X-API-Key" if key is not None else "X-Unused",
        raise_on_unexpected_status=True,  # a status missing from the spec fails the test
    )


@pytest.fixture
def user(server_url: str) -> AuthenticatedClient:
    return _rest_client(server_url, API_KEY)


@pytest.fixture
def admin(server_url: str) -> AuthenticatedClient:
    return _rest_client(server_url, ADMIN_KEY)


@pytest.fixture
def anonymous(server_url: str) -> AuthenticatedClient:
    return _rest_client(server_url, None)


@pytest.fixture
def stranger(server_url: str) -> AuthenticatedClient:
    """Sends a well-formed key that is neither API_KEY nor ADMIN_API_KEY."""
    return _rest_client(server_url, "w" * 32)


@pytest.fixture
def graphql(server_url: str) -> GraphqlClient:
    return GraphqlClient(url=f"{server_url}/graphql", headers={"X-API-Key": API_KEY})


async def _seed() -> None:
    engine = make_engine(load_settings(DatabaseSettings))
    try:
        await seed(engine)
    finally:
        await engine.dispose()


@pytest.fixture
def postgres_user(env: pytest.MonkeyPatch, postgres_url: str) -> Iterator[AuthenticatedClient]:
    """A client of the app with its real backend, over a migrated and seeded Postgres."""
    env.setenv("DATABASE_URL", postgres_url)
    command.upgrade(Config(toml_file=PYPROJECT), "head")
    asyncio.run(_seed())
    app.dependency_overrides.update(UNLIMITED)
    try:
        with _serve() as url:
            yield _rest_client(url, API_KEY)
    finally:
        app.dependency_overrides.clear()
