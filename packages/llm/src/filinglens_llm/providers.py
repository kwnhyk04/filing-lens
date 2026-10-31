"""Model providers behind one interface: OpenAI-compatible chat (Groq, OpenRouter, NVIDIA NIM,
Ollama) over httpx, Gemini on google-genai, and Claude on the anthropic SDK. Every call reports
its tokens and latency.

Failures map to the error taxonomy: 429 RateLimitedError and 5xx, timeouts or unreachable hosts
UpstreamError (both transient, so the caller may fall back), 402 (credits used up), 410 (model
retired) and 401/403 AiUnavailableError, which no retry fixes.
"""

import asyncio
import functools
import json
import math
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Concatenate, Final, Protocol, cast

import anthropic
import httpx
import httpx2
import structlog
from anthropic.types import OutputConfigParam
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from opentelemetry import trace
from opentelemetry.trace import SpanKind, StatusCode
from redis.exceptions import RedisError

from filinglens_core.errors import (
    AiUnavailableError,
    FilingLensError,
    RateLimitedError,
    UpstreamError,
)
from filinglens_core.settings import PROVIDER_KEYS, ApiSettings
from filinglens_llm.budget import ClaudeLedger, seconds_to_midnight
from filinglens_telemetry import metrics

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
CLAUDE_MAX_TOKENS = 1052  # 956, the most Claude wrote with thinking off (122 calls), plus 10%
# A 400 that means the credits cannot pay: a spend limit you set ("You have reached your specified
# API usage limits", Anthropic's rate-limits page, read 2026-10-17) or an empty credit balance.
CREDITS_GONE = re.compile(r"spend(ing)? limit|usage limit|credit balance", re.IGNORECASE)
log = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


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

    def complete(
        self, system: str, user: str, *, max_tokens: int, schema: Mapping[str, Any] | None = None
    ) -> Awaitable[Completion]:
        """One answer; with `schema`, JSON that the provider holds to that JSON Schema."""
        ...

    def stream(self, system: str, user: str, *, max_tokens: int) -> AsyncIterator[str | Completion]:
        """Text as it arrives, then one Completion with the whole text and the usage."""
        ...


class _Named(Protocol):
    name: str  # provider:model


def _span(name: str) -> trace.Span:
    """A model call's span: the GenAI names, never the prompt or the reply. It is not made
    current: nothing nests under it, and a stream's span lives across yields."""
    provider, _, model = name.partition(":")
    attributes = {
        "gen_ai.provider.name": provider,
        "gen_ai.request.model": model,
        "gen_ai.operation.name": "chat",
    }
    return tracer.start_span(f"chat {model}", kind=SpanKind.CLIENT, attributes=attributes)


def _done(
    name: str,
    span: trace.Span,
    started: float,
    completion: Completion | None,
    error: Exception | None,
) -> None:
    provider, _, model = name.partition(":")
    labels = {"gen_ai.provider.name": provider, "gen_ai.request.model": model}
    if error is not None:
        kind = error.code if isinstance(error, FilingLensError) else type(error).__qualname__
        span.set_status(StatusCode.ERROR)  # no description: provider messages can echo input
        span.set_attribute("error.type", kind)
        labels["error.type"] = kind
    if completion is not None:
        span.set_attributes(
            {
                "gen_ai.usage.input_tokens": completion.input_tokens,
                "gen_ai.usage.output_tokens": completion.output_tokens,
            }
        )
        for token_type, tokens in (
            ("input", completion.input_tokens),
            ("output", completion.output_tokens),
        ):
            metrics.LLM_TOKENS.record(tokens, {**labels, "gen_ai.token.type": token_type})
    metrics.LLM_DURATION.record(time.perf_counter() - started, labels)
    outcome = "error" if error is not None else "ok"
    metrics.LLM_CALLS.add(1, {"provider": provider, "model": model, "outcome": outcome})
    span.end()


