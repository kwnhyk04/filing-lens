"""Every operation through the generated clients, against the app served by uvicorn.

The app runs over an in-memory backend, so these tests pin the contract (paths, parameters,
bodies, status codes, headers and problem shapes), not the data layer.
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import httpx2
import pytest
from filing_lens_api_client import AuthenticatedClient, errors
from filing_lens_api_client.api.answers import create_answer, stream_answer
from filing_lens_api_client.api.catalog import list_companies, list_filings
from filing_lens_api_client.api.health import healthz, readyz
from filing_lens_api_client.api.ingest import create_ingest_job, get_ingest_job
from filing_lens_api_client.api.search import search
from filing_lens_api_client.models import (
    Answer,
    AnswerRequest,
    CompanyPage,
    FilingPage,
    Health,
    IngestJob,
    IngestJobAccepted,
    IngestJobRequest,
    Problem,
    SearchPage,
)
from filing_lens_api_client.types import UNSET, Response, Unset
from filing_lens_graphql_client import Client as GraphqlClient
from filing_lens_graphql_client import GraphQLClientGraphQLMultiError
from filing_lens_graphql_client.enums import FiscalPeriod, FormType
from redis.exceptions import RedisError
from starlette.routing import WebSocketRoute

from filinglens_api import backend, main, schemas
from filinglens_api.answering import Answerer, _final
from filinglens_api.backend import LiveBackend, SearchKey, encode_cursor
from filinglens_api.limits import answer_limits_for
from filinglens_api.main import app, graphql_router
from filinglens_core.errors import (
    FilingLensError,
    OverloadedError,
    RateLimitedError,
    UpstreamError,
)
from filinglens_llm import budget
from filinglens_llm.providers import failure

JOB = IngestJobRequest(ciks=[320193], form_types=["10-K", "10-Q"], since=date(2024, 1, 1))
QUESTION = AnswerRequest(question="What was revenue in fiscal 2025?", company_ids=[320193])

OPERATIONS: dict[str, Callable[[AuthenticatedClient], Response[Any]]] = {
    "create_ingest_job": lambda c: create_ingest_job.sync_detailed(
        client=c, body=JOB, idempotency_key="auth-check"
    ),
    "get_ingest_job": lambda c: get_ingest_job.sync_detailed(uuid4(), client=c),
    "list_companies": lambda c: list_companies.sync_detailed(client=c),
    "list_filings": lambda c: list_filings.sync_detailed(client=c),
    "search": lambda c: search.sync_detailed(client=c, q="revenue"),
    "create_answer": lambda c: create_answer.sync_detailed(client=c, body=QUESTION),
    "stream_answer": lambda c: stream_answer.sync_detailed(client=c, body=QUESTION),
}
ADMIN_ONLY = ["create_ingest_job", "get_ingest_job"]
EITHER_KEY = [name for name in OPERATIONS if name not in ADMIN_ONLY]


def _problem(response: Response[Any], status: int, code: str) -> Problem:
    assert response.status_code == status, response.content
    assert response.headers["content-type"] == "application/problem+json"
    assert isinstance(response.parsed, Problem)
    assert response.parsed.code == code
    return response.parsed


def _events(response: Response[Any]) -> list[dict[str, Any]]:
    """The JSON payload of each Server-Sent Event."""
    lines = response.content.decode().splitlines()
    return [json.loads(line.removeprefix("data: ")) for line in lines if line.startswith("data: ")]


def test_health_probes_need_no_key(anonymous: AuthenticatedClient) -> None:
    live = healthz.sync(client=anonymous)
    assert isinstance(live, Health)
    assert live.status == "ok"
    ready = readyz.sync_detailed(client=anonymous)
    assert ready.status_code == 503  # nothing listens on the test's dependency ports
    assert isinstance(ready.parsed, Health)
    assert ready.parsed.status == "unavailable"


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("caller", ["anonymous", "stranger"])
def test_every_operation_refuses_a_missing_or_unknown_key(
    request: pytest.FixtureRequest, caller: str, operation: str
) -> None:
    response = OPERATIONS[operation](request.getfixturevalue(caller))
    _problem(response, 401, "unauthorized")
    assert response.headers["WWW-Authenticate"] == "APIKey"


@pytest.mark.parametrize("operation", ADMIN_ONLY)
def test_the_normal_key_is_forbidden_on_admin_routes(
    user: AuthenticatedClient, operation: str
) -> None:
    _problem(OPERATIONS[operation](user), 403, "forbidden")


@pytest.mark.parametrize("operation", EITHER_KEY)
def test_the_admin_key_opens_the_other_routes_too(
    admin: AuthenticatedClient, operation: str
) -> None:
    assert OPERATIONS[operation](admin).status_code == 200


def test_ingest_job_is_idempotent_and_pages_its_failures(admin: AuthenticatedClient) -> None:
    accepted = create_ingest_job.sync_detailed(client=admin, body=JOB, idempotency_key="job-1")
    assert accepted.status_code == 202
    assert isinstance(accepted.parsed, IngestJobAccepted)
    job_id = accepted.parsed.job_id
    assert accepted.headers["Location"] == f"/v1/ingest-jobs/{job_id}"

    replay = create_ingest_job.sync(client=admin, body=JOB, idempotency_key="job-1")
    assert isinstance(replay, IngestJobAccepted)
    assert replay.job_id == job_id
    other = IngestJobRequest(ciks=[789019], form_types=["10-K"], since=date(2024, 1, 1))
    reused = create_ingest_job.sync_detailed(client=admin, body=other, idempotency_key="job-1")
    _problem(reused, 422, "idempotency_key_reused")

    first = get_ingest_job.sync(job_id, client=admin, limit=2)
    assert isinstance(first, IngestJob)
    assert (first.status, first.counts.failed, first.request.ciks) == (
        "partially_failed",
        3,
        [320193],
    )
    assert isinstance(first.failures.next_cursor, str)
    rest = get_ingest_job.sync(job_id, client=admin, cursor=first.failures.next_cursor)
    assert isinstance(rest, IngestJob)
    assert rest.failures.next_cursor is None
    numbers = [f.accession_number for f in first.failures.items + rest.failures.items]
    assert len(first.failures.items) == 2
    assert len(set(numbers)) == 3


def test_unknown_ingest_job_is_not_found(admin: AuthenticatedClient) -> None:
    _problem(get_ingest_job.sync_detailed(uuid4(), client=admin), 404, "not_found")


def test_a_missing_idempotency_key_points_at_the_header(admin: AuthenticatedClient) -> None:
    response = create_ingest_job.sync_detailed(client=admin, body=JOB, idempotency_key="")
    problem = _problem(response, 422, "validation_failed")
    assert isinstance(problem.errors, list)
    assert [error.pointer for error in problem.errors] == ["/header/Idempotency-Key"]


def test_companies_page_by_cursor(user: AuthenticatedClient) -> None:
    tickers: list[str] = []
    cursor: str | Unset = UNSET
    while True:
        page = list_companies.sync(client=user, limit=2, cursor=cursor)
        assert isinstance(page, CompanyPage)
        tickers += [company.ticker for company in page.items]
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    assert tickers == ["AAPL", "MSFT", "NVDA"]


def test_filings_filter_and_page(user: AuthenticatedClient) -> None:
    first = list_filings.sync(client=user, cik=320193, limit=1)
    assert isinstance(first, FilingPage)
    assert [(f.form_type, f.filed_on) for f in first.items] == [("10-K", date(2025, 10, 31))]
    rest = list_filings.sync(client=user, cik=320193, limit=1, cursor=first.next_cursor)
    assert isinstance(rest, FilingPage)
    assert [f.form_type for f in rest.items] == ["10-Q"]
    assert rest.next_cursor is None
    annual = list_filings.sync(client=user, form_type="10-K")
    assert isinstance(annual, FilingPage)
    assert {f.cik for f in annual.items} == {320193, 789019}


def test_search_pages_by_score_then_chunk_id(user: AuthenticatedClient) -> None:
    first = search.sync(client=user, q="supplier risk", limit=2)
    assert isinstance(first, SearchPage)
    assert not first.degraded
    assert [(hit.chunk_id, hit.score) for hit in first.items] == [("c-1", 0.91), ("c-2", 0.85)]
    rest = search.sync(client=user, q="supplier risk", limit=2, cursor=first.next_cursor)
    assert isinstance(rest, SearchPage)
    assert [hit.chunk_id for hit in rest.items] == ["c-3"]
    assert rest.next_cursor is None


def test_answer_cites_a_fact_or_a_chunk(user: AuthenticatedClient) -> None:
    answer = create_answer.sync(client=user, body=QUESTION)
    assert isinstance(answer, Answer)
    assert [(c.fact_id, c.chunk_id) for c in answer.citations] == [("f-1", None), (None, "c-1")]
    assert (answer.degraded, answer.usage.input_tokens, answer.usage.cost_usd) == (False, 1200, 0)


def test_streamed_answer_ends_with_the_whole_answer(user: AuthenticatedClient) -> None:
    plain = create_answer.sync(client=user, body=QUESTION)
    assert isinstance(plain, Answer)
    response = stream_answer.sync_detailed(client=user, body=QUESTION)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    *deltas, last = _events(response)
    assert {event["type"] for event in deltas} == {"delta"}
    assert "".join(event["text"] for event in deltas) == plain.answer
    assert last == {"type": "completed", "answer": plain.to_dict()}


def test_a_failure_mid_stream_arrives_as_a_failed_event(
    user: AuthenticatedClient, fake: Any
) -> None:
    fake.fail_mid_stream = UpstreamError("The model provider timed out.")
    response = stream_answer.sync_detailed(client=user, body=QUESTION)
    assert response.status_code == 200  # the stream had already started
    first, *_, last = _events(response)
    assert first["type"] == "delta"
    assert last["type"] == "failed"
    assert last["problem"] == {
        "type": "about:blank",
        "title": "Bad Gateway",
        "status": 502,
        "detail": "The model provider timed out.",
        "code": "upstream_error",
    }


def test_rate_limit_problem_carries_the_rate_limit_headers(
    user: AuthenticatedClient, fake: Any
) -> None:
    fake.fail_with = RateLimitedError("Too many requests.", retry_after_s=7, limit=60)
    response = list_companies.sync_detailed(client=user)
    _problem(response, 429, "rate_limited")
    assert response.headers["Retry-After"] == "7"
    assert response.headers["RateLimit-Limit"] == "60"
    assert response.headers["RateLimit-Remaining"] == "0"


@pytest.mark.parametrize("operation", ["create_answer", "stream_answer"])
def test_overload_is_a_503_with_retry_after_even_for_streams(
    user: AuthenticatedClient, fake: Any, operation: str
) -> None:
    fake.fail_with = OverloadedError("Too many answers in flight.", retry_after_s=3)
    response = OPERATIONS[operation](user)
    _problem(response, 503, "overloaded")
    assert response.headers["Retry-After"] == "3"


class _Hget:
    """Redis for budget.check: today's tokens, or a Redis error when there are none."""

    def __init__(self, used: bytes | None = None) -> None:
        self.used = used

    async def hget(self, key: str, field: str) -> bytes | None:
        if self.used is None:
            raise RedisError("Redis is down.")
        return self.used


