"""Error taxonomy: each error carries its HTTP status and whether a worker should retry it."""

from typing import ClassVar


class FilingLensError(Exception):
    """Unexpected failure: HTTP 500, not retried."""

    code: ClassVar[str] = "internal"
    http_status: ClassVar[int] = 500
    retryable: ClassVar[bool] = False

    def __init__(self, message: str = "", *, retry_after_s: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s  # the API sends it as Retry-After


class InvalidInputError(FilingLensError):
    code = "invalid_input"
    http_status = 400


class UnauthorizedError(FilingLensError):
    code = "unauthorized"
    http_status = 401


class ForbiddenError(FilingLensError):
    """Valid credentials without access here, such as the normal key on an admin route."""

    code = "forbidden"
    http_status = 403


class NotFoundError(FilingLensError):
    code = "not_found"
    http_status = 404


class IdempotencyKeyReusedError(FilingLensError):
    """An Idempotency-Key came back with a different request body."""

    code = "idempotency_key_reused"
    http_status = 422


class TransientError(FilingLensError):
    """Expected to clear by itself; workers retry it with backoff (Celery autoretry_for)."""

    code = "transient"
    http_status = 503
    retryable = True


class RateLimitedError(TransientError):
    """A rate limit (ours or SEC's) is exhausted; retry after backoff."""

    code = "rate_limited"
    http_status = 429

    def __init__(
        self, message: str = "", *, retry_after_s: int | None = None, limit: int | None = None
    ) -> None:
        super().__init__(message, retry_after_s=retry_after_s)
        self.limit = limit  # requests allowed per window; the API sends it as RateLimit-Limit


class NotImplementedYetError(FilingLensError):
    """The route is in the contract, but the feature behind it arrives in a later build step."""

    code = "not_implemented"
    http_status = 501


class UpstreamError(TransientError):
    """A dependency such as SEC EDGAR or an LLM provider failed or timed out."""

    code = "upstream_error"
    http_status = 502


class OverloadedError(TransientError):
    """Load shedding: too much work in flight, so callers should back off."""

    code = "overloaded"
    http_status = 503


class AiUnavailableError(FilingLensError):
    """Model calls are off: AI_ENABLED=false, or today's AI token budget is used up."""

    code = "ai_unavailable"
    http_status = 503
