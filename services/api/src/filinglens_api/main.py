"""FastAPI app: health probes, request ids, problem details, REST v1 and GraphQL."""

import asyncio
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import monotonic
from typing import Any

import httpx
import structlog
from fastapi import Depends, FastAPI, Request, Response
from kombu import Connection
from opentelemetry import trace
from pydantic.json_schema import models_json_schema
from redis.asyncio import Redis
from starlette.datastructures import State
from strawberry.fastapi import GraphQLRouter

from filinglens_api import routes
from filinglens_api.answering import Answerer, Models, PostgresEvidence
from filinglens_api.backend import DiscoverQueue, LiveBackend
from filinglens_api.graph import get_context, schema
from filinglens_api.limits import BodyLimit, rate_limit
from filinglens_api.problems import add_problem_handlers, internal_error
from filinglens_api.schemas import Health, Problem
from filinglens_core.ratelimit import BUCKET_SCRIPT
from filinglens_core.settings import ApiSettings, load_settings
from filinglens_db import make_engine, ping
from filinglens_llm.budget import ClaudeLedger
from filinglens_llm.providers import TIMEOUT, provider

CHECK_TIMEOUT_S = 2
READY_TTL_S = 5  # /readyz needs no key on a public URL: one round of checks per 5 s at most
REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")  # any other incoming id is replaced, not logged
PROBES = ("/healthz", "/readyz")
DESCRIPTION = """\
Answers analyst questions over SEC filings with citations you can check.

**Keys.** Send `X-API-Key` on every route except `/healthz` and `/readyz`. `API_KEY` opens the
normal routes. `ADMIN_API_KEY` opens every route, and it is the only key for the admin routes
under `/v1/ingest-jobs`. A missing or unknown key gets 401; `API_KEY` on an admin route gets 403.
Only servers call this API: any request with an `Origin` header gets 403, on every route.

**Errors.** Every error is an RFC 9457 problem (`application/problem+json`) with a stable `code`.
429 carries `Retry-After`, `RateLimit-Limit` and `RateLimit-Remaining`. 503 carries `Retry-After`
only when waiting helps: `overloaded` (too many answers in progress, a busy reranker, or a broker
that refused a job or could not be reached), and `ai_unavailable` when today's AI budget is used
up (until 00:00 UTC), the budget cannot be checked, or the model providers are rate limited. An
`ai_unavailable` without `Retry-After` does not clear by waiting: AI is switched off on this
server, or the last model refused the key, has no credits left or was retired. GraphQL's `answer`
reports its limits as errors with `extensions.code`, without headers. GraphQL takes POST only.

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
    app.state.redis = Redis.from_url(
        redis_url, socket_timeout=CHECK_TIMEOUT_S, socket_connect_timeout=CHECK_TIMEOUT_S
    )
    app.state.token_bucket = app.state.redis.register_script(BUCKET_SCRIPT)  # the rate limits
    app.state.ready, app.state.ready_lock = None, asyncio.Lock()  # /readyz's last round
    http = httpx.AsyncClient(timeout=TIMEOUT)  # every model provider call
    answerer = None
    if settings.ai_enabled:  # settings checked that each role's key is set
        extra = settings.llm_answer_fallback  # None keeps a single answer model before the fallback
        ledger = ClaudeLedger(app.state.redis, settings.claude_daily_token_budget)
        models = Models(
            router=provider(settings.llm_router, settings, http),
            primary=provider(settings.llm_primary, settings, http, ledger),
            fallback=provider(settings.llm_fallback, settings, http),
            answer_fallback=provider(extra, settings, http, ledger) if extra else None,
        )
        evidence = PostgresEvidence(app.state.engine, settings)
        answerer = Answerer(
            evidence, models, app.state.redis, max_inflight=settings.llm_max_inflight
        )
    discover = DiscoverQueue(str(settings.broker_url.get_secret_value()))
    app.state.backend = LiveBackend(app.state.engine, discover, settings, answerer)
    yield
    await http.aclose()
    await app.state.redis.aclose()
    await app.state.engine.dispose()


app = FastAPI(
    title="FilingLens API",
    version="0.1.0",
    description=DESCRIPTION,
    lifespan=lifespan,
    dependencies=[Depends(routes.refuse_browsers)],  # before every route's key check
    # No docs or spec routes: contracts.py exports the spec in process, and nothing fetches it.
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    generate_unique_id_function=lambda route: route.name,  # operationIds name the client functions
    # Server spans and HTTP metrics once configure_telemetry installed the providers. No logs
    # (they carry validation inputs), no exporters of FastAPI's own, probes left out, and no
    # per-operation spans, so the request's span stays current in routes and carries the answer.
    telemetry={
        "logs": False,
        "auto_configure": False,
        "operation_spans": False,
        "exclude": lambda scope: scope.get("path") in PROBES,
    },
)
add_problem_handlers(app)
# Added before the request-id middleware below, so it runs inside it and 413s get an id too.
app.add_middleware(BodyLimit)
app.include_router(routes.admin)
app.include_router(routes.router)
graphql_router = GraphQLRouter(
    schema, graphql_ide=None, include_in_schema=False, context_getter=get_context
)
# POST only: a GET could spend on `answer`, and no subscription needs the WebSocket route.
graphql_router.routes = [
    route for route in graphql_router.routes if getattr(route, "methods", None) == {"POST"}
]
app.include_router(
    graphql_router,
    prefix="/graphql",
    dependencies=[Depends(routes.require_api_key), Depends(rate_limit)],
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
    trace.get_current_span().set_attribute("request_id", request_id)  # find a reported request
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
    """Readiness: Postgres, RabbitMQ and Redis answer. No key; a result is reused for 5 s."""
    state = request.app.state
    async with state.ready_lock:  # calls that arrive during a round wait for its result
        if state.ready is None or monotonic() - state.ready[0] >= READY_TTL_S:
            checks = await _checks(state)
            state.ready = (monotonic(), checks)  # stamped at the end, however long it took
    checks = state.ready[1]
    if all(checks.values()):
        return Health(status="ok", checks=checks)
    response.status_code = 503
    return Health(status="unavailable", checks=checks)


async def _checks(state: State) -> dict[str, bool]:
    broker_url = str(state.settings.broker_url.get_secret_value())
    return {
        "postgres": await _check("postgres", ping(state.engine)),
        "rabbitmq": await _check("rabbitmq", asyncio.to_thread(_ping_rabbitmq, broker_url)),
        "redis": await _check("redis", state.redis.ping()),
    }


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
