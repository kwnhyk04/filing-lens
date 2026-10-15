"""SecClient over a mocked EDGAR (respx), and the network guard that keeps every test off the web.

The integration tests run the client against a fake SEC server with a real Redis; these need
neither. The stand-in Redis always grants the rate limit and holds no SEC refusal.
"""

import asyncio
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
import respx

from filinglens_core.errors import UpstreamError
from filinglens_sec_client import SecClient
from network_guard import NetworkBlockedError

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
