"""FastAPI app: health probes, request ids, API-key auth and GraphQL."""

import asyncio
import re
import secrets
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import strawberry
import structlog
from fastapi import Depends, FastAPI, Request, Response, Security
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from kombu import Connection
from pydantic import BaseModel
from redis.asyncio import Redis
from strawberry.fastapi import GraphQLRouter

from filinglens_core.errors import FilingLensError, UnauthorizedError
from filinglens_core.settings import ApiSettings, load_settings
from filinglens_db import make_engine, ping

CHECK_TIMEOUT_S = 2
REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")  # any other incoming id is replaced, not logged
log = structlog.get_logger(__name__)


class Health(BaseModel):
    status: Literal["ok", "unavailable"]
    checks: dict[str, bool] = {}


@strawberry.type
class Query:
    @strawberry.field
    def status(self) -> str:
        return "ok"


schema = strawberry.Schema(query=Query)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = load_settings(ApiSettings)
    redis_url = str(settings.redis_url.get_secret_value())
    app.state.settings = settings
    app.state.engine = make_engine(settings)
    app.state.redis = Redis.from_url(
        redis_url, socket_timeout=CHECK_TIMEOUT_S, socket_connect_timeout=CHECK_TIMEOUT_S
    )
    yield
    await app.state.redis.aclose()
    await app.state.engine.dispose()


def require_api_key(request: Request, key: Annotated[str | None, Security(api_key_header)]) -> None:
    expected: str = request.app.state.settings.api_key.get_secret_value()
    if key is None or not secrets.compare_digest(key.encode(), expected.encode()):
        raise UnauthorizedError("Missing or invalid API key")


app = FastAPI(
    title="FilingLens API",
    version="0.1.0",
    lifespan=lifespan,
    generate_unique_id_function=lambda route: route.name,  # operationIds name the client functions
)
app.include_router(
    GraphQLRouter(schema, graphql_ide=None, include_in_schema=False),
    prefix="/graphql",
    dependencies=[Depends(require_api_key)],
)


@app.middleware("http")
async def bind_request_id(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Tag every log line of a request with an id, reusing a well-formed incoming X-Request-ID."""
    incoming = request.headers.get("x-request-id", "")
    request_id = incoming if REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(FilingLensError)
async def handle_error(_: Request, exc: FilingLensError) -> JSONResponse:
    body = {"error": {"code": exc.code, "message": str(exc)}}
    return JSONResponse(body, status_code=exc.http_status)


@app.get("/healthz")
async def healthz() -> Health:
    return Health(status="ok")


@app.get("/readyz", responses={503: {"model": Health}})
async def readyz(request: Request, response: Response) -> Health:
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
