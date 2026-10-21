"""REST v1. Every route declares its response model and the problem responses it can send."""

import asyncio
import secrets
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, Security
from fastapi.security import APIKeyHeader
from fastapi.sse import EventSourceResponse
from pydantic import SecretStr

from filinglens_api import limits
from filinglens_api.backend import AnswerEvents, BackendDep
from filinglens_api.limits import answer_limits, rate_limit, timed_answer
from filinglens_api.problems import problem_doc, problem_for, problems
from filinglens_api.schemas import (
    Answer,
    AnswerEvent,
    AnswerFailed,
    AnswerRequest,
    CompanyPage,
    FilingPage,
    FormType,
    IngestJob,
    IngestJobAccepted,
    IngestJobRequest,
    NoNul,
    SearchPage,
)
from filinglens_core.errors import (
    FilingLensError,
    ForbiddenError,
    UnauthorizedError,
    UpstreamError,
)

# One header, two schemes, so the spec can say which key each route takes.
api_key = APIKeyHeader(
    name="X-API-Key",
    scheme_name="ApiKey",
    description="API_KEY. Opens every route except the admin routes; ADMIN_API_KEY works too.",
    auto_error=False,
)
admin_key = APIKeyHeader(
    name="X-API-Key",
    scheme_name="AdminApiKey",
    description="ADMIN_API_KEY. The only key for the admin routes (/v1/ingest-jobs).",
    auto_error=False,
)


def _matches(key: str | None, expected: SecretStr) -> bool:
    return key is not None and secrets.compare_digest(
        key.encode(), expected.get_secret_value().encode()
    )


def require_api_key(
    request: Request,
    key: Annotated[str | None, Security(api_key)],
    _: Annotated[str | None, Security(admin_key)],  # lists AdminApiKey as an alternative
) -> None:
    settings = request.app.state.settings
    if not (_matches(key, settings.api_key) or _matches(key, settings.admin_api_key)):
        raise UnauthorizedError("Missing or invalid API key.")


def require_admin_key(request: Request, key: Annotated[str | None, Security(admin_key)]) -> None:
    settings = request.app.state.settings
    if _matches(key, settings.admin_api_key):
        return
    if _matches(key, settings.api_key):
        raise ForbiddenError("This route needs the admin API key.")
    raise UnauthorizedError("Missing or invalid API key.")


def refuse_browsers(request: Request) -> None:
    """Only servers call this API; a browser page's request carries Origin, `null` included."""
    if "origin" in request.headers:
        raise ForbiddenError("Browsers cannot call this API; use the web app.")


COMMON = problems(401, 422, 429, 503)
# Keys first, then the per-key rate limit.
admin = APIRouter(
    prefix="/v1",
    dependencies=[Depends(require_admin_key), Depends(rate_limit)],
    responses=COMMON | problems(403),
)
router = APIRouter(
    prefix="/v1", dependencies=[Depends(require_api_key), Depends(rate_limit)], responses=COMMON
)

Limit = Annotated[int, Query(ge=1, le=100, description="Page size (at most 100).")]
Cursor = Annotated[
    str | None, Query(max_length=1000, description="`next_cursor` from the previous page.")
]


@admin.post(
    "/ingest-jobs",
    tags=["ingest"],
    status_code=202,
    response_model=IngestJobAccepted,
    response_description="Job accepted.",
    responses={
        202: {"headers": {"Location": {"description": "Job URL.", "schema": {"type": "string"}}}},
        **problems(413),
        422: problem_doc(
            "Invalid request (validation_failed), or an Idempotency-Key already used with a"
            " different body (idempotency_key_reused)."
        ),
    },
)
async def create_ingest_job(
    body: IngestJobRequest,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=255,
            description="Unique per job. A retry with the same key and body gets the same job.",
        ),
    ],
    response: Response,
    backend: BackendDep,
) -> IngestJobAccepted:
    """Queue ingestion of the companies' filings. Admin route: ADMIN_API_KEY only."""
    job_id = await backend.create_ingest_job(body, idempotency_key)
    response.headers["Location"] = f"/v1/ingest-jobs/{job_id}"
    return IngestJobAccepted(job_id=job_id)