class _Begun:
    """An engine whose transaction gives the job a new id and takes any statement."""

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[Any]:
        async def execute(statement: Any) -> Any:
            return SimpleNamespace(scalar_one_or_none=uuid4)

        yield SimpleNamespace(execute=execute)


class _Refused:
    """A discover queue whose broker refuses every publish."""

    def publish(self, job_id: Any, ciks: Any) -> None:
        raise OSError("Connection refused.")


async def _raise(exc: FilingLensError) -> None:
    raise exc


async def _admitted_past_the_cap(_: pytest.MonkeyPatch) -> None:
    pipeline = Answerer(cast(Any, None), cast(Any, None), cast(Any, None), max_inflight=0)
    pipeline.admit(schemas.AnswerRequest(question="What was revenue?"))


async def _next_page_while_the_reranker_is_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    async def degraded(*args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(hits=[], degraded=True)

    monkeypatch.setattr(backend, "search", degraded)
    settings = SimpleNamespace(
        retrieval_embedding_column="embedding",
        rerank_model="reranker",
        rerank_candidates=50,
        rerank_max_tokens=512,
        rerank_timeout_ms=500,
    )
    cursor = encode_cursor(SearchKey(score=1.0, chunk_id="c-1", index_version="embedding"))
    live = LiveBackend(cast(Any, None), cast(Any, None), cast(Any, settings))
    await live.search("revenue", 10, cursor)


async def _job_the_broker_refused(_: pytest.MonkeyPatch) -> None:
    request = schemas.IngestJobRequest(
        ciks=[320193], form_types=[schemas.FormType.FORM_10K], since=date(2024, 1, 1)
    )
    await LiveBackend(cast(Any, _Begun()), cast(Any, _Refused())).create_ingest_job(request, "k")


# Every 503 the API sends, raised by the production code that raises it, and its Retry-After:
# seconds to wait, or None when waiting will not help (the header is then absent).
type Raise = Callable[[pytest.MonkeyPatch], Coroutine[Any, Any, object]]
UNAVAILABLE: list[tuple[str, Raise, str | None]] = [
    (
        "ai switched off",
        lambda _: budget.check(cast(Any, None), enabled=False, daily_tokens=1),
        None,
    ),
    (
        "ai switched off, no answerer",
        lambda _: LiveBackend(cast(Any, None), cast(Any, None)).stream_answer(
            schemas.AnswerRequest(question="What was revenue?")
        ),
        None,
    ),
    (
        "budget used up",
        lambda _: budget.check(cast(Any, _Hget(b"5")), enabled=True, daily_tokens=5),
        "until 00:00 UTC",
    ),
    (
        "budget cannot be checked",
        lambda _: budget.check(cast(Any, _Hget()), enabled=True, daily_tokens=5),
        "30",
    ),
    ("providers rate limited", lambda _: _raise(_final(failure("groq", 429))), "60"),
    ("providers ask to wait", lambda _: _raise(_final(failure("groq", 429, "7"))), "7"),
    ("last model out of credits", lambda _: _raise(_final(failure("nvidia", 402))), None),
    ("last model retired", lambda _: _raise(_final(failure("nvidia", 410))), None),
    ("last model refused the key", lambda _: _raise(_final(failure("nvidia", 401))), None),
    ("too many answers in progress", _admitted_past_the_cap, "2"),
    ("reranker busy on a later page", _next_page_while_the_reranker_is_busy, "1"),
    ("broker refused or unreachable", _job_the_broker_refused, "5"),
]


@pytest.mark.parametrize(
    ("raise_it", "retry_after"),
    [row[1:] for row in UNAVAILABLE],
    ids=[row[0] for row in UNAVAILABLE],
)
def test_a_503_carries_retry_after_only_when_waiting_helps(
    user: AuthenticatedClient,
    fake: Any,
    monkeypatch: pytest.MonkeyPatch,
    raise_it: Raise,
    retry_after: str | None,
) -> None:
    with pytest.raises(FilingLensError) as raised:
        asyncio.run(raise_it(monkeypatch))
    fake.fail_with = raised.value
    response = create_answer.sync_detailed(client=user, body=QUESTION)
    _problem(response, 503, raised.value.code)
    if retry_after is None:
        assert "Retry-After" not in response.headers
    elif retry_after == "until 00:00 UTC":
        assert 0 < int(response.headers["Retry-After"]) <= 86_400
    else:
        assert response.headers["Retry-After"] == retry_after


def test_graphql_takes_post_only_so_a_get_of_answer_spends_nothing(
    server_url: str, fake: Any, api_key: str
) -> None:
    taken: list[str] = []

    async def answer_limits() -> None:  # records the answer token a real limit would take
        taken.append("answers")

    kept = app.dependency_overrides[answer_limits_for]
    app.dependency_overrides[answer_limits_for] = lambda: answer_limits
    query = '{ answer(question: "What was revenue?") { answer } }'
    headers = {"X-API-Key": api_key}
    try:
        got = httpx2.get(f"{server_url}/graphql", params={"query": query}, headers=headers)
        assert got.status_code == 405
        assert got.json()["code"] == "method_not_allowed"
        assert (fake.answered, taken) == (0, [])
        posted = httpx2.post(f"{server_url}/graphql", json={"query": query}, headers=headers)
        assert posted.status_code == 200
        assert posted.json()["data"]["answer"]["answer"]
        assert (fake.answered, taken) == (1, ["answers"])
    finally:
        app.dependency_overrides[answer_limits_for] = kept


def test_graphql_mounts_one_post_route_and_no_websocket_route() -> None:
    routes = graphql_router.routes
    assert [sorted(getattr(route, "methods", None) or []) for route in routes] == [["POST"]]
    assert not [route for route in routes if isinstance(route, WebSocketRoute)]


def test_validation_problem_points_at_each_bad_input(user: AuthenticatedClient) -> None:
    response = list_companies.sync_detailed(client=user, limit=101)
    problem = _problem(response, 422, "validation_failed")
    assert isinstance(problem.errors, list)
    assert [error.pointer for error in problem.errors] == ["/query/limit"]


def test_an_unusable_cursor_is_a_bad_request(user: AuthenticatedClient) -> None:
    _problem(list_companies.sync_detailed(client=user, cursor="not-a-cursor"), 400, "invalid_input")


def test_unexpected_errors_hide_their_details_and_keep_the_connection(
    user: AuthenticatedClient, fake: Any
) -> None:
    fake.fail_with = RuntimeError("password=hunter2 leaked from a driver")
    with pytest.raises(errors.UnexpectedStatus) as exc:  # 500 is deliberately not in the spec
        list_companies.sync_detailed(client=user)
    assert exc.value.status_code == 500
    assert json.loads(exc.value.content) == {
        "type": "about:blank",
        "title": "Internal Server Error",
        "status": 500,
        "code": "internal",
    }
    fake.fail_with = None
    for _ in range(5):  # same pooled connection; it used to be dropped after a 500
        assert list_companies.sync_detailed(client=user).status_code == 200


def test_graphql_operations_through_the_generated_client(graphql: GraphqlClient) -> None:
    companies = graphql.companies(first=2).companies
    assert [edge.node.ticker for edge in companies.edges] == ["AAPL", "MSFT"]
    assert companies.page_info.has_next_page
    rest = graphql.companies(first=2, after=companies.page_info.end_cursor).companies
    assert [edge.node.ticker for edge in rest.edges] == ["NVDA"]

    filings = graphql.filings(first=1, chunks=2, facts=1, cik=320193, form_type=FormType.FORM_10K)
    filing = filings.filings.edges[0].node
    assert (filing.form_type, filing.fiscal_period) == (FormType.FORM_10K, FiscalPeriod.FY)
    assert filing.filed_on == date(2025, 10, 31)
    assert [section.item for section in filing.sections] == ["1A", "7"]
    assert [edge.node.id for edge in filing.chunks.edges] == ["c-1", "c-2"]
    assert filing.chunks.page_info.has_next_page
    assert [edge.node.concept for edge in filing.facts.edges] == ["us-gaap:Revenues"]

    answer = graphql.answer(question="What was revenue in fiscal 2025?").answer
    assert [(c.fact_id, c.chunk_id) for c in answer.citations] == [("f-1", None), (None, "c-1")]


def test_graphql_errors_carry_a_code_and_hide_unexpected_details(
    graphql: GraphqlClient, fake: Any
) -> None:
    fake.fail_with = RateLimitedError("Too many requests.")
    with pytest.raises(GraphQLClientGraphQLMultiError) as limited:
        graphql.companies(first=2)
    assert [(e.message, e.extensions) for e in limited.value.errors] == [
        ("Too many requests.", {"code": "rate_limited"})
    ]
    fake.fail_with = RuntimeError("password=hunter2 leaked from a driver")
    with pytest.raises(GraphQLClientGraphQLMultiError) as unexpected:
        graphql.companies(first=2)
    assert [(e.message, e.extensions) for e in unexpected.value.errors] == [
        ("Unexpected error.", {"code": "internal"})
    ]


def test_graphql_sources_keep_the_order_given_and_link_each_citation(
    graphql: GraphqlClient,
) -> None:
    sources = graphql.sources(chunk_ids=["c-2", "unknown", "c-1", "c-2"], fact_ids=["f-1"])
    assert [
        (chunk.id, chunk.section.item, chunk.filing.accession_number, chunk.filing.company.ticker)
        for chunk in sources.chunks
    ] == [
        ("c-2", "7", "0000320193-25-000079", "AAPL"),
        ("c-1", "1A", "0000320193-25-000079", "AAPL"),
    ]
    assert [(fact.id, fact.company.ticker) for fact in sources.facts] == [("f-1", "AAPL")]


IDS: list[tuple[str, list[str], int | None]] = [
    ("none", [], 0),
    ("20, the most it takes", ["c-1", "f-1"] * 10, 1),
    ("one of 64 characters", ["c" * 64], 0),
    ("one with another control character", ["c\x01"], 0),
    ("21", ["c-1"] * 21, None),
    ("one of 65 characters", ["c" * 65], None),
    ("an empty one", [""], None),
    ("one with a NUL", ["c\x00"], None),
]


@pytest.mark.parametrize("kind", ["chunks", "facts"])
@pytest.mark.parametrize(("ids", "found"), [row[1:] for row in IDS], ids=[row[0] for row in IDS])
def test_graphql_lookups_take_0_to_20_ids_of_1_to_64_characters(
    graphql: GraphqlClient, kind: str, ids: list[str], found: int | None
) -> None:
    chunk_ids, fact_ids = (ids, []) if kind == "chunks" else ([], ids)
    if found is None:
        with pytest.raises(GraphQLClientGraphQLMultiError) as refused:
            graphql.sources(chunk_ids=chunk_ids, fact_ids=fact_ids)
        assert [(e.message, e.extensions) for e in refused.value.errors] == [
            (
                "ids takes at most 20 ids, each 1 to 64 characters with no NUL.",
                {"code": "invalid_input"},
            )
        ]
    else:
        sources = graphql.sources(chunk_ids=chunk_ids, fact_ids=fact_ids)
        assert len(sources.chunks) + len(sources.facts) == found


def test_graphql_links_resolve_off_the_citation_path_too(server_url: str, api_key: str) -> None:
    # Within depth 6, a cited chunk's filing is where its listed chunks and facts are reached.
    query = """{ filings(first: 1) { edges { node { company { ticker } } } }
        chunks(ids: ["c-2"]) { filing {
          chunks(first: 1) { edges { node { section { item } filing { accessionNumber } } } }
          facts(first: 1) { edges { node { company { ticker } } } } } } }"""
    response = httpx2.post(
        f"{server_url}/graphql", json={"query": query}, headers={"X-API-Key": api_key}
    )
    body = response.json()
    assert "errors" not in body, body["errors"]
    filing = body["data"]["filings"]["edges"][0]["node"]
    cited = body["data"]["chunks"][0]["filing"]
    chunk = cited["chunks"]["edges"][0]["node"]
    fact = cited["facts"]["edges"][0]["node"]
    assert (
        filing["company"]["ticker"],
        chunk["section"]["item"],
        chunk["filing"]["accessionNumber"],
        fact["company"]["ticker"],
    ) == ("AAPL", "1A", "0000320193-25-000079", "AAPL")


def test_graphql_limits_pass_the_deepest_query_the_web_needs(graphql: GraphqlClient) -> None:
    """Coverage (B2's coverage page and demo export) reaches depth 6 with no alias: the edge."""
    coverage = graphql.coverage(first=1).companies
    assert coverage.page_info.has_next_page
    assert [edge.node.accession_number for edge in coverage.edges[0].node.filings.edges] == [
        "0000320193-25-000079",
        "0000320193-25-000073",
    ]


PAST_THE_LIMITS: list[tuple[str, str, str]] = [
    (
        "depth 7: Coverage plus each filing's company",
        "query TooDeep { companies(first: 1) { edges { node { filings(first: 1) { edges { node {"
        " company { ticker } } } } } } } }",
        "'TooDeep' exceeds maximum operation depth of 6",
    ),
    (
        "one alias",
        "{ first: companies(first: 1) { edges { node { ticker } } } }",
        "1 aliases found. Allowed: 0",
    ),
]


@pytest.mark.parametrize(
    ("query", "message"),
    [row[1:] for row in PAST_THE_LIMITS],
    ids=[row[0] for row in PAST_THE_LIMITS],
)
def test_graphql_refuses_a_query_past_its_limits_before_any_resolver_runs(
    server_url: str, api_key: str, fake: Any, query: str, message: str
) -> None:
    fake.fail_with = RuntimeError("a resolver ran")  # any backend call would add an internal error
    response = httpx2.post(
        f"{server_url}/graphql", json={"query": query}, headers={"X-API-Key": api_key}
    )
    body = response.json()
    assert (body.get("data"), [error["message"] for error in body["errors"]]) == (None, [message])


DISABLED = "GraphQL introspection has been disabled, but the requested query contained the field"
INTROSPECTION: list[tuple[str, str, str | None]] = [
    ("__schema", "{ __schema { description } }", f"{DISABLED} '__schema'."),
    ("__type", '{ __type(name: "Query") { name } }', f"{DISABLED} '__type'."),
    ("__typename, which stays", "{ __typename }", None),
]


@pytest.mark.parametrize(
    ("query", "message"), [row[1:] for row in INTROSPECTION], ids=[row[0] for row in INTROSPECTION]
)
def test_graphql_refuses_introspection_before_any_resolver_runs(
    server_url: str, api_key: str, fake: Any, query: str, message: str | None
) -> None:
    fake.fail_with = RuntimeError("a resolver ran")
    response = httpx2.post(
        f"{server_url}/graphql", json={"query": query}, headers={"X-API-Key": api_key}
    )
    body = response.json()
    if message is None:
        assert body == {"data": {"__typename": "Query"}}
    else:
        assert (body.get("data"), [error["message"] for error in body["errors"]]) == (
            None,
            [message],
        )


# Postgres refuses a NUL in text; another control character goes through, as it always did.
CONTROL = [("\x00", True), ("\x01", False)]
CONTROL_IDS = ["NUL", "another control character"]


@pytest.mark.parametrize(("char", "refused"), CONTROL, ids=CONTROL_IDS)
def test_a_nul_in_the_search_text_is_refused_before_the_backend(
    user: AuthenticatedClient,
    fake: Any,
    monkeypatch: pytest.MonkeyPatch,
    char: str,
    refused: bool,
) -> None:
    searched: list[str] = []
    real = fake.search

    async def spy(q: str, *args: Any, **kwargs: Any) -> Any:
        searched.append(q)
        return await real(q, *args, **kwargs)

    monkeypatch.setattr(fake, "search", spy)
    response = search.sync_detailed(client=user, q=f"rev{char}enue")
    if refused:
        problem = _problem(response, 422, "validation_failed")
        assert isinstance(problem.errors, list)
        assert [error.pointer for error in problem.errors] == ["/query/q"]
        assert searched == []
    else:
        assert response.status_code == 200
        assert searched == [f"rev{char}enue"]


@pytest.mark.parametrize(("char", "refused"), CONTROL, ids=CONTROL_IDS)
def test_a_nul_in_a_question_is_refused_before_the_backend(
    user: AuthenticatedClient, graphql: GraphqlClient, fake: Any, char: str, refused: bool
) -> None:
    question = f"What{char} was revenue?"
    rest = create_answer.sync_detailed(client=user, body=AnswerRequest(question=question))
    if refused:
        problem = _problem(rest, 422, "validation_failed")
        assert isinstance(problem.errors, list)
        assert [error.pointer for error in problem.errors] == ["/body/question"]
        with pytest.raises(GraphQLClientGraphQLMultiError) as over_graphql:
            graphql.answer(question=question)
        assert [error.extensions for error in over_graphql.value.errors] == [
            {"code": "invalid_input"}
        ]
        assert fake.answered == 0
    else:
        assert rest.status_code == 200
        assert graphql.answer(question=question).answer.answer
        assert fake.answered == 2


FACTS_BY_CONCEPT = """query Facts($concept: String) { filings(first: 1) { edges { node {
    facts(concept: $concept) { edges { node { id } } } } } } }"""


@pytest.mark.parametrize(
    ("concept", "found"),
    [("us-gaap:Revenues\x00", None), ("us-gaap:Revenues\x01", []), ("us-gaap:Revenues", ["f-1"])],
    ids=["NUL", "another control character", "a concept"],
)
def test_a_nul_in_a_concept_is_refused_before_the_backend(
    server_url: str,
    api_key: str,
    fake: Any,
    monkeypatch: pytest.MonkeyPatch,
    concept: str,
    found: list[str] | None,
) -> None:
    listed: list[str | None] = []
    real = fake.list_facts

    async def spy(*args: Any, concept: str | None = None, **kwargs: Any) -> Any:
        listed.append(concept)
        return await real(*args, concept=concept, **kwargs)

    monkeypatch.setattr(fake, "list_facts", spy)
    body = httpx2.post(
        f"{server_url}/graphql",
        json={"query": FACTS_BY_CONCEPT, "variables": {"concept": concept}},
        headers={"X-API-Key": api_key},
    ).json()
    if found is None:
        assert [(error["message"], error["extensions"]) for error in body.get("errors", [])] == [
            ("concept must not hold a NUL character.", {"code": "invalid_input"})
        ]
        assert listed == []
    else:
        edges = body["data"]["filings"]["edges"][0]["node"]["facts"]["edges"]
        assert [edge["node"]["id"] for edge in edges] == found


@pytest.mark.parametrize(
    ("year", "refused"),
    [(40000, True), (1992, True), (2025, False)],
    ids=["past SMALLINT", "before EDGAR", "a fiscal year"],
)
def test_graphql_refuses_a_fiscal_year_outside_rest_bounds_before_the_backend(
    server_url: str,
    api_key: str,
    fake: Any,
    monkeypatch: pytest.MonkeyPatch,
    year: int,
    refused: bool,
) -> None:
    listed: list[int | None] = []
    real = fake.list_filings

    async def spy(*args: Any, **kwargs: Any) -> Any:
        listed.append(kwargs.get("fiscal_year"))
        return await real(*args, **kwargs)

    monkeypatch.setattr(fake, "list_filings", spy)
    query = "query F($y: Int) { filings(fiscalYear: $y, first: 1) { edges { node { cik } } } }"
    body = httpx2.post(
        f"{server_url}/graphql",
        json={"query": query, "variables": {"y": year}},
        headers={"X-API-Key": api_key},
    ).json()
    if refused:
        assert [(error["message"], error["extensions"]) for error in body.get("errors", [])] == [
            ("fiscalYear must be between 1993 and 2100.", {"code": "invalid_input"})
        ]
        assert listed == []
    else:
        assert (listed, len(body["data"]["filings"]["edges"])) == ([2025], 1)


def test_concurrent_readyz_calls_share_one_round_of_checks(
    server_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    pings: list[str] = []

    def ping_rabbitmq(url: str) -> None:
        pings.append(url)
        time.sleep(0.3)  # long enough for every request to arrive during the round
        raise OSError("unreachable")

    monkeypatch.setattr(main, "_ping_rabbitmq", ping_rabbitmq)
    monkeypatch.setattr(app.state, "ready", None, raising=False)  # forget an earlier round
    with ThreadPoolExecutor(5) as pool:
        codes = list(pool.map(lambda _: httpx2.get(f"{server_url}/readyz").status_code, range(5)))
    assert (codes, len(pings)) == ([503] * 5, 1)
