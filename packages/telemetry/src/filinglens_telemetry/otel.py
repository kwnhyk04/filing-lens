"""OpenTelemetry: traces and metrics to the collector over OTLP/HTTP; nothing without an endpoint.

configure_telemetry builds the SDK providers and installs them as the process's own. Library code
uses only the API (trace.get_tracer and filinglens_telemetry.metrics), which records nothing until
then. Tests install in-memory exporters through the same providers() and install().
"""

import uuid
from typing import Any

from celery import signals  # pyright: ignore[reportMissingTypeStubs]
from opentelemetry import context, metrics, propagate, trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagators.textmap import Getter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Span, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, StatusCode

from filinglens_telemetry import query_names

EXPORT_INTERVAL_MS = 15_000  # the Prometheus scrape interval
EXPORT_TIMEOUT_S = 10.0
tracer = trace.get_tracer("filinglens.celery")


class QueryNames(SpanProcessor):
    """Keep only the parameter names of `url.query`. FastAPI records the values, so search text,
    or a key someone puts in a URL, would otherwise be exported."""

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        query = (span.attributes or {}).get("url.query")
        if isinstance(query, str):
            span.set_attribute("url.query", query_names(query))


def providers(
    service: str, spans: SpanProcessor, reader: MetricReader
) -> tuple[TracerProvider, MeterProvider]:
    """The SDK providers for one process. Each process is its own instance: prefork children that
    pushed the same series would overwrite each other's cumulative counts."""
    resource = Resource.create({"service.name": service, "service.instance.id": uuid.uuid4().hex})
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(QueryNames())
    tracer_provider.add_span_processor(spans)
    return tracer_provider, MeterProvider(resource=resource, metric_readers=[reader])


def install(tracer_provider: TracerProvider, meter_provider: MeterProvider) -> None:
    """Make these the process's providers (possible once per process) and trace Celery messages."""
    trace.set_tracer_provider(tracer_provider)
    metrics.set_meter_provider(meter_provider)
    trace_celery()


def configure_telemetry(service: str, endpoint: str | None) -> None:
    """Export traces and metrics to an OTLP/HTTP endpoint, such as http://otel-collector:4318."""
    if not endpoint:
        return
    base = endpoint.rstrip("/")  # an endpoint given in code gets no /v1/<signal> of its own
    spans = BatchSpanProcessor(
        OTLPSpanExporter(endpoint=f"{base}/v1/traces", timeout=EXPORT_TIMEOUT_S)
    )
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{base}/v1/metrics", timeout=EXPORT_TIMEOUT_S),
        export_interval_millis=EXPORT_INTERVAL_MS,
    )
    install(*providers(service, spans, reader))


def shutdown() -> None:
    """Flush and stop the providers. Prefork children exit through os._exit, which skips the
    SDK's exit hook, so their last spans and metrics would be lost."""
    tracer_provider, meter_provider = trace.get_tracer_provider(), metrics.get_meter_provider()
    if isinstance(tracer_provider, TracerProvider):
        tracer_provider.shutdown()
    if isinstance(meter_provider, MeterProvider):
        meter_provider.shutdown()


class _RequestGetter(Getter[Any]):
    """Reads the trace headers that Celery copies onto task.request."""

    def get(self, carrier: Any, key: str) -> list[str] | None:
        value = getattr(carrier, key, None)
        return [value] if isinstance(value, str) else None

    def keys(self, carrier: Any) -> list[str]:
        return []


_GETTER = _RequestGetter()
_RUNNING: dict[str, tuple[trace.Span, object]] = {}  # task id: its span and context token


def _inject(headers: dict[str, Any] | None = None, **_: Any) -> None:
    """Every published task carries the current trace context. No span starts here, so a publish
    that fails (a nack from a full queue) leaves none open or current."""
    if headers is not None:
        propagate.inject(headers)


def _start(task_id: str, task: Any, **_: Any) -> None:
    parent = propagate.extract(task.request, getter=_GETTER)
    span = tracer.start_span(
        f"run/{str(task.name).rsplit('.', 1)[-1]}",  # run/discover
        context=parent,
        kind=SpanKind.CONSUMER,
        attributes={
            "celery.task_name": task.name,
            "messaging.message.id": task_id,
            "celery.retries": task.request.retries or 0,
        },
    )
    _RUNNING[task_id] = (span, context.attach(trace.set_span_in_context(span, parent)))


def _end(task_id: str, state: str | None = None, **_: Any) -> None:
    running = _RUNNING.pop(task_id, None)
    if running is not None:
        span, token = running
        span.set_attribute("celery.state", state or "")
        context.detach(token)  # type: ignore[arg-type]  # the token attach() returned
        span.end()


def _fail(task_id: str, exception: BaseException | None = None, **_: Any) -> None:
    running = _RUNNING.get(task_id)
    if running is not None:
        running[0].set_status(StatusCode.ERROR)  # no description: messages can hold URLs or data
        running[0].set_attribute("error.type", type(exception).__qualname__)


def _retry(request: Any = None, **_: Any) -> None:
    running = _RUNNING.get(getattr(request, "id", None) or "")
    if running is not None:
        running[0].add_event("retry")


def trace_celery() -> None:
    """Carry trace context through RabbitMQ: publishes inject it and task runs continue it, so an
    ingest job is one trace from the API through every task."""
    for signal, handler in (
        (signals.before_task_publish, _inject),
        (signals.task_prerun, _start),
        (signals.task_postrun, _end),
        (signals.task_failure, _fail),
        (signals.task_retry, _retry),
    ):
        signal.connect(  # pyright: ignore[reportUnknownMemberType]  # celery is untyped
            handler, weak=False, dispatch_uid=f"filinglens-otel{handler.__name__}"
        )