def traced_complete[S: _Named, **P](
    call: Callable[Concatenate[S, P], Awaitable[Completion]],
) -> Callable[Concatenate[S, P], Awaitable[Completion]]:
    """A model call's span and metrics (gen_ai.client.*, filinglens.llm.calls)."""

    @functools.wraps(call)
    async def complete(self: S, *args: P.args, **kwargs: P.kwargs) -> Completion:
        span, started = _span(self.name), time.perf_counter()
        try:
            completion = await call(self, *args, **kwargs)
        except Exception as error:
            _done(self.name, span, started, None, error)
            raise
        except BaseException:  # cancelled: not the provider's failure
            span.end()
            raise
        _done(self.name, span, started, completion, None)
        return completion

    return complete


def traced_stream[S: _Named, **P](
    call: Callable[Concatenate[S, P], AsyncIterator[str | Completion]],
) -> Callable[Concatenate[S, P], AsyncIterator[str | Completion]]:
    """traced_complete for streams, with an event at the first text."""

    @functools.wraps(call)
    async def stream(self: S, *args: P.args, **kwargs: P.kwargs) -> AsyncIterator[str | Completion]:
        span, started = _span(self.name), time.perf_counter()
        completion: Completion | None = None
        first = True
        try:
            async for item in call(self, *args, **kwargs):
                if isinstance(item, Completion):
                    completion = item
                elif first:
                    first = False
                    span.add_event("first_token")
                yield item
        except Exception as error:
            _done(self.name, span, started, None, error)
            raise
        except BaseException:  # cancelled, or closed early by its reader
            span.end()
            raise
        _done(self.name, span, started, completion, None)

    return stream


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

    @traced_complete
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

    @traced_stream
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

    @traced_complete
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

    @traced_stream
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


def claude_schema(node: Any) -> Any:
    """A JSON Schema in the form Claude's structured outputs take: a nullable enum, such as the
    router's {"type": ["string", "null"], "enum": [..., null]}, becomes anyOf an enum and null,
    since the API refuses the first form (400, live check 2026-10-31)."""
    if isinstance(node, list):
        return [claude_schema(item) for item in cast(list[Any], node)]
    if not isinstance(node, dict):
        return node
    fields = {key: claude_schema(value) for key, value in cast(dict[str, Any], node).items()}
    kinds = cast(list[str], fields["type"]) if isinstance(fields.get("type"), list) else []
    if "null" in kinds and len(kinds) == 2 and "enum" in fields:
        kind = next(kind for kind in kinds if kind != "null")
        values = [value for value in cast(list[Any], fields["enum"]) if value is not None]
        rest = {key: value for key, value in fields.items() if key not in ("type", "enum")}
        return rest | {"anyOf": [{"type": kind, "enum": values}, {"type": "null"}]}
    return fields


