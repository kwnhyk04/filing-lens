"""Model providers behind one interface: OpenAI-compatible chat (Groq, OpenRouter, NVIDIA NIM,
Ollama) over httpx, Gemini on google-genai, and Claude on the anthropic SDK. Every call reports
its tokens and latency.

Failures map to the error taxonomy: 429 RateLimitedError and 5xx, timeouts or unreachable hosts
UpstreamError (both transient, so the caller may fall back), 402 (credits used up), 410 (model
retired) and 401/403 AiUnavailableError, which no retry fixes.
"""

import asyncio
import json
import math
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Final, Protocol

import anthropic
import httpx
import httpx2
import structlog
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from filinglens_core.errors import (
    AiUnavailableError,
    FilingLensError,
    RateLimitedError,
    UpstreamError,
)
from filinglens_core.settings import PROVIDER_KEYS, ApiSettings

TIMEOUT = httpx.Timeout(30.0, connect=5.0)  # read and write 30 s, connect 5 s
BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
}
# Claude's list prices in USD per 1M tokens (input, output): prompts up to LONG_PROMPT tokens, then
# longer ones (user and Anthropic's model table, 2026-10-17). Calls spend prepaid credits at these.
CLAUDE_PRICES = {"claude-haiku-5-5": ((0.10, 0.50), (0.50, 2.50))}
LONG_PROMPT = 100_000
# Claude answers with thinking off at effort low (user decision, 2026-10-17): a fast fallback, as
# the primary runs minimal thinking, and the answer cap then holds only text.
CLAUDE_THINKING: Final = "disabled"
CLAUDE_EFFORT: Final = "low"
CLAUDE_RETRY_MAX_S = 10.0  # a 429 that asks for a longer wait goes to the next model instead
# A 400 that means the credits cannot pay: a spend limit you set ("You have reached your specified
# API usage limits", Anthropic's rate-limits page, read 2026-10-17) or an empty credit balance.
CREDITS_GONE = re.compile(r"spend(ing)? limit|usage limit|credit balance", re.IGNORECASE)
log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class Completion:
    model: str  # provider:model
    text: str
    input_tokens: int
    output_tokens: int  # reasoning tokens included
    latency_s: float  # from the request to the last byte
    first_token_s: float | None = None  # streams: from the request to the first text


class Provider(Protocol):
    name: str  # provider:model, as in LLM_PRIMARY

    async def complete(
        self, system: str, user: str, *, max_tokens: int, schema: Mapping[str, Any] | None = None
    ) -> Completion:
        """One answer; with `schema`, JSON that the provider holds to that JSON Schema."""
        ...

    def stream(self, system: str, user: str, *, max_tokens: int) -> AsyncIterator[str | Completion]:
        """Text as it arrives, then one Completion with the whole text and the usage."""
        ...


def failure(provider: str, status: int, retry_after: str | None = None) -> FilingLensError:
    """The taxonomy error for a provider's HTTP status."""
    if status == 429:
        seconds = int(retry_after) if retry_after and retry_after.isdigit() else None
        return RateLimitedError(f"{provider} is rate limited (429).", retry_after_s=seconds)
    if status == 402:
        return AiUnavailableError(f"{provider} has no credits left (402).")
    if status == 410:
        return AiUnavailableError(f"{provider} retired this model (410).")
    if status in (401, 403):
        return AiUnavailableError(f"{provider} refused the API key ({status}).")
    return UpstreamError(f"{provider} answered {status}.")


