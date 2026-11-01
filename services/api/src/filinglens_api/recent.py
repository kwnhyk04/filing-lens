"""Recent questions: each sign-in's last answers in Redis, so a repeat answers from earlier.

Only the answer stream route uses this. The eval harness runs Answerer in process without it, so
evals keep measuring real model calls (evals/tests/test_ci.py checks that it never loads).
"""

import hashlib
import json
import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, cast

import structlog
from fastapi import Depends, Request
from pydantic import AwareDatetime, BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError

from filinglens_api.backend import decode_cursor, encode_cursor
from filinglens_api.schemas import Answer, AnswerRequest, NoNul, RecentAnswer, RecentAnswerPage
from filinglens_core.errors import TransientError
from filinglens_llm.validate import STRAIGHT_QUOTES

KEEP = 10  # answers per sign-in; past it the oldest goes
UNAVAILABLE = "Recent questions are unavailable right now; try again shortly."
log = structlog.get_logger(__name__)


def normalized(question: str) -> str:
    """The words compared: NFKC, straight quotes, casefolded, single spaces, no closing ?, ! or ."""
    text = unicodedata.normalize("NFKC", question).translate(STRAIGHT_QUOTES).casefold()
    return " ".join(text.split()).rstrip("?!. ")


def question_key(request: AnswerRequest) -> str:
    """The same normalized words over the same companies and years make the same question."""
    scope = [
        normalized(request.question),
        sorted(set(request.company_ids or [])),
        sorted(set(request.fiscal_years or [])),
    ]
    return hashlib.sha256(json.dumps(scope).encode()).hexdigest()[:32]


class Stored(BaseModel):
    question: str  # as asked
    answered_at: AwareDatetime
    answer: Answer


class RecentKey(BaseModel):
    """Recent answers page newest first, by (answered_at, id)."""

    answered_at: AwareDatetime  # a naive time could not be compared with the stored ones
    id: NoNul


def _stored(raw: bytes | str) -> Stored | None:
    """None for a value that no longer parses, such as one stored before a schema change."""
    try:
        return Stored.model_validate_json(raw)
    except ValueError:
        return None


def _text(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


def _unavailable(op: str, exc: Exception) -> None:
    # The error's type only: a Redis error reply can quote its command's arguments, the question.
    log.warning("recent answers unavailable", op=op, error=type(exc).__name__)


class RecentAnswers:
    """A hash per sign-in, `recent:<sha256 of its id>`, never the id itself: a field per question,
    each with its own TTL (HSETEX, Redis 8.0 or later), at most KEEP. Redis drops the hash with its
    last field. get and put sit on the answer path, so they fail open."""

    def __init__(
        self, redis: Redis, ttl_s: int, now: Callable[[], datetime] = lambda: datetime.now(UTC)
    ) -> None:
        self._redis = redis
        self._ttl_s = ttl_s
        self._now = now

    @staticmethod
    def key(session_id: str) -> str:
        return f"recent:{hashlib.sha256(session_id.encode()).hexdigest()[:32]}"

    async def get(self, session_id: str, request: AnswerRequest) -> Stored | None:
        """The answer this sign-in got to this question, or None; Redis down is a miss."""
        try:
            raw = cast(
                bytes | None, await self._redis.hget(self.key(session_id), question_key(request))
            )
        except RedisError as exc:
            _unavailable("get", exc)
            return None
        return None if raw is None else _stored(raw)

    async def put(self, session_id: str, request: AnswerRequest, answer: Answer) -> None:
        """Keep a completed answer, then only the KEEP newest; Redis down skips it."""
        key = self.key(session_id)
        stored = Stored(question=request.question, answered_at=self._now(), answer=answer)
        try:
            await self._redis.hsetex(
                key, question_key(request), stored.model_dump_json(), ex=self._ttl_s
            )
            entries = cast(dict[bytes, bytes], await self._redis.hgetall(key))
            if len(entries) > KEEP:
                unreadable = datetime.min.replace(tzinfo=UTC)  # goes first

                def age(field: bytes) -> datetime:
                    found = _stored(entries[field])
                    return found.answered_at if found else unreadable

                await self._redis.hdel(key, *sorted(entries, key=age, reverse=True)[KEEP:])
        except RedisError as exc:
            _unavailable("put", exc)

    async def page(self, session_id: str, limit: int, cursor: str | None) -> RecentAnswerPage:
        """This sign-in's answers, newest first; values that no longer parse are left out."""
        try:
            entries = cast(dict[bytes, bytes], await self._redis.hgetall(self.key(session_id)))
        except RedisError as exc:
            raise TransientError(UNAVAILABLE, retry_after_s=5) from exc
        items = [
            RecentAnswer(
                id=_text(field),
                question=stored.question,
                answered_at=stored.answered_at,
                answer=stored.answer,
            )
            for field, raw in entries.items()
            if (stored := _stored(raw)) is not None
        ]
        items.sort(key=lambda item: (item.answered_at, item.id), reverse=True)
        if cursor is not None:
            after = decode_cursor(cursor, RecentKey)
            items = [i for i in items if (i.answered_at, i.id) < (after.answered_at, after.id)]
        if len(items) <= limit:
            return RecentAnswerPage(items=items, next_cursor=None)
        last = items[limit - 1]
        next_cursor = encode_cursor(RecentKey(answered_at=last.answered_at, id=last.id))
        return RecentAnswerPage(items=items[:limit], next_cursor=next_cursor)

    async def clear(self, session_id: str) -> None:
        try:
            await self._redis.delete(self.key(session_id))
        except RedisError as exc:
            raise TransientError(UNAVAILABLE, retry_after_s=5) from exc


def get_recent(request: Request) -> RecentAnswers:
    return request.app.state.recent


RecentDep = Annotated[RecentAnswers, Depends(get_recent)]
