"""Request limits: per-key rate limits in Redis, the AI switch and budget, body size and time."""

import hashlib
import math

import structlog
from fastapi import Request
from redis.exceptions import RedisError
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from filinglens_api.problems import http_problem
from filinglens_core.errors import RateLimitedError
from filinglens_llm import budget

PER_MINUTE = 60  # every route that takes a key, per key
ANSWERS_PER_MINUTE = 10  # POST /v1/answers and its stream, per key
MAX_BODY_BYTES = 64 * 1024
ANSWER_TIMEOUT_S = 30
TOO_LARGE = f"The request body is larger than {MAX_BODY_BYTES // 1024} KB."
log = structlog.get_logger(__name__)


async def _take(request: Request, bucket: str, per_minute: int) -> None:
    """Take a token from this key's bucket or raise 429; fails open while Redis is down."""
    key = hashlib.sha256(request.headers.get("x-api-key", "").encode()).hexdigest()[:32]
    try:
        taken, wait_ms = await request.app.state.token_bucket(
            keys=[f"ratelimit:{bucket}:{key}"], args=[per_minute / 60, per_minute]
        )
    except RedisError as exc:
        log.warning("rate limiter unavailable, request allowed", bucket=bucket, error=repr(exc))
        return
    if not taken:
        raise RateLimitedError(
            f"Rate limit of {per_minute} requests a minute reached.",
            retry_after_s=max(1, math.ceil(wait_ms / 1000)),
            limit=per_minute,
        )


async def rate_limit(request: Request) -> None:
    """60 requests a minute per API key."""
    await _take(request, "all", PER_MINUTE)


async def answer_limits(request: Request) -> None:
    """Answers: 10 a minute per API key, only while AI is on and today's budget lasts."""
    await _take(request, "answers", ANSWERS_PER_MINUTE)
    settings = request.app.state.settings
    await budget.check(
        request.app.state.redis,
        enabled=settings.ai_enabled,
        daily_tokens=settings.daily_ai_token_budget,
    )


class BodyLimit:
    """Refuse request bodies over MAX_BODY_BYTES with 413, chunked ones included."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        length = Headers(scope=scope).get("content-length", "")
        if length.isdigit() and int(length) > MAX_BODY_BYTES:
            await http_problem(HTTPException(413, TOO_LARGE))(scope, receive, send)
            return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > MAX_BODY_BYTES:  # a chunked body announces no length
                    raise HTTPException(413, TOO_LARGE)  # FastAPI passes it to the 413 handler
            return message

        await self.app(scope, limited_receive, send)
