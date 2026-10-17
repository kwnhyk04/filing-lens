"""SecClient over a mocked EDGAR (respx), and the network guard that keeps every test off the web.

The integration tests run the client against a fake SEC server with a real Redis; these need
neither. The stand-in Redis always grants the rate limit and holds no SEC refusal.
"""

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import httpx
import pytest
import respx
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from filinglens_core.errors import RateLimitedError, UpstreamError
from filinglens_sec_client import SecClient, SecRefusedError
from network_guard import NetworkBlockedError

type Changes = Callable[[str], dict[str, float]]

AGENT = "FilingLens tests tests@filinglens.test"
ACCESSION, NAME = "0000320193-25-000079", "aapl-20250927.htm"
DOCUMENT = f"https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/{NAME}"
# EDGAR, Gemini, Groq, Cloudflare Workers AI and the Hugging Face hub.
HOSTS = [
    "www.sec.gov",
    "data.sec.gov",
    "generativelanguage.googleapis.com",
    "api.groq.com",
    "api.cloudflare.com",
    "huggingface.co",
]


def sec_client(cache: Path) -> SecClient:
    redis = Mock()
    redis.register_script.return_value = lambda **_: [1, 0]  # a token, no wait
    redis.get.return_value = None  # no refusal recorded
    return SecClient(
        user_agent=AGENT,
        www_url="https://www.sec.gov",
        data_url="https://data.sec.gov",
        cache_dir=cache,
        redis=redis,
    )


@respx.mock
def test_requests_carry_the_user_agent_and_both_timeouts(tmp_path: Path) -> None:
    route = respx.get(DOCUMENT).respond(200, content=b"<html>10-K</html>")
    assert sec_client(tmp_path).document(320193, ACCESSION, NAME) == b"<html>10-K</html>"
    request = route.calls.last.request
    assert request.headers["User-Agent"] == AGENT
    timeouts = {"connect": 5.0, "read": 30.0, "write": 30.0, "pool": 30.0}
    assert request.extensions["timeout"] == timeouts


@pytest.mark.parametrize("timeout", [httpx.ConnectTimeout, httpx.ReadTimeout])
@respx.mock
def test_a_timeout_is_a_transient_upstream_error(
    tmp_path: Path, timeout: type[httpx.TimeoutException]
) -> None:
    respx.get(DOCUMENT).mock(side_effect=timeout)
    with pytest.raises(UpstreamError, match=f"SEC request failed \\({timeout.__name__}\\)"):
        sec_client(tmp_path).document(320193, ACCESSION, NAME)


@respx.mock
def test_each_request_is_counted_and_traced_without_the_user_agent(
    tmp_path: Path, spans: InMemorySpanExporter, metric_changes: Changes
) -> None:
    respx.get(DOCUMENT).respond(200, content=b"<html>10-K</html>")
    client = sec_client(tmp_path)
    client.document(320193, ACCESSION, NAME)
    client.document(320193, ACCESSION, NAME)  # from the cache: no request
    assert metric_changes("filinglens.sec.requests") == {"kind=document,status=200": 1}
    sent, cached = spans.get_finished_spans()
    assert sent.name == "SEC GET document" and sent.kind == SpanKind.CLIENT
    assert (sent.attributes or {})["http.response.status_code"] == 200
    assert (sent.attributes or {})["filinglens.sec.cache_hit"] is False
    assert (cached.attributes or {})["filinglens.sec.cache_hit"] is True
    assert "tests@filinglens.test" not in sent.to_json() + cached.to_json()


@respx.mock
def test_a_429_cools_off_and_a_recorded_refusal_fails_without_a_request(
    tmp_path: Path, spans: InMemorySpanExporter, metric_changes: Changes
) -> None:
    respx.get(DOCUMENT).respond(429, headers={"Retry-After": "5"})
    client = sec_client(tmp_path)
    with pytest.raises(RateLimitedError):
        client.document(320193, ACCESSION, NAME)
    refused = sec_client(tmp_path)
    cast(Mock, refused._redis).get.return_value = b"SEC still refuses requests."  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(SecRefusedError):
        refused.document(320193, ACCESSION, NAME)
    assert metric_changes("filinglens.sec.requests") == {"kind=document,status=429": 1}
    assert metric_changes("filinglens.sec.cooloffs") == {"status=429": 1}
    assert metric_changes("filinglens.sec.refusals") == {"": 1}
    throttled, stopped = spans.get_finished_spans()
    assert throttled.status.status_code == stopped.status.status_code == StatusCode.ERROR
    assert (stopped.attributes or {})["error.type"] == "SecRefusedError"


def test_the_sec_client_cannot_reach_sec_in_tests(tmp_path: Path) -> None:
    with pytest.raises(NetworkBlockedError, match=r"www\.sec\.gov"):
        sec_client(tmp_path).document(320193, ACCESSION, NAME)


@pytest.mark.parametrize("host", HOSTS)
def test_no_test_reaches_sec_or_a_model_provider(host: str) -> None:
    with pytest.raises(NetworkBlockedError, match=host):
        httpx.get(f"https://{host}/", timeout=5)

    async def connect() -> None:  # the asyncio clients resolve hosts through the same lookup
        await asyncio.open_connection(host, 443)

    with pytest.raises(NetworkBlockedError, match=host):
        asyncio.run(connect())
