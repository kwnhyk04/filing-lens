"""REST v1. Every route declares its response model and the problem responses it can send."""

import asyncio
import secrets
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, Security
from fastapi.security import APIKeyHeader
from fastapi.sse import EventSourceResponse
from opentelemetry import trace
from pydantic import SecretStr

from filinglens_api import limits
from filinglens_api.backend import AnswerEvents, BackendDep
from filinglens_api.limits import answer_limits, rate_limit, timed_answer
from filinglens_api.problems import problem_doc, problem_for, problems
from filinglens_api.recent import RecentDep, Stored
from filinglens_api.schemas import (
    Answer,
    AnswerCompleted,
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
    RecentAnswerPage,
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
SESSION = Header(
    alias="X-Session-ID",
    pattern=r"^[A-Za-z0-9_-]{22,64}$",
    description=(
        "The web's sign-in id. Answers are kept for that sign-in alone, and only for"
        " RECENT_ANSWERS_TTL_S (default 30 minutes)."
    ),
)
SessionId = Annotated[str, SESSION]
OptionalSessionId = Annotated[str | None, SESSION]


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


async def _replay(stored: Stored) -> AsyncGenerator[AnswerCompleted, None]:
    yield AnswerCompleted(answer=stored.answer, stored_at=stored.answered_at)


async def _answer_events(
    body: AnswerRequest,
    backend: BackendDep,
    recent: RecentDep,
    session_id: OptionalSessionId = None,
    fresh: Annotated[
        bool, Query(description="Answer again, even when this sign-in has the answer already.")
    ] = False,
) -> AsyncIterator[AnswerEvents]:
    # A dependency runs before the response starts, so admission errors keep their status code.
    # Its teardown runs after the response, so the answer's in-flight slot comes back even when
    # the client leaves before the first event.
    stored = await recent.get(session_id, body) if session_id is not None and not fresh else None
    if stored is not None:  # no in-flight slot and no model call
        trace.get_current_span().set_attribute("filinglens.answer.stored", True)
        events: AnswerEvents = _replay(stored)
    else:
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
    body: AnswerRequest,  # this name, as in _answer_events, keeps the body unembedded
    events: Annotated[AnswerEvents, Depends(_answer_events, scope="request")],
    recent: RecentDep,
    session_id: OptionalSessionId = None,
) -> AsyncIterator[AnswerEvent]:
    """POST /v1/answers as Server-Sent Events. Either key; shares the answers limits.

    `delta` events carry the answer's text as the model writes it, then one `completed` event
    carries the whole answer after validation. The two agree unless validation rewrote the draft,
    and then the completed answer has warnings and replaces the streamed text. An error after the
    stream has started arrives as a `failed` event with a problem, and so does a stream still
    running after 30 s.

    With `X-Session-ID`, a completed answer that is not refused or degraded is kept for that
    sign-in, and the same question again (same words, ignoring case, spacing, curly quotes and
    closing punctuation, over the same companies and years) gets it back at once as one
    `completed` event with `stored_at`, without a model call. `fresh=true` answers again.
    """
    deadline = asyncio.get_running_loop().time() + limits.ANSWER_TIMEOUT_S
    try:
        while True:
            async with asyncio.timeout_at(deadline):  # never around a yield
                event = await anext(events)
            if (
                session_id is not None
                and isinstance(event, AnswerCompleted)
                and event.stored_at is None  # a new answer, not one from earlier
                and not (event.answer.refused or event.answer.degraded)
            ):
                await recent.put(session_id, body, event.answer)  # past the deadline's reach
            yield event
    except StopAsyncIteration:
        return
    except TimeoutError:
        timeout = UpstreamError(f"No answer within {limits.ANSWER_TIMEOUT_S} s.")
        yield AnswerFailed(problem=problem_for(timeout))
    except FilingLensError as exc:
        yield AnswerFailed(problem=problem_for(exc))


@router.get(
    "/answers/recent", tags=["answers"], response_model=RecentAnswerPage, responses=problems(400)
)
async def list_recent_answers(
    session_id: SessionId, recent: RecentDep, limit: Limit = 10, cursor: Cursor = None
) -> RecentAnswerPage:
    """This sign-in's questions with their completed answers, newest first. Either key.

    At most 10 are kept, each for RECENT_ANSWERS_TTL_S; refused and degraded answers never are.
    """
    return await recent.page(session_id, limit, cursor)


@router.delete(
    "/answers/recent",
    tags=["answers"],
    status_code=204,
    response_class=Response,
    response_description="Forgotten.",
)
async def clear_recent_answers(session_id: SessionId, recent: RecentDep) -> None:
    """Forget this sign-in's answers; the web does at sign-out. Either key."""
    await recent.clear(session_id)