class Anthropic:
    """Claude on the Anthropic API through the official SDK, paid from prepaid credits.

    Off for good, stored in its ledger so every process and a restart see it: credits gone (a 402,
    or a 400 that names a spend limit or the credit balance) and a rejected key or model (401, 403,
    404, logged as an error for the alert); from the day the credits expire (UTC) too. It also sits
    out while today's ledger budget is used up. Each call then fails at once without a request, and
    the answer chain skips it (`unusable`). A 429 hands that one call on: one asking for
    CLAUDE_RETRY_MAX_S or less is retried once first. Its calls get CLAUDE_MAX_TOKENS, and no
    prompt goes that could pass LONG_PROMPT tokens. It answers and routes (a JSON reply held to the
    router's schema); settings keep it out of judging and of the free models behind it.
    """

    def __init__(
        self,
        model: str,
        key: str,
        *,
        expires: date,
        ledger: ClaudeLedger,
        today: Callable[[], date] = lambda: datetime.now(UTC).date(),
        http_client: httpx2.AsyncClient | None = None,  # tests pass a mock transport
    ) -> None:
        if model not in CLAUDE_PRICES:
            raise ValueError(f"anthropic:{model} has no price in CLAUDE_PRICES.")
        self.name = f"anthropic:{model}"
        self._model = model
        self._expires = expires
        self._ledger = ledger
        self._today = today
        self._client = anthropic.AsyncAnthropic(
            api_key=key,
            timeout=anthropic.Timeout(30.0, connect=5.0),
            max_retries=0,  # only a short 429 is retried (_send); the answer chain covers the rest
            http_client=http_client,
            open_telemetry=False,  # traced_complete/_stream span every provider the same way
        )
        # Why Claude is off here; the switch-off is stored in Redis and survives restarts.
        self._gone: str | None = None

    def off(self) -> str | None:
        """Why Claude is skipped for the rest of the credit period, or None while it may answer."""
        if self._gone is None and self._today() >= self._expires:
            self._stop(f"its credits expired on {self._expires.isoformat()}")
        return self._gone

    def _stop(self, reason: str) -> AiUnavailableError:
        """Turn Claude off in this process for the rest of the credit period, with one log line."""
        self._gone = reason
        log.warning(
            "claude is off for the rest of the credit period",
            model=self.name,
            reason=reason,
            credits_expire=self._expires.isoformat(),
        )
        return self._unavailable()

    async def _switch_off(self, kind: str, reason: str) -> AiUnavailableError:
        """Off for good in every process: credits gone, or a key or model the API rejects."""
        if kind == "key_or_model":  # a setup error: ClaudeKeyOrModelRejected alerts on it
            log.error("claude rejected the key or model", model=self.name, reason=reason)
        error = self._stop(reason)
        try:
            await self._ledger.turn_off(kind, reason)
        except RedisError as exc:  # this process still knows; another learns from its own call
            log.warning("claude switch-off not stored", error=repr(exc))
        return error

    async def unusable(self) -> FilingLensError | None:
        """Why a call cannot go to Claude now, or None: off for good, today's budget used up, or a
        ledger that cannot say (fail closed: the free chain answers)."""
        if self.off():
            return self._unavailable()
        try:
            if (reason := await self._ledger.off()) is not None:
                self._gone = reason
                return self._unavailable()
            if await self._ledger.tokens_today() >= self._ledger.daily_tokens:
                daily = self._ledger.daily_tokens
                return RateLimitedError(
                    f"{self.name}'s budget of {daily:,} tokens a day is used up.",
                    retry_after_s=seconds_to_midnight(datetime.now(UTC)),
                )
        except RedisError as exc:
            return UpstreamError(f"{self.name}'s budget cannot be checked ({type(exc).__name__}).")
        return None

    async def _ready(self, system: str, user: str) -> None:
        """Raise before any request when Claude cannot take this prompt."""
        if (error := await self.unusable()) is not None:
            raise error
        size = len(system.encode()) + len(user.encode())  # a token holds at least one byte
        if size > LONG_PROMPT:  # longer prompts cost 5x
            raise UpstreamError(
                f"{self.name} skipped a {size:,}-byte prompt: it could pass {LONG_PROMPT:,} tokens."
            )

    async def _spend(self, tokens: int) -> None:
        try:
            await self._ledger.record(tokens)
        except RedisError as exc:  # the call already cost the tokens; keep its answer
            log.warning("claude tokens not counted", error=repr(exc))

    def _unavailable(self) -> AiUnavailableError:
        return AiUnavailableError(f"{self.name} is off for the credit period: {self._gone}.")

    async def _send[T](self, request: Callable[[], Awaitable[T]], *, retry: bool = True) -> T:
        """`request` while Claude is on, once more after a short 429; credits gone stop Claude."""
        if self.off():
            raise self._unavailable()
        try:
            return await request()
        except anthropic.RateLimitError as exc:  # this call only: Claude stays on
            wait = _retry_after(exc.response.headers)
            if wait is None or not retry or wait > CLAUDE_RETRY_MAX_S:
                seconds = math.ceil(wait) if wait is not None and math.isfinite(wait) else None
                message = f"{self.name} is rate limited (429)."
                raise RateLimitedError(message, retry_after_s=seconds) from exc
        except anthropic.APIStatusError as exc:
            reason = f"{exc.status_code} {exc.type or 'error'}: {exc.message}"
            credits = exc.status_code == 400 and CREDITS_GONE.search(exc.message)
            if exc.status_code == 402 or credits:
                raise await self._switch_off("credits", reason) from exc
            if exc.status_code in (401, 403, 404):
                raise await self._switch_off("key_or_model", reason) from exc
            raise failure(self.name, exc.status_code) from exc
        except anthropic.APIConnectionError as exc:  # timeouts included
            raise UpstreamError(f"{self.name} did not answer ({type(exc).__name__}).") from exc
        await asyncio.sleep(wait)
        return await self._send(request, retry=False)

    @traced_complete
    async def complete(
        self, system: str, user: str, *, max_tokens: int, schema: Mapping[str, Any] | None = None
    ) -> Completion:
        await self._ready(system, user)
        config: OutputConfigParam = {"effort": CLAUDE_EFFORT}
        if schema is not None:  # a routing reply: JSON held to the router's schema
            config["format"] = {"type": "json_schema", "schema": claude_schema(schema)}
        started = time.perf_counter()
        message = await self._send(
            lambda: self._client.messages.create(
                model=self._model,
                max_tokens=CLAUDE_MAX_TOKENS,  # its own cap, sized from its answers
                system=system,
                messages=[{"role": "user", "content": user}],
                thinking={"type": CLAUDE_THINKING},
                output_config=config,
            )
        )
        if message.stop_reason == "refusal":
            raise UpstreamError(f"{self.name} declined to answer (refusal).")
        text = "".join(block.text for block in message.content if block.type == "text")
        usage = message.usage
        await self._spend(usage.input_tokens + usage.output_tokens)
        return Completion(
            self.name, text, usage.input_tokens, usage.output_tokens, time.perf_counter() - started
        )

    @traced_stream
    async def stream(
        self, system: str, user: str, *, max_tokens: int
    ) -> AsyncIterator[str | Completion]:
        await self._ready(system, user)
        started, first, parts = time.perf_counter(), None, list[str]()
        events = await self._send(
            lambda: self._client.messages.create(
                model=self._model,
                max_tokens=CLAUDE_MAX_TOKENS,  # its own cap, sized from its answers
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
        await self._spend(input_tokens + output_tokens)
        if stop_reason == "refusal":
            raise UpstreamError(f"{self.name} declined to answer (refusal).")
        yield Completion(
            self.name, "".join(parts), input_tokens, output_tokens,
            time.perf_counter() - started, first,
        )  # fmt: skip


def provider(
    role: str, settings: ApiSettings, client: httpx.AsyncClient, ledger: ClaudeLedger | None = None
) -> Provider:
    """The provider for a role such as LLM_PRIMARY (provider:model), with its key from settings.
    Claude keeps its own HTTP client (the anthropic SDK runs on httpx2) and needs its ledger."""
    name, _, model = role.partition(":")
    field = PROVIDER_KEYS[name]
    secret = getattr(settings, field) if field else None
    key = secret.get_secret_value() if secret is not None else None
    if name == "gemini":
        return Gemini(model, key or "", client)
    if name == "anthropic":
        if ledger is None:
            raise ValueError("Claude needs its ledger: its daily tokens and switch-off.")
        return Anthropic(model, key or "", expires=settings.anthropic_credits_expire, ledger=ledger)
    base_url = str(settings.ollama_url) if name == "ollama" else BASE_URLS[name]
    return OpenAICompatible(name, base_url, model, key, client)