class OpenAICompatible:
    """POST /chat/completions with a bearer key (none for Ollama)."""

    def __init__(
        self, provider: str, base_url: str, model: str, key: str | None, client: httpx.AsyncClient
    ) -> None:
        self.name = f"{provider}:{model}"
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._model = model
        self._headers = {"Authorization": f"Bearer {key}"} if key else {}
        self._client = client

    def _body(self, system: str, user: str, max_tokens: int, **extra: Any) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            **extra,
        }
        if "gpt-oss" in self._model:
            body["reasoning_effort"] = "low"  # it reasons first; low keeps the latency down
        return body

    async def complete(
        self, system: str, user: str, *, max_tokens: int, schema: Mapping[str, Any] | None = None
    ) -> Completion:
        extra: dict[str, Any] = {}
        if schema is not None:
            json_schema = {"name": "reply", "strict": True, "schema": schema}
            extra["response_format"] = {"type": "json_schema", "json_schema": json_schema}
        started = time.perf_counter()
        try:
            response = await self._client.post(
                self._url, json=self._body(system, user, max_tokens, **extra), headers=self._headers
            )
        except httpx.HTTPError as exc:
            raise UpstreamError(f"{self.name} did not answer ({type(exc).__name__}).") from exc
        if response.status_code != 200:
            raise failure(self.name, response.status_code, response.headers.get("retry-after"))
        data: dict[str, Any] = response.json()
        usage: dict[str, int] = data.get("usage") or {}
        return Completion(
            model=self.name,
            text=data["choices"][0]["message"].get("content") or "",
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            latency_s=time.perf_counter() - started,
        )

    async def stream(
        self, system: str, user: str, *, max_tokens: int
    ) -> AsyncIterator[str | Completion]:
        body = self._body(
            system, user, max_tokens, stream=True, stream_options={"include_usage": True}
        )
        started, first, parts = time.perf_counter(), None, list[str]()
        usage: dict[str, int] = {}
        try:
            async with self._client.stream(
                "POST", self._url, json=body, headers=self._headers
            ) as response:
                if response.status_code != 200:
                    await response.aread()
                    raise failure(
                        self.name, response.status_code, response.headers.get("retry-after")
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    chunk: dict[str, Any] = json.loads(payload)
                    groq: dict[str, Any] = chunk.get("x_groq") or {}  # Groq's last chunk
                    usage = chunk.get("usage") or groq.get("usage") or usage
                    choices: list[dict[str, Any]] = chunk.get("choices") or []
                    for choice in choices:
                        delta: dict[str, Any] = choice.get("delta") or {}
                        text: str | None = delta.get("content")
                        if text:
                            first = first or time.perf_counter() - started
                            parts.append(text)
                            yield text
        except httpx.HTTPError as exc:
            raise UpstreamError(f"{self.name} did not answer ({type(exc).__name__}).") from exc
        yield Completion(
            model=self.name,
            text="".join(parts),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            latency_s=time.perf_counter() - started,
            first_token_s=first,
        )


class Gemini:
    """Gemini API (not Vertex AI) through google-genai, on the shared httpx client.

    The SDK sends the key in the x-goog-api-key header, never in the URL (?key=), and the key
    passed here wins over GOOGLE_API_KEY or GEMINI_API_KEY in the environment.
    """

    def __init__(
        self, model: str, key: str, client: httpx.AsyncClient, *, minimal_thinking: bool = True
    ) -> None:
        self.name = f"gemini:{model}"
        self._model = model
        self._minimal_thinking = minimal_thinking  # False: the model's default (evals compare)
        options = types.HttpOptions(
            httpx_async_client=client,
            retry_options=types.HttpRetryOptions(attempts=1),  # the caller falls back instead
        )
        self._client = genai.Client(api_key=key, vertexai=False, http_options=options)

    def _config(self, system: str, max_tokens: int, schema: Mapping[str, Any] | None) -> Any:
        minimal = types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL)
        return types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            thinking_config=minimal if self._minimal_thinking else None,
            response_mime_type="application/json" if schema is not None else None,
            response_json_schema=dict(schema) if schema is not None else None,
        )

    async def complete(
        self, system: str, user: str, *, max_tokens: int, schema: Mapping[str, Any] | None = None
    ) -> Completion:
        started = time.perf_counter()
        try:
            response = await self._client.aio.models.generate_content(  # pyright: ignore[reportUnknownMemberType]
                model=self._model, contents=user, config=self._config(system, max_tokens, schema)
            )
        except genai_errors.APIError as exc:
            raise failure(self.name, exc.code) from exc
        except httpx.HTTPError as exc:
            raise UpstreamError(f"{self.name} did not answer ({type(exc).__name__}).") from exc
        prompt, output = _usage(response.usage_metadata)
        return Completion(
            self.name, response.text or "", prompt, output, time.perf_counter() - started
        )

    async def stream(
        self, system: str, user: str, *, max_tokens: int
    ) -> AsyncIterator[str | Completion]:
        started, first, parts = time.perf_counter(), None, list[str]()
        usage: types.GenerateContentResponseUsageMetadata | None = None
        try:
            chunks = await self._client.aio.models.generate_content_stream(  # pyright: ignore[reportUnknownMemberType]
                model=self._model, contents=user, config=self._config(system, max_tokens, None)
            )
            async for chunk in chunks:
                usage = chunk.usage_metadata or usage
                if chunk.text:
                    first = first or time.perf_counter() - started
                    parts.append(chunk.text)
                    yield chunk.text
        except genai_errors.APIError as exc:
            raise failure(self.name, exc.code) from exc
        except httpx.HTTPError as exc:
            raise UpstreamError(f"{self.name} did not answer ({type(exc).__name__}).") from exc
        prompt, output = _usage(usage)
        yield Completion(
            self.name, "".join(parts), prompt, output, time.perf_counter() - started, first
        )