@admin.get(
    "/ingest-jobs/{job_id}",
    tags=["ingest"],
    response_model=IngestJob,
    responses=problems(400, 404),
)
async def get_ingest_job(
    job_id: UUID, backend: BackendDep, limit: Limit = 20, cursor: Cursor = None
) -> IngestJob:
    """Per-filing status counts and a page of failures (limit and cursor page the failures).

    Admin route: ADMIN_API_KEY only.
    """
    return await backend.get_ingest_job(job_id, limit, cursor)


@router.get("/companies", tags=["catalog"], response_model=CompanyPage, responses=problems(400))
async def list_companies(
    backend: BackendDep, limit: Limit = 20, cursor: Cursor = None
) -> CompanyPage:
    """Tracked companies in CIK order. Either key."""
    return await backend.list_companies(limit, cursor)


@router.get("/filings", tags=["catalog"], response_model=FilingPage, responses=problems(400))
async def list_filings(
    backend: BackendDep,
    limit: Limit = 20,
    cursor: Cursor = None,
    cik: Annotated[int | None, Query(ge=1, le=9_999_999_999)] = None,
    form_type: FormType | None = None,
    fiscal_year: Annotated[int | None, Query(ge=1993, le=2100)] = None,
) -> FilingPage:
    """Ingested filings, newest first. Either key."""
    return await backend.list_filings(
        limit, cursor, cik=cik, form_type=form_type, fiscal_year=fiscal_year
    )


@router.get("/search", tags=["search"], response_model=SearchPage, responses=problems(400, 409))
async def search(
    q: Annotated[NoNul, Query(min_length=1, max_length=500, description="Search text.")],
    backend: BackendDep,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size (at most 100).")] = 10,
    cursor: Cursor = None,
    cik: Annotated[int | None, Query(ge=1, le=9_999_999_999, description="One company.")] = None,
    fiscal_year: Annotated[int | None, Query(ge=1993, le=2100)] = None,
) -> SearchPage:
    """Hybrid search over the text of indexed filings. Either key.

    Vector and full-text matches are fused and reranked. The cursor holds the last hit's score
    and chunk id and the index version, so later pages come from the same index; once the index
    changes (a new embedding model), a cursor gets 409 and the search starts again without one.
    """
    return await backend.search(q, limit, cursor, cik=cik, fiscal_year=fiscal_year)


@router.post(
    "/answers",
    tags=["answers"],
    response_model=Answer,
    dependencies=[Depends(answer_limits)],
    responses=problems(413, 502),
)
async def create_answer(body: AnswerRequest, backend: BackendDep) -> Answer:
    """Answer a question from the filings, citing a chunk or an XBRL fact. Either key.

    At most 10 a minute per key, and 30 s each (then 502).
    """
    return await timed_answer(backend, body)


async def _answer_events(body: AnswerRequest, backend: BackendDep) -> AsyncIterator[AnswerEvents]:
    # A dependency runs before the response starts, so admission errors keep their status code.
    # Its teardown runs after the response, so the answer's in-flight slot comes back even when
    # the client leaves before the first event.
    events = await backend.stream_answer(body)
    try:
        yield events
    finally:
        await events.aclose()


# FastAPI reads a stream's item model from the return annotation, not from response_model.
@router.post(
    "/answers/stream",
    tags=["answers"],
    response_class=EventSourceResponse,
    response_description="Server-Sent Events, each carrying one AnswerEvent as JSON.",
    dependencies=[Depends(answer_limits)],
    responses=problems(413, 502),
)
async def stream_answer(
    events: Annotated[AnswerEvents, Depends(_answer_events, scope="request")],
) -> AsyncIterator[AnswerEvent]:
    """POST /v1/answers as Server-Sent Events. Either key; shares the answers limits.

    `delta` events carry the answer's text as the model writes it, then one `completed` event
    carries the whole answer after validation. The two agree unless validation rewrote the draft,
    and then the completed answer has warnings and replaces the streamed text. An error after the
    stream has started arrives as a `failed` event with a problem, and so does a stream still
    running after 30 s.
    """
    deadline = asyncio.get_running_loop().time() + limits.ANSWER_TIMEOUT_S
    try:
        while True:
            async with asyncio.timeout_at(deadline):  # never around a yield
                event = await anext(events)
            yield event
    except StopAsyncIteration:
        return
    except TimeoutError:
        timeout = UpstreamError(f"No answer within {limits.ANSWER_TIMEOUT_S} s.")
        yield AnswerFailed(problem=problem_for(timeout))
    except FilingLensError as exc:
        yield AnswerFailed(problem=problem_for(exc))
