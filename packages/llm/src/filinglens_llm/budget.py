"""Daily AI budget: Redis counts LLM calls and tokens per UTC day; past it, no model calls."""

import math
from datetime import UTC, date, datetime, time, timedelta
from typing import cast

import redis as sync_redis
from redis.asyncio import Redis
from redis.exceptions import RedisError

from filinglens_core.errors import AiUnavailableError
from filinglens_telemetry import metrics

KEEP = timedelta(days=2)  # a day's counters outlive the day, so yesterday stays readable
CLAUDE_OFF = "ai:claude:off"  # hash kind, reason, at; it stays until someone deletes the key


def usage_key(day: date) -> str:
    """Hash with fields `calls` and `tokens` for one UTC day."""
    return f"ai:usage:{day.isoformat()}"


def claude_usage_key(day: date) -> str:
    """Hash with fields `calls` and `tokens`: Claude's own budget for one UTC day."""
    return f"ai:claude:{day.isoformat()}"


def claude_off_kind(redis: sync_redis.Redis) -> str | None:
    """Why Claude is off for good (credits, key_or_model) for the alert's gauge (a sync callback);
    None while it may answer or Redis is down."""
    try:
        kind = cast(bytes | None, redis.hget(CLAUDE_OFF, "kind"))
    except RedisError:
        return None
    return kind.decode() if kind else None


class ClaudeLedger:
    """Claude's own daily tokens and its switch-off, in the API's Redis database: the api and the
    evals share them, and a switch-off outlives a restart."""

    def __init__(self, redis: Redis, daily_tokens: int) -> None:
        self.daily_tokens = daily_tokens
        self._redis = redis

    async def off(self) -> str | None:
        """Why Claude is off for good, or None."""
        reason = cast(bytes | None, await self._redis.hget(CLAUDE_OFF, "reason"))
        return reason.decode() if reason else None

    async def turn_off(self, kind: str, reason: str) -> None:
        at = datetime.now(UTC).isoformat(timespec="seconds")
        await self._redis.hset(CLAUDE_OFF, mapping={"kind": kind, "reason": reason, "at": at})

    async def tokens_today(self) -> int:
        key = claude_usage_key(datetime.now(UTC).date())
        return int(cast(bytes | None, await self._redis.hget(key, "tokens")) or 0)

    async def record(self, tokens: int) -> None:
        key = claude_usage_key(datetime.now(UTC).date())
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hincrby(key, "calls", 1)
            pipe.hincrby(key, "tokens", tokens)
            pipe.expire(key, KEEP)
            await pipe.execute()


def tokens_today(redis: sync_redis.Redis) -> int | None:
    """Today's LLM tokens for the metrics gauge (a sync callback); None while Redis is down."""
    try:
        return int(
            cast(bytes | None, redis.hget(usage_key(datetime.now(UTC).date()), "tokens")) or 0
        )
    except RedisError:
        return None


async def record(redis: Redis, tokens: int) -> None:
    """Count one LLM call and its tokens against today's budget."""
    key = usage_key(datetime.now(UTC).date())
    async with redis.pipeline(transaction=True) as pipe:
        pipe.hincrby(key, "calls", 1)
        pipe.hincrby(key, "tokens", tokens)
        pipe.expire(key, KEEP)
        await pipe.execute()


async def record_fallback(redis: Redis) -> None:
    """Count one model call that went to LLM_FALLBACK, in today's hash (field `fallbacks`)."""
    key = usage_key(datetime.now(UTC).date())
    async with redis.pipeline(transaction=True) as pipe:
        pipe.hincrby(key, "fallbacks", 1)
        pipe.expire(key, KEEP)
        await pipe.execute()


async def check(redis: Redis, *, enabled: bool, daily_tokens: int) -> None:
    """Raise AiUnavailableError (503) when AI is off or today's tokens reached the budget.

    Fails closed: when Redis cannot say how much was used, no model call goes out.
    """
    if not enabled:
        metrics.REJECTED.add(1, {"reason": "ai_disabled"})
        raise AiUnavailableError("AI is switched off on this server (AI_ENABLED=false).")
    now = datetime.now(UTC)
    try:
        used = int(await redis.hget(usage_key(now.date()), "tokens") or 0)
    except RedisError as exc:
        metrics.REJECTED.add(1, {"reason": "budget_unavailable"})
        message = "The AI budget cannot be checked right now."
        raise AiUnavailableError(message, retry_after_s=30) from exc
    if used >= daily_tokens:
        metrics.REJECTED.add(1, {"reason": "budget_exhausted"})
        raise AiUnavailableError(
            f"Today's AI budget of {daily_tokens:,} tokens is used up; answers resume at"
            " 00:00 UTC.",
            retry_after_s=seconds_to_midnight(now),
        )


def seconds_to_midnight(now: datetime) -> int:
    """Seconds until 00:00 UTC, when the daily budgets start again."""
    midnight = datetime.combine(now.date() + timedelta(days=1), time(), UTC)
    return math.ceil((midnight - now).total_seconds())
