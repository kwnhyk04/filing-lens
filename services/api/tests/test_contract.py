"""Every operation through the generated clients, against the app served by uvicorn.

The app runs over an in-memory backend, so these tests pin the contract (paths, parameters,
bodies, status codes, headers and problem shapes), not the data layer.
"""

import json
from collections.abc import Callable
from datetime import date
from typing import Any
from uuid import uuid4

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

from filinglens_core.errors import OverloadedError, RateLimitedError, UpstreamError

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
