"""Each ingest task run is counted and timed under its outcome, which its span carries too."""

from collections.abc import Callable
from contextlib import suppress
from types import SimpleNamespace
from typing import Any, cast

import pytest
from celery import Task
from celery.exceptions import Reject
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from filinglens_core.errors import UpstreamError
from filinglens_ingest import pipeline
from filinglens_sec_client import LimiterUnavailableError


@pytest.mark.parametrize(
    ("error", "retries", "outcome"),
    [
        (None, 0, "succeeded"),
        (UpstreamError("SEC answered 503"), 0, "retried"),
        (UpstreamError("SEC answered 503"), pipeline.MAX_RETRIES, "dead_lettered"),
        (ValueError("no required item"), 0, "dead_lettered"),
        (LimiterUnavailableError("Redis is down"), 0, "paused"),
    ],
)
def test_each_run_is_counted_and_timed_under_its_outcome(
    monkeypatch: pytest.MonkeyPatch,
    spans: InMemorySpanExporter,
    metric_changes: Callable[[str], dict[str, float]],
    error: Exception | None,
    retries: int,
    outcome: str,
) -> None:
    monkeypatch.setattr(pipeline, "_run", lambda work: None)  # the dead_letters row
    sent: list[dict[str, Any]] = []
    request = SimpleNamespace(retries=retries, args=[1], kwargs={}, id="task-1")
    task = SimpleNamespace(
        name="filinglens_ingest.pipeline.fetch",
        request=request,
        apply_async=lambda *_, **options: sent.append(options),
    )

    def work() -> None:
        if error is not None:
            raise error

    tracer = trace.get_tracer("tests")
    # retried raises for autoretry, dead_lettered rejects into the DLQ
    with tracer.start_as_current_span("run/fetch"), suppress(UpstreamError, Reject):
        pipeline._attempt(cast(Task, task), work, cast(Any, None), "fetch.retry")  # pyright: ignore[reportPrivateUsage]
    assert metric_changes("filinglens.ingest.tasks") == {f"outcome={outcome},task=fetch": 1}
    assert metric_changes("filinglens.ingest.task.duration") == {"task=fetch": 1}
    [run] = spans.get_finished_spans()
    assert (run.attributes or {})["filinglens.ingest.outcome"] == outcome
    assert len(sent) == (outcome == "paused")  # a pause sends the task again