def _usage(usage: types.GenerateContentResponseUsageMetadata | None) -> tuple[int, int]:
    if usage is None:
        return 0, 0
    output = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
    return usage.prompt_token_count or 0, output


def credits_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """What one call cost in prepaid credits: Claude at its list price, the free tiers nothing."""
    name, _, model_id = model.partition(":")
    if name != "anthropic":
        return 0.0
    short, long = CLAUDE_PRICES[model_id]
    rate_in, rate_out = long if input_tokens > LONG_PROMPT else short
    return (input_tokens * rate_in + output_tokens * rate_out) / 1e6


def _retry_after(headers: Mapping[str, str]) -> float | None:
    """The wait a 429 asks for in seconds, or None when it names none, as the 429 of a reached
    spend cap does; an unreadable value counts as a long wait."""
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        return math.inf


class Anthropic:
    """Claude on the Anthropic API through the official SDK, paid from prepaid credits.

    Credits gone (a 402, a 400 that names a spend limit or the credit balance, or a 429 without
    Retry-After) turn it off for the rest of the credit period, and so does the day the credits
    expire (UTC): each call then fails at once without a request, and the answer chain skips it
    (`off`). A 429 that asks for CLAUDE_RETRY_MAX_S or less is retried once. It writes answers only,
    never JSON replies, so settings keep it out of routing and judging.
    """

    def __init__(
        self,
        model: str,
        key: str,
        *,
        expires: date,
        today: Callable[[], date] = lambda: datetime.now(UTC).date(),
        http_client: httpx2.AsyncClient | None = None,  # tests pass a mock transport
    ) -> None:
        if model not in CLAUDE_PRICES:
            raise ValueError(f"anthropic:{model} has no price in CLAUDE_PRICES.")
        self.name = f"anthropic:{model}"
        self._model = model
        self._expires = expires
        self._today = today
        self._client = anthropic.AsyncAnthropic(
            api_key=key,
            timeout=anthropic.Timeout(30.0, connect=5.0),
            max_retries=0,  # only a short 429 is retried (_send); the answer chain covers the rest
            http_client=http_client,
        )
        # ponytail: per process, so a restart learns it again from one refused call; keep it in
        # Redis if restarts get frequent.
        self._gone: str | None = None

    def off(self) -> str | None:
        """Why Claude is skipped for the rest of the credit period, or None while it may answer."""
        if self._gone is None and self._today() >= self._expires:
            self._stop(f"its credits expired on {self._expires.isoformat()}")
        return self._gone

    def _stop(self, reason: str) -> AiUnavailableError:
        """Turn Claude off for the rest of the credit period, with one log line."""
        self._gone = reason
        log.warning(
            "claude is off for the rest of the credit period",
            model=self.name,
            reason=reason,
            credits_expire=self._expires.isoformat(),
        )
        return self._unavailable()

    def _unavailable(self) -> AiUnavailableError:
        return AiUnavailableError(f"{self.name} is off for the credit period: {self._gone}.")

    async def _send[T](self, request: Callable[[], Awaitable[T]], *, retry: bool = True) -> T:
        """`request` while Claude is on, once more after a short 429; credits gone stop Claude."""
        if self.off():
            raise self._unavailable()
        try:
            return await request()
        except anthropic.RateLimitError as exc:
            wait = _retry_after(exc.response.headers)
            if wait is None:
                raise self._stop("429 without Retry-After (spend cap reached)") from exc
            if not retry or wait > CLAUDE_RETRY_MAX_S:
                seconds = math.ceil(wait) if math.isfinite(wait) else None
                message = f"{self.name} is rate limited (429)."
                raise RateLimitedError(message, retry_after_s=seconds) from exc
        except anthropic.APIStatusError as exc:
            credits = exc.status_code == 400 and CREDITS_GONE.search(exc.message)
            if exc.status_code == 402 or credits:
                raise self._stop(f"{exc.status_code} {exc.type or 'error'}: {exc.message}") from exc
            raise failure(self.name, exc.status_code) from exc
        except anthropic.APIConnectionError as exc:  # timeouts included
            raise UpstreamError(f"{self.name} did not answer ({type(exc).__name__}).") from exc
        await asyncio.sleep(wait)
        return await self._send(request, retry=False)

    async def complete(
        self, system: str, user: str, *, max_tokens: int, schema: Mapping[str, Any] | None = None
    ) -> Completion:
        if schema is not None:
            raise NotImplementedError(f"{self.name} writes answers only, not JSON replies.")
        started = time.perf_counter()
        message = await self._send(
            lambda: self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                thinking={"type": CLAUDE_THINKING},
                output_config={"effort": CLAUDE_EFFORT},
            )
        )
        if message.stop_reason == "refusal":
            raise UpstreamError(f"{self.name} declined to answer (refusal).")
        text = "".join(block.text for block in message.content if block.type == "text")
        usage = message.usage
        return Completion(
            self.name, text, usage.input_tokens, usage.output_tokens, time.perf_counter() - started
        )

    async def stream(
        self, system: str, user: str, *, max_tokens: int
    ) -> AsyncIterator[str | Completion]:
        started, first, parts = time.perf_counter(), None, list[str]()
        events = await self._send(
            lambda: self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                thinking={"type": CLAUDE_THINKING},
                output_config={"effort": CLAUDE_EFFORT},
                stream=True,
            )
        )
        input_tokens = output_tokens = 0
        stop_reason = None
        try:
            async with events:
                async for event in events:  # only text deltas are the answer
                    if event.type == "message_start":
                        input_tokens = event.message.usage.input_tokens
                    elif event.type == "content_block_delta" and event.delta.type == "text_delta":
                        first = first or time.perf_counter() - started
                        parts.append(event.delta.text)
                        yield event.delta.text
                    elif event.type == "message_delta":
                        output_tokens = event.usage.output_tokens
                        stop_reason = event.delta.stop_reason
        except anthropic.APIStatusError as exc:  # an error event after the stream began
            raise UpstreamError(f"{self.name} failed mid-answer ({exc.type or 'error'}).") from exc
        except (anthropic.APIConnectionError, httpx2.HTTPError) as exc:
            raise UpstreamError(f"{self.name} did not answer ({type(exc).__name__}).") from exc
        if stop_reason == "refusal":
            raise UpstreamError(f"{self.name} declined to answer (refusal).")
        yield Completion(
            self.name, "".join(parts), input_tokens, output_tokens,
            time.perf_counter() - started, first,
        )  # fmt: skip


def provider(role: str, settings: ApiSettings, client: httpx.AsyncClient) -> Provider:
    """The provider for a role such as LLM_PRIMARY (provider:model), with its key from settings.
    Claude keeps its own HTTP client: the anthropic SDK runs on httpx2."""
    name, _, model = role.partition(":")
    field = PROVIDER_KEYS[name]
    secret = getattr(settings, field) if field else None
    key = secret.get_secret_value() if secret is not None else None
    if name == "gemini":
        return Gemini(model, key or "", client)
    if name == "anthropic":
        return Anthropic(model, key or "", expires=settings.anthropic_credits_expire)
    base_url = str(settings.ollama_url) if name == "ollama" else BASE_URLS[name]
    return OpenAICompatible(name, base_url, model, key, client)
