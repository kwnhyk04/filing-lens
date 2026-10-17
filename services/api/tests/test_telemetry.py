"""The API's request spans, HTTP metrics and access log, and the labels every metric may carry.

The session's in-memory providers stand in for the collector (the root conftest).
"""

import json
import logging
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from filinglens_api.backend import get_backend
from filinglens_api.main import app
from filinglens_telemetry import configure_logging

QUERY = "merger talks with Qualcomm"
CURSOR = "an-opaque-cursor-value"


@pytest.fixture
def traced(env: pytest.MonkeyPatch, fake: Any) -> Iterator[TestClient]:
    """The app over the in-memory backend; the rate limits fail open, since Redis is down."""
    app.dependency_overrides[get_backend] = lambda: fake
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def test_a_request_span_has_its_route_request_id_and_query_names_only(
    traced: TestClient,
    api_key: str,
    spans: InMemorySpanExporter,
    metric_changes: Callable[[str], dict[str, float]],
) -> None:
    headers = {"X-API-Key": api_key, "X-Request-ID": "req-42"}
    assert traced.get("/v1/search", params={"q": QUERY, "limit": 2}, headers=headers).is_success
    traced.get("/healthz")
    traced.get("/readyz")  # the probes leave no span and no metric
    [server] = spans.get_finished_spans()
    attributes = server.attributes or {}
    assert server.name == "GET /v1/search" and server.kind == SpanKind.SERVER
    assert attributes["request_id"] == "req-42"  # Jaeger finds the trace of a reported request
    assert attributes["url.query"] == "q&limit"
    assert attributes["http.route"] == "/v1/search"
    assert attributes["http.response.status_code"] == 200
    [labels] = metric_changes("http.server.request.duration")
    assert "http.route=/v1/search" in labels and "http.response.status_code=200" in labels


def test_no_key_and_no_query_value_reaches_a_span(
    traced: TestClient, api_key: str, admin_key: str, spans: InMemorySpanExporter
) -> None:
    unknown = "w" * 32
    traced.get(
        "/v1/search", params={"q": QUERY, "api_key": admin_key}, headers={"X-API-Key": api_key}
    )
    traced.post("/graphql", json={"query": "{ __typename }"}, headers={"X-API-Key": admin_key})
    assert traced.get("/v1/companies", headers={"X-API-Key": unknown}).status_code == 401
    exported = "".join(span.to_json() for span in spans.get_finished_spans())
    assert len(spans.get_finished_spans()) == 3
    for secret in (api_key, admin_key, unknown, "Qualcomm"):
        assert secret not in exported


def test_access_lines_keep_query_names_only(
    serve: Callable[..., AbstractContextManager[str]],
    fake: Any,
    api_key: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app.dependency_overrides[get_backend] = lambda: fake  # serve clears the overrides
    configure_logging("api")  # its handler writes to the captured stdout
    # As in a fresh API process: a server started with access_log=False (the other tests') stops
    # uvicorn.access from propagating, and one with the access log on does not undo it.
    monkeypatch.setattr(logging.getLogger("uvicorn.access"), "propagate", True)
    with serve(access_log=True) as url:
        params, headers = {"q": QUERY, "cursor": CURSOR}, {"X-API-Key": api_key}
        httpx2.get(f"{url}/v1/search", params=params, headers=headers, timeout=10)
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    [access] = [line for line in lines if line.get("logger") == "uvicorn.access"]
    assert '"GET /v1/search?q&cursor HTTP/1.1" 400' in access["event"]  # the fake's bad cursor
    server = json.dumps([line for line in lines if line.get("logger") != "httpx2"])  # not ours
    assert "Qualcomm" not in server and CURSOR not in server


def test_a_404_records_no_route_and_no_path(
    traced: TestClient, api_key: str, metric_changes: Callable[[str], dict[str, float]]
) -> None:
    """The root conftest checks every series' labels after the session; a path is never one."""
    traced.get(f"/v1/{QUERY}", headers={"X-API-Key": api_key})
    [labels] = metric_changes("http.server.request.duration")
    assert "http.route" not in labels and "merger" not in labels
