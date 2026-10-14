"""EDGAR client: every SEC request goes through the shared Redis rate limiter (8 req/s).

Responses are cached on disk, gzipped, under their URL path: a filing document is downloaded once,
and submissions JSON again only after SUBMISSIONS_MAX_AGE. When SEC throttles, a shared cool-off
key pauses every worker process, not only the one that was refused.
"""

import gzip
import json
import re
import time
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

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
TIMEOUT = httpx.Timeout(30.0, connect=5.0)  # connect 5 s; read, write and pool waits 30 s
SUBMISSIONS_MAX_AGE = timedelta(hours=1)
ACCESSION = re.compile(r"\d{10}-\d{2}-\d{6}")
FILE_NAME = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}"
)  # one path segment: keeps the cache safe
OLDER_FILE = re.compile(r"CIK\d{10}-submissions-\d{3}\.json")


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
        return self._json(self._data, f"submissions/CIK{cik:010d}.json")

    def submissions_file(self, name: str) -> dict[str, Any]:
        """An older submissions file, such as CIK0000320193-submissions-001.json."""
        if not OLDER_FILE.fullmatch(name):
            raise FilingLensError(f"Not a submissions file name: {name!r}")
        return self._json(self._data, f"submissions/{name}")

    def document(self, cik: int, accession_number: str, name: str) -> bytes:
        """A filing document from EDGAR's archives; filings never change, so it is kept for good."""
        if not ACCESSION.fullmatch(accession_number) or not FILE_NAME.fullmatch(name):
            raise FilingLensError(f"Not a filing document: {accession_number} {name!r}")
        folder = accession_number.replace("-", "")
        return self._get(self._www, f"Archives/edgar/data/{cik}/{folder}/{name}")

    def close(self) -> None:
        self._http.close()

    def _json(self, base: str, path: str) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self._get(base, path, SUBMISSIONS_MAX_AGE)))

    def _get(self, base: str, path: str, max_age: timedelta | None = None) -> bytes:
        cached = self._cache_dir / f"{path}.gz"
        if cached.exists() and (
            max_age is None or time.time() - cached.stat().st_mtime < max_age.total_seconds()
        ):
            return gzip.decompress(cached.read_bytes())
        body = self._download(f"{base}/{path}")
        cached.parent.mkdir(parents=True, exist_ok=True)
        partial = cached.with_name(f"{cached.name}.{uuid.uuid4().hex}.part")
        partial.write_bytes(gzip.compress(body))
        partial.replace(cached)  # atomic, so a reader never sees half a file
        return body

    def _download(self, url: str) -> bytes:
        self._acquire()
        try:
            response = self._http.get(url)
        except httpx.HTTPError as exc:  # timeouts and connection errors
            raise UpstreamError(f"SEC request failed ({type(exc).__name__}): {url}") from exc
        status = response.status_code
        if status == 200:
            return response.content
        if status in (403, 429):  # SEC answers 403 to clients over its rate
            seconds = self._cool_off(response.headers.get("Retry-After"))
            hint = (
                " Check SEC_USER_AGENT." if b"Undeclared Automated Tool" in response.content else ""
            )
            raise RateLimitedError(
                f"SEC refused {url} ({status}); every worker pauses {seconds} s.{hint}",
                retry_after_s=seconds,
            )
        if status == 404:
            raise NotFoundError(f"SEC has no {url}")
        if status >= 500:
            raise UpstreamError(f"SEC answered {status} for {url}")
        raise FilingLensError(f"SEC answered {status} for {url}")

    def _acquire(self) -> None:
        """Wait for a token from the shared bucket; a cool-off holds every process meanwhile."""
        while True:
            try:
                taken, wait_ms = self._bucket(
                    keys=[BUCKET_KEY, COOL_OFF_KEY], args=[RATE_PER_SECOND, 1]
                )
            except RedisError as exc:
                raise UpstreamError("Redis is unavailable for the SEC rate limit.") from exc
            if taken:
                return
            time.sleep(wait_ms / 1000)

    def _cool_off(self, retry_after: str | None) -> int:
        seconds = int(retry_after) if retry_after and retry_after.isdigit() else COOL_OFF_S
        seconds = min(max(seconds, 1), MAX_COOL_OFF_S)
        try:
            self._redis.set(COOL_OFF_KEY, 1, ex=seconds)
        except RedisError as exc:
            raise UpstreamError("Redis is unavailable for the SEC cool-off.") from exc
        return seconds
