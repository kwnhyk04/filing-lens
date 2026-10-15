"""EDGAR client: every SEC request goes through the shared Redis rate limiter (8 req/s).

Responses are cached on disk, gzipped, under their URL path: a filing document is downloaded once,
and JSON (submissions, companyfacts, company tickers) again only after JSON_MAX_AGE. Every request
sent is counted by kind in the Redis hash REQUESTS_KEY. When SEC throttles, a shared cool-off
key pauses every worker process, not only the one that was refused. A 403 that comes back right
after a cool-off is a refusal, not a throttle: from then on every request fails at once, without
reaching SEC, until a worker restarts. Without Redis nothing is sent (LimiterUnavailableError).
"""

import gzip
import json
import re
import time
import uuid
from collections.abc import Callable
from contextlib import suppress
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, NoReturn, cast

import httpx
from redis import Redis
from redis.exceptions import RedisError

from filinglens_core.errors import FilingLensError, NotFoundError, RateLimitedError, UpstreamError
from filinglens_core.ratelimit import BUCKET_SCRIPT

RATE_PER_SECOND = 8  # SEC allows 10; with a capacity of 1, no burst goes past the rate
BUCKET_KEY = "sec:bucket"
COOL_OFF_KEY = "sec:cool-off"
COOL_OFF_S = 60  # pause after a refusal that carries no usable Retry-After
MAX_COOL_OFF_S = 120  # well inside the tasks' 300 s soft time limit
STRIKE_KEY = "sec:403-strike"  # a 403 started a cool-off; a success clears it
STRIKE_GRACE_S = 60  # a 403 this long after the cool-off still counts as the second one
REFUSED_KEY = "sec:refused"  # why SEC refuses; a worker restart clears it (worker_ready)
REQUESTS_KEY = "sec:requests"  # requests sent to SEC, by kind: document, submissions, ...
TIMEOUT = httpx.Timeout(30.0, connect=5.0)  # connect 5 s; read, write and pool waits 30 s
JSON_MAX_AGE = timedelta(hours=1)
ACCESSION = re.compile(r"\d{10}-\d{2}-\d{6}")
FILE_NAME = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}"
)  # one path segment: keeps the cache safe
OLDER_FILE = re.compile(r"CIK\d{10}-submissions-\d{3}\.json")


class LimiterUnavailableError(UpstreamError):
    """Redis, which holds the shared rate limit, is unreachable, so nothing was sent to SEC."""


class SecRefusedError(FilingLensError):
    """SEC still answers 403 after a cool-off: a refusal that retries cannot fix."""

    code = "sec_refused"
    http_status = 502


