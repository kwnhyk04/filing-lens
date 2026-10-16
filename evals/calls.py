"""Model calls in evals: replies cached by call key, every call recorded, 429s kept from the
Answerer (which would fall back or give up) and turned into a wait or a stop."""

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals.golden import read_jsonl
from filinglens_core.errors import RateLimitedError
from filinglens_llm.providers import Completion, Provider

MAX_WAIT_S = 120  # a longer Retry-After means the quota is gone for now
STRIKES = 3  # 429s in a row without a Retry-After before the run stops
TIMED_STRIKES = 10  # 429s in a row with a short Retry-After before the run stops
GEMINI_WAIT_S = 60  # Gemini sends no Retry-After


class RateLimited(Exception):
    """A provider's 429, raised past the Answerer: not a FilingLensError, so no fallback."""

    def __init__(self, message: str, retry_after_s: float | None) -> None:
        super().__init__(message)
        self.timed = retry_after_s is not None  # Groq sends Retry-After; Gemini does not
        self.wait_s = retry_after_s or GEMINI_WAIT_S


class Stop(Exception):
    """Ends the run with an exit code: 2 for a quota or a refused key, 3 for drift."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


class Cache:
    """Replies by call key in an append-only JSONL file. A key is written once, so a report's
    call keys always read back the replies it saw; a live rerun takes new keys (harness --tag)."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._replies = {row["key"]: Completion(**row["completion"]) for row in read_jsonl(path)}

    def get(self, key: str) -> Completion | None:
        return self._replies.get(key)

    def put(self, key: str, completion: Completion) -> None:
        self._replies[key] = completion
        at = datetime.now(UTC).isoformat(timespec="seconds")
        row = {"key": key, "completion": asdict(completion), "at": at}
        with self._path.open("a", encoding="utf-8", newline="\n") as file:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


@dataclass
class Call:
    role: str  # router, primary or judge
    model: str
    cache_id: str  # its key in the reply cache; reports name it so secret scanners stay quiet
    cached: bool
    input_tokens: int
    output_tokens: int
    latency_s: float
    first_token_s: float | None
    truncated: bool  # the output reached max_tokens
    text: str = field(repr=False)  # kept out of records: the cache holds it under `key`

    def saved(self) -> dict[str, Any]:
        return {name: value for name, value in asdict(self).items() if name != "text"}


class Recorded:
    """A provider that replies from the cache when it can and records each call it serves.

    The call key hashes `context` (question id, answer path), the role, model, options,
    max_tokens and schema, and both prompts. `max_tokens`, when set, replaces the caller's.
    """

    def __init__(
        self,
        inner: Provider,
        role: str,
        cache: Cache,
        context: Mapping[str, Any],
        calls: list[Call],
        *,
        options: Mapping[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self.name = inner.name
        self._inner, self._role, self._cache, self._calls = inner, role, cache, calls
        self._context = {**context, "role": role, "model": inner.name, "options": options or {}}
        self._max_tokens = max_tokens

    def key(self, system: str, user: str, max_tokens: int, schema: Mapping[str, Any] | None) -> str:
        return digest(
            self._context
            | {
                "max_tokens": self._max_tokens or max_tokens,
                "schema": schema,
                "system": digest(system),
                "user": digest(user),
            }
        )

    def _keep(self, key: str, completion: Completion, cached: bool, max_tokens: int) -> None:
        self._calls.append(
            Call(
                self._role,
                self.name,
                key,
                cached,
                completion.input_tokens,
                completion.output_tokens,
                completion.latency_s,
                completion.first_token_s,
                completion.output_tokens >= max_tokens,
                completion.text,
            )
        )

    async def complete(
        self, system: str, user: str, *, max_tokens: int, schema: Mapping[str, Any] | None = None
    ) -> Completion:
        key = self.key(system, user, max_tokens, schema)
        max_tokens = self._max_tokens or max_tokens
        completion = self._cache.get(key)
        cached = completion is not None
        if completion is None:
            try:
                completion = await self._inner.complete(
                    system, user, max_tokens=max_tokens, schema=schema
                )
            except RateLimitedError as exc:
                raise RateLimited(str(exc), exc.retry_after_s) from exc
            self._cache.put(key, completion)
        self._keep(key, completion, cached, max_tokens)
        return completion

    async def stream(
        self, system: str, user: str, *, max_tokens: int
    ) -> AsyncIterator[str | Completion]:
        key = self.key(system, user, max_tokens, None)
        max_tokens = self._max_tokens or max_tokens
        if (completion := self._cache.get(key)) is not None:
            self._keep(key, completion, True, max_tokens)
            yield completion.text
            yield completion
            return
        try:
            async for item in self._inner.stream(system, user, max_tokens=max_tokens):
                if isinstance(item, Completion):
                    self._cache.put(key, item)
                    self._keep(key, item, False, max_tokens)
                yield item
        except RateLimitedError as exc:  # a 429 comes before any text
            raise RateLimited(str(exc), exc.retry_after_s) from exc


async def patiently[T](attempt: Callable[[], Awaitable[T]]) -> T:
    """Run `attempt` again after a 429 that asks for a short wait, outside any answer timeout.
    Stop the run (exit 2) on a Retry-After over MAX_WAIT_S, on the STRIKES-th 429 in a row
    without one (Gemini), or on the TIMED_STRIKES-th with one: a large prompt under Groq's
    tokens-a-minute limit can draw several short waits in a row (calibration, 2026-10-16)."""
    strikes = 0
    while True:
        try:
            return await attempt()
        except RateLimited as limited:
            strikes += 1
            limit = TIMED_STRIKES if limited.timed else STRIKES
            if strikes >= limit or limited.wait_s > MAX_WAIT_S:
                raise Stop(2, f"Quota: {limited} Rerun later: the run resumes.") from None
            print(f"  {limited} Waiting {limited.wait_s:.0f} s.", flush=True)
            await asyncio.sleep(limited.wait_s)
