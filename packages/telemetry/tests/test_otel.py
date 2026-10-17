"""OpenTelemetry setup and our own Celery propagation, on the session's in-memory providers."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import structlog
from celery import Celery
from kombu import Producer
from kombu.exceptions import OperationalError
from opentelemetry import trace
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from filinglens_telemetry import configure_logging, otel

TRACER = trace.get_tracer("tests")


def test_nothing_is_set_up_without_an_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    installed: list[object] = []
    monkeypatch.setattr(otel, "install", lambda *providers: installed.append(providers))
    otel.configure_telemetry("filinglens-api", None)
    otel.configure_telemetry("filinglens-api", "")
    assert installed == []


def test_each_process_is_its_own_instance_of_its_service() -> None:
    resources = [
        otel.providers(
            "filinglens-ingest", SimpleSpanProcessor(InMemorySpanExporter()), InMemoryMetricReader()
        )[0].resource.attributes
        for _ in range(2)
    ]
    assert [r["service.name"] for r in resources] == ["filinglens-ingest"] * 2
    assert resources[0]["service.instance.id"] != resources[1]["service.instance.id"]


def test_url_query_keeps_parameter_names_only(spans: InMemorySpanExporter) -> None:
    with TRACER.start_as_current_span("GET /v1/search", attributes={"url.query": "q=merger+talks"}):
        pass
    TRACER.start_span("GET", attributes={"url.query": "q=a&cursor=b&cik="}).end()
    # A part without `=`, or a long name, may be a value: words, or a key pasted into the URL.
    loose = f"what+did+apple+say&q=x&{'k' * 32}=1&sk-live-{'x' * 24}&"
    TRACER.start_span("GET", attributes={"url.query": loose}).end()
    first, second, third = spans.get_finished_spans()
    assert (first.attributes or {})["url.query"] == "q"
    assert (second.attributes or {})["url.query"] == "q&cursor&cik"
    assert (third.attributes or {})["url.query"] == "_&q&_&_"


def test_log_lines_inside_a_span_carry_its_trace(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("api")
    with TRACER.start_as_current_span("request") as span:
        structlog.get_logger("filinglens").info("inside")
    structlog.get_logger("filinglens").info("outside")
    inside, outside = (json.loads(line) for line in capsys.readouterr().out.splitlines())
    context = span.get_span_context()
    assert inside["trace_id"] == format(context.trace_id, "032x")
    assert inside["span_id"] == format(context.span_id, "016x")
    assert "trace_id" not in outside


def _task(name: str, headers: dict[str, str]) -> SimpleNamespace:
    """A task as the signals see it: the message headers copied onto task.request."""
    return SimpleNamespace(name=name, request=SimpleNamespace(retries=0, **headers))


def test_a_task_continues_the_trace_of_the_message_that_queued_it(
    spans: InMemorySpanExporter,
) -> None:
    headers: dict[str, str] = {}
    with TRACER.start_as_current_span("POST /v1/ingest-jobs") as request:
        otel._inject(headers=headers)  # pyright: ignore[reportPrivateUsage]
    before = trace.get_current_span()
    otel._start("task-1", _task("filinglens_ingest.pipeline.discover", headers))  # pyright: ignore[reportPrivateUsage]
    running = trace.get_current_span()  # current while the task runs
    otel._fail("task-1", ValueError("https://data.sec.gov/... answered 500"))  # pyright: ignore[reportPrivateUsage]
    otel._end("task-1", "FAILURE")  # pyright: ignore[reportPrivateUsage]
    assert trace.get_current_span() is before  # detached again
    _, run = spans.get_finished_spans()
    assert run.name == "run/discover" and run.kind == SpanKind.CONSUMER
    assert run.context is not None
    assert run.context.span_id == running.get_span_context().span_id
    assert run.context.trace_id == request.get_span_context().trace_id
    assert run.parent is not None and run.parent.span_id == request.get_span_context().span_id
    assert run.status.status_code == StatusCode.ERROR and run.status.description is None
    assert (run.attributes or {})["error.type"] == "ValueError"
    assert "data.sec.gov" not in run.to_json()


def test_a_failed_publish_leaves_no_span_open_or_current(spans: InMemorySpanExporter) -> None:
    """Discover's nack on a full fetch queue: the publish raises after before_task_publish."""
    app = Celery("tests", broker="memory://", set_as_current=False)
    nacked = OperationalError("nacked: the fetch queue is full")
    with TRACER.start_as_current_span("run/discover") as running:
        with (
            patch.object(Producer, "publish", side_effect=nacked) as publish,
            pytest.raises(OperationalError),
        ):
            app.send_task("filinglens_ingest.pipeline.fetch", args=[1], retry=False)
        assert trace.get_current_span() is running
    trace_id = format(running.get_span_context().trace_id, "032x")
    assert trace_id in publish.call_args.kwargs["headers"]["traceparent"]  # the message had it
    assert [span.name for span in spans.get_finished_spans()] == ["run/discover"]
