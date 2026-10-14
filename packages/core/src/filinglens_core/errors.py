"""Error taxonomy: each error carries its HTTP status and whether a worker should retry it."""

from typing import ClassVar


class FilingLensError(Exception):
    """Unexpected failure: HTTP 500, not retried."""

    code: ClassVar[str] = "internal"
    http_status: ClassVar[int] = 500
    retryable: ClassVar[bool] = False


class InvalidInputError(FilingLensError):
    code = "invalid_input"
    http_status = 400


class UnauthorizedError(FilingLensError):
    code = "unauthorized"
    http_status = 401


class NotFoundError(FilingLensError):
    code = "not_found"
    http_status = 404


class RateLimitedError(FilingLensError):
    """A rate limit (ours or SEC's) is exhausted; retry after backoff."""

    code = "rate_limited"
    http_status = 429
    retryable = True


class UpstreamError(FilingLensError):
    """A dependency such as SEC EDGAR or an LLM provider failed or timed out."""

    code = "upstream_error"
    http_status = 502
    retryable = True


class OverloadedError(FilingLensError):
    """Load shedding: too much work in flight, so callers should back off."""

    code = "overloaded"
    http_status = 503
    retryable = True
