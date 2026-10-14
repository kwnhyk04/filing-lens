"""Structured logging with structlog: one JSON object per line on stdout, credentials redacted."""

import logging
import re
import sys
from collections.abc import Iterable, Mapping
from typing import Any, cast

import structlog
from structlog.types import EventDict, Processor, WrappedLogger

REDACTED = "[REDACTED]"
# Credential-bearing field and header names; counters such as input_tokens stay visible.
SENSITIVE_KEY = re.compile(
    r"(^|[-_])(authorization|cookie|api[-_]?key|password|secret|token)$", re.I
)


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


def configure_logging(service: str, level: str = "INFO", secrets: Iterable[str] = ()) -> None:
    """Send every logger (ours, uvicorn, celery, alembic) to stdout as JSON.

    Credential-named fields are redacted, and so is any occurrence of a value in `secrets`.
    """
    known = tuple(secret for secret in secrets if secret)

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
