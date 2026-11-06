"""Each model reply records why it stopped, as a metric the operators can read."""

from collections.abc import Callable
from typing import Any

import httpx

from filinglens_llm.providers import BASE_URLS, Completion, OpenAICompatible

type Changes = Callable[[str], dict[str, float]]


def model(reply: httpx.Response) -> OpenAICompatible:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: reply))
    return OpenAICompatible("groq", BASE_URLS["groq"], "m", "k", client)


async def test_a_reply_says_why_it_stopped(metric_changes: Changes) -> None:
    body: dict[str, Any] = {
        "choices": [{"message": {"content": "Revenue"}, "finish_reason": "length"}],
        "usage": {},
    }
    completion = await model(httpx.Response(200, json=body)).complete("s", "u", max_tokens=5)
    assert completion.finish_reason == "length"
    assert metric_changes("filinglens.llm.finishes") == {"model=m,provider=groq,reason=length": 1}


async def test_a_stream_says_why_it_stopped(metric_changes: Changes) -> None:
    lines = (
        'data: {"choices":[{"delta":{"content":"Revenue"}}]}\n\n'
        'data: {"choices":[{"delta":{},"finish_reason":"content_filter"}]}\n\n'
        "data: [DONE]\n\n"
    )
    reply = httpx.Response(200, text=lines, headers={"content-type": "text/event-stream"})
    items = [item async for item in model(reply).stream("s", "u", max_tokens=5)]
    completion = items[-1]
    assert isinstance(completion, Completion) and completion.finish_reason == "content_filter"
    assert metric_changes("filinglens.llm.finishes") == {
        "model=m,provider=groq,reason=content_filter": 1
    }
