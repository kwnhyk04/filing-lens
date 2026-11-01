import json
import logging

import pytest
import structlog

from filinglens_telemetry import REDACTED, configure_logging

API_KEY = "k" * 32


def test_json_lines_carry_context_and_redact_credentials(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("api", "INFO", secrets=[API_KEY])
    structlog.contextvars.bind_contextvars(request_id="req-1")
    try:
        structlog.get_logger("filinglens").info(
            "fetched",
            cik=320193,
            input_tokens=12,
            api_key=API_KEY,
            headers={"Authorization": "Bearer abc", "Accept": "*/*"},
        )
        logging.getLogger("uvicorn.access").info("GET /graphql?key=%s 200", API_KEY)
    finally:
        structlog.contextvars.clear_contextvars()
        structlog.reset_defaults()
        logging.getLogger().handlers.clear()
    out = capsys.readouterr().out
    ours, uvicorn = (json.loads(line) for line in out.splitlines())
    assert API_KEY not in out
    assert ours["event"] == "fetched"
    assert ours["level"] == "info"
    assert ours["service"] == "api"
    assert ours["request_id"] == "req-1"
    assert (ours["cik"], ours["input_tokens"]) == (320193, 12)
    assert ours["api_key"] == REDACTED
    assert ours["headers"] == {"Authorization": REDACTED, "Accept": "*/*"}
    assert uvicorn["event"] == f"GET /graphql?key={REDACTED} 200"
    assert uvicorn["request_id"] == "req-1"


def test_session_ids_are_redacted_like_credentials(capsys: pytest.CaptureFixture[str]) -> None:
    session = "s" * 22
    configure_logging("api")
    try:
        structlog.get_logger("filinglens").info(
            "asked",
            session_id=session,
            headers={"X-Session-ID": session, "Accept": "*/*"},
            sessions=3,  # a count, not an id: it stays
        )
    finally:
        structlog.reset_defaults()
        logging.getLogger().handlers.clear()
    line = json.loads(capsys.readouterr().out)
    assert session not in json.dumps(line)
    assert line["session_id"] == REDACTED
    assert line["headers"] == {"X-Session-ID": REDACTED, "Accept": "*/*"}
    assert line["sessions"] == 3
