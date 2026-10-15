"""Model providers behind one interface: OpenAI-compatible chat (Groq, OpenRouter, NVIDIA NIM,
Ollama) over httpx, and Gemini on google-genai. Every call reports its tokens and latency.

Failures map to the error taxonomy: 429 RateLimitedError and 5xx, timeouts or unreachable hosts
UpstreamError (both transient, so the caller may fall back), 402 (credits used up) and 401/403
AiUnavailableError, which no retry fixes.
"""

import json
import time
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
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

    def __init__(self, model: str, key: str, client: httpx.AsyncClient) -> None:
        self.name = f"gemini:{model}"
        self._model = model
        options = types.HttpOptions(
            httpx_async_client=client,
            retry_options=types.HttpRetryOptions(attempts=1),  # the caller falls back instead
        )
        self._client = genai.Client(api_key=key, vertexai=False, http_options=options)

    def _config(self, system: str, max_tokens: int, schema: Mapping[str, Any] | None) -> Any:
        return types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
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


def provider(role: str, settings: ApiSettings, client: httpx.AsyncClient) -> Provider:
    """The provider for a role such as LLM_PRIMARY (provider:model), with its key from settings."""
    name, _, model = role.partition(":")
    field = PROVIDER_KEYS[name]
    secret = getattr(settings, field) if field else None
    key = secret.get_secret_value() if secret is not None else None
    if name == "gemini":
        return Gemini(model, key or "", client)
    base_url = str(settings.ollama_url) if name == "ollama" else BASE_URLS[name]
    return OpenAICompatible(name, base_url, model, key, client)
