"""FastAPI app: health probes, request ids, problem details, REST v1 and GraphQL."""

import asyncio
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import Depends, FastAPI, Request, Response
from kombu import Connection
from pydantic.json_schema import models_json_schema
from redis.asyncio import Redis
from strawberry.fastapi import GraphQLRouter

from filinglens_api import routes
from filinglens_api.backend import LiveBackend
from filinglens_api.graph import get_context, schema
from filinglens_api.problems import add_problem_handlers, internal_error
from filinglens_api.schemas import Health, Problem
from filinglens_core.settings import ApiSettings, load_settings
from filinglens_db import make_engine, ping

CHECK_TIMEOUT_S = 2
REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")  # any other incoming id is replaced, not logged
DESCRIPTION = """\
Answers analyst questions over SEC filings with citations you can check.

**Keys.** Send `X-API-Key` on every route except `/healthz` and `/readyz`. `API_KEY` opens the
normal routes. `ADMIN_API_KEY` opens every route, and it is the only key for the admin routes
under `/v1/ingest-jobs`. A missing or unknown key gets 401; `API_KEY` on an admin route gets 403.

**Errors.** Every error is an RFC 9457 problem (`application/problem+json`) with a stable `code`.
429 and 503 carry `Retry-After`; 429 also carries `RateLimit-Limit` and `RateLimit-Remaining`.

**Pages.** List routes take `limit` (at most 100) and an opaque `cursor`. Send back `next_cursor`
until it is null.
"""
log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = load_settings(ApiSettings)
    redis_url = str(settings.redis_url.get_secret_value())
    app.state.settings = settings
    app.state.engine = make_engine(settings)
    app.state.backend = LiveBackend(app.state.engine)
    app.state.redis = Redis.from_url(
        redis_url, socket_timeout=CHECK_TIMEOUT_S, socket_connect_timeout=CHECK_TIMEOUT_S
    )
    yield
    await app.state.redis.aclose()
    await app.state.engine.dispose()


app = FastAPI(
    title="FilingLens API",
    version="0.1.0",
    description=DESCRIPTION,
    lifespan=lifespan,
    generate_unique_id_function=lambda route: route.name,  # operationIds name the client functions
)
add_problem_handlers(app)
app.include_router(routes.admin)
app.include_router(routes.router)
app.include_router(
    GraphQLRouter(schema, graphql_ide=None, include_in_schema=False, context_getter=get_context),
    prefix="/graphql",
    dependencies=[Depends(routes.require_api_key)],
)


def openapi() -> dict[str, Any]:
    """FastAPI's spec plus the Problem schemas that the error responses point to."""
    if app.openapi_schema is not None:
        return app.openapi_schema
    spec = FastAPI.openapi(app)
    _, problem_schemas = models_json_schema(
        [(Problem, "serialization")], ref_template="#/components/schemas/{model}"
    )
    components = spec["components"]["schemas"] | problem_schemas["$defs"]
    spec["components"]["schemas"] = dict(sorted(components.items()))
    return spec


app.openapi = openapi


@app.middleware("http")
async def bind_request_id(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Tag every log line of a request with an id, reusing a well-formed incoming X-Request-ID."""
    incoming = request.headers.get("x-request-id", "")
    request_id = incoming if REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)
    try:
        response = await call_next(request)
    except Exception:
        # Answering here, not in an Exception handler: Starlette re-raises after those, and
        # uvicorn then drops the keep-alive connection that the client's next request reuses.
        log.exception("unhandled error")
        response = internal_error()
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/healthz", tags=["health"], response_model=Health)
async def healthz() -> Health:
    """Liveness. No key."""
    return Health(status="ok")


@app.get(
    "/readyz",
    tags=["health"],
    response_model=Health,
    responses={503: {"model": Health, "description": "A dependency is unreachable."}},
)
async def readyz(request: Request, response: Response) -> Health:
    """Readiness: Postgres, RabbitMQ and Redis answer. No key."""
    state = request.app.state
    broker_url = str(state.settings.broker_url.get_secret_value())
    checks = {
        "postgres": await _check("postgres", ping(state.engine)),
        "rabbitmq": await _check("rabbitmq", asyncio.to_thread(_ping_rabbitmq, broker_url)),
        "redis": await _check("redis", state.redis.ping()),
    }
    if all(checks.values()):
        return Health(status="ok", checks=checks)
    response.status_code = 503
    return Health(status="unavailable", checks=checks)


def _ping_rabbitmq(url: str) -> None:
    with Connection(url, connect_timeout=CHECK_TIMEOUT_S) as connection:
        connection.ensure_connection(max_retries=0)


async def _check(name: str, probe: Awaitable[object]) -> bool:
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_S):
            await probe
    except Exception as exc:
        log.warning("readiness check failed", check=name, error=repr(exc))
        return False
    return True
