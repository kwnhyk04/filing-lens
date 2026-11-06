"""I3: a database or time-limit failure retries; a failure that cannot be recorded stays visible."""

from collections.abc import Callable
from contextlib import suppress
from types import SimpleNamespace
from typing import Any, cast

import pytest
from asyncpg.exceptions import (
    AdminShutdownError,
    CannotConnectNowError,
    DeadlockDetectedError,
    QueryCanceledError,
    UniqueViolationError,
)
from celery import Task
from celery.exceptions import Reject, SoftTimeLimitExceeded
from sqlalchemy.exc import DBAPIError, IntegrityError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout

from filinglens_core.errors import FilingLensError, TransientError
from filinglens_ingest import pipeline


def wrapped(error: Exception) -> DBAPIError:
    """As SQLAlchemy's asyncpg dialect raises a server error: the driver's sits in .orig."""
    return DBAPIError("SELECT 1", {}, error)


@pytest.mark.parametrize(
    "error",
    [
        ConnectionRefusedError("connection refused"),  # Postgres is down
        ConnectionResetError("reset by peer"),
        OSError("network unreachable"),
        TimeoutError("connect timed out"),
        TimeoutError(),
        PoolTimeout("pool timed out"),
        InterfaceError("SELECT 1", {}, Exception("connection is closed")),
        OperationalError("SELECT 1", {}, Exception("server closed the connection")),
        wrapped(DeadlockDetectedError("deadlock detected")),
        wrapped(QueryCanceledError("canceling statement due to statement timeout")),
        wrapped(AdminShutdownError("terminating connection")),
        wrapped(CannotConnectNowError("the database system is starting up")),
        SoftTimeLimitExceeded(),
    ],
)
def test_a_failure_that_clears_by_itself_is_transient(error: Exception) -> None:
    assert pipeline.transient(error)


@pytest.mark.parametrize(
    "error",
    [
        ValueError("no required item"),
        KeyError("filings"),
        FilingLensError("Filing 1 has no section text to chunk."),
        IntegrityError("INSERT", {}, UniqueViolationError("duplicate key")),
        wrapped(UniqueViolationError("duplicate key")),
        PermissionError("the SEC cache is read-only"),
        FileNotFoundError("no such file"),
    ],
)
def test_a_failure_that_will_repeat_is_not(error: Exception) -> None:
    assert not pipeline.transient(error)


def task(retries: int = 0) -> tuple[Task, list[dict[str, Any]]]:
    sent: list[dict[str, Any]] = []
    request = SimpleNamespace(retries=retries, args=[1], kwargs={}, id="task-1")
    fake = SimpleNamespace(
        name="filinglens_ingest.pipeline.fetch",
        request=request,
        apply_async=lambda *_, **options: sent.append(options),
    )
    return cast(Task, fake), sent


def attempt(fake: Task, error: Exception, queue: str = "parse") -> None:
    def work() -> None:
        raise error

    pipeline._attempt(fake, work, cast(Any, None), queue)  # pyright: ignore[reportPrivateUsage]


def test_a_database_failure_in_a_task_goes_to_its_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[Any] = []
    monkeypatch.setattr(pipeline, "_run", recorded.append)
    fake, _ = task()
    with pytest.raises(TransientError, match="ConnectionRefusedError"):
        attempt(fake, ConnectionRefusedError("Postgres is down"))
    assert recorded == []  # no dead letter on the first attempt


def test_a_task_out_of_retries_is_dead_lettered_with_its_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[Any] = []
    monkeypatch.setattr(pipeline, "_run", recorded.append)
    fake, _ = task(retries=pipeline.MAX_RETRIES)
    with pytest.raises(Reject):
        attempt(fake, ConnectionRefusedError("Postgres is down"))
    assert "ConnectionRefusedError: Postgres is down" in recorded[0].keywords["error"]


def down(_: Any) -> None:
    raise ConnectionRefusedError("Postgres is down")


def test_a_failure_that_cannot_be_recorded_comes_back_later_and_is_not_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """While Postgres is down the dead letter cannot be written either. Rejecting would leave no
    row, its item running and the job open for good; the task comes back later instead."""
    monkeypatch.setattr(pipeline, "_run", down)
    fake, sent = task()
    attempt(fake, ValueError("no required item"))
    assert len(sent) == 1
    assert sent[0]["queue"] == "parse" and sent[0]["countdown"] > 0
    assert sent[0]["retries"] == 1  # it counts, so a failure that never clears cannot loop


def test_a_failure_that_can_never_be_recorded_is_rejected_loudly_and_does_not_loop(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(pipeline, "_run", down)
    fake, sent = task(retries=pipeline.MAX_RETRIES)
    with pytest.raises(Reject):
        attempt(fake, ValueError("no required item"))
    assert sent == []
    assert "dead letter not recorded" in caplog.text and "no required item" in caplog.text


def test_a_task_sent_back_counts_as_retried(
    monkeypatch: pytest.MonkeyPatch, metric_changes: Callable[[str], dict[str, float]]
) -> None:
    monkeypatch.setattr(pipeline, "_run", down)
    fake, _ = task()
    with suppress(Reject):
        attempt(fake, ValueError("no required item"))
    assert metric_changes("filinglens.ingest.tasks") == {"outcome=retried,task=fetch": 1}
