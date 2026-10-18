"""RFC 9457 problem details: the exception handlers and the OpenAPI responses that document them."""

from collections.abc import Mapping, Sequence
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from filinglens_api.schemas import FieldError, Problem
from filinglens_core.errors import FilingLensError, RateLimitedError

MEDIA_TYPE = "application/problem+json"


def problem(
    status: int, code: str, detail: str | None = None, errors: list[FieldError] | None = None
) -> Problem:
    return Problem(
        title=HTTPStatus(status).phrase, status=status, detail=detail, code=code, errors=errors
    )


def problem_for(exc: FilingLensError) -> Problem:
    return problem(exc.http_status, exc.code, str(exc) or None)


def _headers(exc: FilingLensError) -> dict[str, str]:
    headers: dict[str, str] = {}
    if exc.http_status == 401:
        headers["WWW-Authenticate"] = "APIKey"  # RFC 9110 requires a challenge on 401
    if exc.retry_after_s is not None:
        headers["Retry-After"] = str(exc.retry_after_s)
    if isinstance(exc, RateLimitedError) and exc.limit is not None:
        headers["RateLimit-Limit"] = str(exc.limit)
        headers["RateLimit-Remaining"] = "0"
    return headers


def _response(body: Problem, headers: Mapping[str, str] | None = None) -> JSONResponse:
    return JSONResponse(body.model_dump(), body.status, headers=headers, media_type=MEDIA_TYPE)


def _pointer(location: Sequence[str | int]) -> str:
    """JSON Pointer such as /body/ciks/0 or /query/limit."""
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in location)


async def _taxonomy_error(_: Request, exc: FilingLensError) -> JSONResponse:
    return _response(problem_for(exc), _headers(exc))


async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Inputs are left out on purpose: they may hold secrets.
    errors = [FieldError(detail=e["msg"], pointer=_pointer(e["loc"])) for e in exc.errors()]
    return _response(problem(422, "validation_failed", "The request is not valid.", errors))


def http_problem(exc: HTTPException) -> JSONResponse:
    """Framework errors, such as an unknown path (404), method (405) or a large body (413)."""
    phrase = HTTPStatus(exc.status_code).phrase
    detail = str(exc.detail) if exc.detail != phrase else None  # detail may be any JSON value
    code = phrase.lower().replace(" ", "_").replace("-", "_")
    return _response(problem(exc.status_code, code, detail), exc.headers)


async def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
    return http_problem(exc)


def internal_error() -> JSONResponse:
    """The 500 problem: no detail, so nothing about the failure leaks."""
    return _response(problem(500, "internal"))


def add_problem_handlers(app: FastAPI) -> None:
    """Unexpected exceptions are handled by the request-id middleware in main.py instead."""
    app.exception_handler(FilingLensError)(_taxonomy_error)
    app.exception_handler(RequestValidationError)(_validation_error)
    app.exception_handler(HTTPException)(_http_error)


def _int_header(description: str) -> dict[str, Any]:
    return {"description": description, "schema": {"type": "integer"}}


RETRY_AFTER = {"Retry-After": _int_header("Seconds to wait before retrying.")}


def problem_doc(description: str, headers: dict[str, Any] | None = None) -> dict[str, Any]:
    """An OpenAPI response whose body is a Problem."""
    doc: dict[str, Any] = {
        "description": description,
        "content": {MEDIA_TYPE: {"schema": {"$ref": "#/components/schemas/Problem"}}},
    }
    if headers:
        doc["headers"] = headers
    return doc


PROBLEMS: dict[int, dict[str, Any]] = {
    400: problem_doc("Unusable cursor (invalid_input). Start again without one."),
    401: problem_doc(
        "Missing or unknown API key (unauthorized).",
        {"WWW-Authenticate": {"description": "Always APIKey.", "schema": {"type": "string"}}},
    ),
    403: problem_doc("The normal API key on an admin route (forbidden). Send ADMIN_API_KEY."),
    404: problem_doc("No such resource (not_found)."),
    409: problem_doc(
        "The cursor came from a search index that has since changed (conflict). Search again"
        " without a cursor."
    ),
    413: problem_doc("Request body larger than 64 KB (request_entity_too_large)."),
    422: problem_doc("Invalid request (validation_failed); `errors` lists each input."),
    429: problem_doc(
        "Rate limit exhausted (rate_limited).",
        {
            "RateLimit-Limit": _int_header("Requests allowed per window."),
            "RateLimit-Remaining": _int_header("Requests left in this window (0)."),
            **RETRY_AFTER,
        },
    ),
    502: problem_doc("A model provider failed (upstream_error)."),
    503: problem_doc(
        "Overloaded (overloaded), or no model call can be made (ai_unavailable): AI_ENABLED=false,"
        " today's AI token budget used up or not checkable, rate-limited providers, or a last"
        " model that refused the key, has no credits or was retired.",
        {
            "Retry-After": _int_header(
                "Seconds to wait before retrying. Absent when waiting will not help: AI is"
                " switched off, or the last model refused the key, has no credits or was retired."
            )
        },
    ),
}


def problems(*statuses: int) -> dict[int | str, dict[str, Any]]:
    return {status: PROBLEMS[status] for status in statuses}
