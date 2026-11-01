"""Structured logging with structlog: one JSON object per line on stdout, credentials redacted.

OpenTelemetry lives in filinglens_telemetry.otel (setup) and .metrics (instruments).
"""

import logging
import re
import sys
from collections.abc import Iterable, Mapping
from typing import Any, cast
from urllib.parse import unquote_plus

import structlog
from opentelemetry import trace
from structlog.types import EventDict, Processor, WrappedLogger

REDACTED = "[REDACTED]"
# Credential-bearing field and header names, and session ids; counters such as input_tokens stay.
SENSITIVE_KEY = re.compile(
    r"(^|[-_])(authorization|cookie|api[-_]?key|password|secret|token|session([-_]?id)?)$", re.I
)
PARAMETER = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,23}")  # a query parameter's name


def _scrub_fields(fields: Mapping[Any, object], secrets: tuple[str, ...]) -> dict[Any, object]:
    return {
        key: REDACTED if SENSITIVE_KEY.search(str(key)) else _scrub(value, secrets)
        for key, value in fields.items()
    }


def _scrub(value: object, secrets: tuple[str, ...]) -> object:
    if isinstance(value, dict):
        return _scrub_fields(cast("dict[object, object]", value), secrets)
    if isinstance(value, list | tuple):
        return [_scrub(item, secrets) for item in cast("Iterable[object]", value)]
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, REDACTED)
    return value


def query_names(query: str) -> str:
    """A query string with its values dropped: `q=supply+chain&cursor=x` becomes `q&cursor`.

    A part without `=`, or a name that is not short and plain, becomes `_`: it may be a value,
    such as search words or a key pasted into the URL (keys are at least 32 characters).
    """
    names = (
        name if mark and PARAMETER.fullmatch(name := unquote_plus(raw)) else "_"
        for raw, mark, _ in (part.partition("=") for part in query.split("&") if part)
    )
    return "&".join(names)


class _QueryNames(logging.Filter):
    """Keeps only parameter names in uvicorn's access lines, so search text is never logged."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            path, mark, query = args[2].partition("?")
            if mark:
                record.args = (args[0], args[1], f"{path}?{query_names(query)}", *args[3:])
        return True


def _add_trace_ids(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """Lines written inside a span carry its trace and span ids, so a log line finds its trace."""
    span = trace.get_current_span().get_span_context()
    if span.is_valid:
        event_dict["trace_id"] = format(span.trace_id, "032x")
        event_dict["span_id"] = format(span.span_id, "016x")
    return event_dict


def configure_logging(service: str, level: str = "INFO", secrets: Iterable[str] = ()) -> None:
    """Send every logger (ours, uvicorn, celery, alembic) to stdout as JSON.

    Credential-named fields are redacted, and so is any occurrence of a value in `secrets`.
    Uvicorn's access lines keep only the names of query parameters.
    """
    known = tuple(secret for secret in secrets if secret)
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, _QueryNames) for f in access.filters):
        access.addFilter(_QueryNames())

    def add_service(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
        event_dict["service"] = service
        return event_dict

    def redact(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
        return _scrub_fields(event_dict, known)

    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,  # request_id and other bound context
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        add_service,
        _add_trace_ids,
    ]
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,  # records from stdlib loggers such as uvicorn and celery
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            redact,  # after format_exc_info, so tracebacks are scrubbed too
            structlog.processors.JSONRenderer(),
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logging.basicConfig(level=level, handlers=[handler], force=True)