class SecClient:
    """Blocking client for one process; the rate limit and the cool-off span every process."""

    def __init__(
        self, *, user_agent: str, www_url: str, data_url: str, cache_dir: Path, redis: Redis
    ) -> None:
        self._www = www_url.rstrip("/")
        self._data = data_url.rstrip("/")
        self._cache_dir = cache_dir
        self._redis = redis
        self._bucket = redis.register_script(BUCKET_SCRIPT)
        self._http = httpx.Client(headers={"User-Agent": user_agent}, timeout=TIMEOUT)

    def submissions(self, cik: int) -> dict[str, Any]:
        """A company's submissions: its recent filings and the names of its older files."""
        return self._json(self._data, f"submissions/CIK{cik:010d}.json", "submissions")

    def submissions_file(self, name: str) -> dict[str, Any]:
        """An older submissions file, such as CIK0000320193-submissions-001.json."""
        if not OLDER_FILE.fullmatch(name):
            raise FilingLensError(f"Not a submissions file name: {name!r}")
        return self._json(self._data, f"submissions/{name}", "submissions")

    def companyfacts(self, cik: int) -> dict[str, Any]:
        """A company's XBRL facts; decimals stay Decimal, so values keep SEC's digits."""
        path = f"api/xbrl/companyfacts/CIK{cik:010d}.json"
        return self._json(self._data, path, "companyfacts", parse_float=Decimal)

    def company_tickers(self) -> dict[str, Any]:
        """SEC's ticker list: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": ...}, ...}."""
        return self._json(self._www, "files/company_tickers.json", "tickers")

    def document(self, cik: int, accession_number: str, name: str) -> bytes:
        """A filing document from EDGAR's archives; filings never change, so it is kept for good."""
        if not ACCESSION.fullmatch(accession_number) or not FILE_NAME.fullmatch(name):
            raise FilingLensError(f"Not a filing document: {accession_number} {name!r}")
        folder = accession_number.replace("-", "")
        return self._get(self._www, f"Archives/edgar/data/{cik}/{folder}/{name}", "document")

    def close(self) -> None:
        self._http.close()

    def _json(
        self, base: str, path: str, kind: str, parse_float: Callable[[str], Any] = float
    ) -> dict[str, Any]:
        body = self._get(base, path, kind, JSON_MAX_AGE)
        return cast(dict[str, Any], json.loads(body, parse_float=parse_float))

    def _get(self, base: str, path: str, kind: str, max_age: timedelta | None = None) -> bytes:
        cached = self._cache_dir / f"{path}.gz"
        if cached.exists() and (
            max_age is None or time.time() - cached.stat().st_mtime < max_age.total_seconds()
        ):
            return gzip.decompress(cached.read_bytes())
        body = self._download(f"{base}/{path}", kind)
        cached.parent.mkdir(parents=True, exist_ok=True)
        partial = cached.with_name(f"{cached.name}.{uuid.uuid4().hex}.part")
        partial.write_bytes(gzip.compress(body))
        partial.replace(cached)  # atomic, so a reader never sees half a file
        return body

    def _download(self, url: str, kind: str) -> bytes:
        self._acquire()
        with suppress(RedisError):  # a lost count must not cost the request
            self._redis.hincrby(REQUESTS_KEY, kind, 1)
        try:
            response = self._http.get(url)
        except httpx.HTTPError as exc:  # timeouts and connection errors
            raise UpstreamError(f"SEC request failed ({type(exc).__name__}): {url}") from exc
        status = response.status_code
        if status == 200:
            with suppress(RedisError):  # left alone, the strike only expires later
                self._redis.delete(STRIKE_KEY)  # any throttling is over
            return response.content
        if status in (403, 429):  # SEC answers 403 to clients over its rate
            self._refused(url, status, response)
        if status == 404:
            raise NotFoundError(f"SEC has no {url}")
        if status >= 500:
            raise UpstreamError(f"SEC answered {status} for {url}")
        raise FilingLensError(f"SEC answered {status} for {url}")

    def _acquire(self) -> None:
        """Wait for a token from the shared bucket; a cool-off holds every process meanwhile.

        Fails closed: without Redis no request goes out, and a recorded refusal fails at once.
        """
        try:
            while True:
                taken, wait_ms = self._bucket(
                    keys=[BUCKET_KEY, COOL_OFF_KEY], args=[RATE_PER_SECOND, 1]
                )
                if taken:
                    refused = cast(bytes | None, self._redis.get(REFUSED_KEY))
                    break
                time.sleep(wait_ms / 1000)
        except RedisError as exc:
            message = "Redis is unavailable, so no SEC request can be rate limited."
            raise LimiterUnavailableError(message) from exc
        if refused is not None:
            raise SecRefusedError(refused.decode())

    def _refused(self, url: str, status: int, response: httpx.Response) -> NoReturn:
        """Cool every process off after a 403 or 429, unless a 403 already outlasted a cool-off."""
        try:
            strike = status == 403 and self._redis.exists(STRIKE_KEY)
            if strike and not self._redis.exists(COOL_OFF_KEY):
                reason = (
                    f"SEC still refuses requests after a cool-off (403 for {url}), so this is not"
                    " a rate limit. Check SEC_USER_AGENT: it must name the tool and give a contact"
                    " email. Fix it, restart the workers, then replay the dead letters."
                )
                self._redis.set(REFUSED_KEY, reason)
                raise SecRefusedError(reason)
            retry_after = response.headers.get("Retry-After", "")
            seconds = int(retry_after) if retry_after.isdigit() else COOL_OFF_S
            seconds = min(max(seconds, 1), MAX_COOL_OFF_S)
            self._redis.set(COOL_OFF_KEY, 1, ex=seconds)
            if status == 403:
                self._redis.set(STRIKE_KEY, 1, ex=seconds + STRIKE_GRACE_S)
        except RedisError as exc:
            raise LimiterUnavailableError("Redis is unavailable for the SEC cool-off.") from exc
        hint = " Check SEC_USER_AGENT." if b"Undeclared Automated Tool" in response.content else ""
        raise RateLimitedError(
            f"SEC refused {url} ({status}); every worker pauses {seconds} s.{hint}",
            retry_after_s=seconds,
        )
