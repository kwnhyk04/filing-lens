"""Live smoke run: three questions through the answer pipeline, as POST /v1/answers/stream runs it.

A numeric question (answered from an XBRL fact), a textual one (cited filing text) and one with no
answer yet (a fiscal year without a 10-K). Prints the route, the answer, its fact or its citations
with quotes, or the refusal, then tokens, latency per stage and time to first token. The local
models load before the first question, as in a running API.

    uv run --env-file .env python scripts/smoke_answers.py
"""

import asyncio
import json
import os
from typing import Any

import httpx
from redis.asyncio import Redis

from filinglens_api.answering import Answerer, Models, PostgresEvidence
from filinglens_api.schemas import AnswerCompleted, AnswerDelta, AnswerRequest
from filinglens_core.settings import ApiSettings, load_settings
from filinglens_db import make_engine
from filinglens_llm.providers import TIMEOUT, provider
from filinglens_retrieval import Scope
from filinglens_telemetry import configure_logging

QUESTIONS = [
    "What was Apple's total revenue in fiscal 2025?",
    "What supply chain risks does Apple describe in its latest annual report?",
    "What was Apple's revenue in fiscal 2027?",
]


async def main() -> None:
    os.environ["AI_ENABLED"] = "true"  # a live run: it calls the models on purpose
    settings = load_settings(ApiSettings)
    configure_logging("smoke", "WARNING")
    engine = make_engine(settings)
    redis = Redis.from_url(str(settings.redis_url.get_secret_value()))
    async with httpx.AsyncClient(timeout=TIMEOUT) as http:
        models = Models(
            router=provider(settings.llm_router, settings, http),
            primary=provider(settings.llm_primary, settings, http),
            fallback=provider(settings.llm_fallback, settings, http),
        )
        evidence = PostgresEvidence(engine, settings)
        await evidence.search("warm up the local models", Scope())  # no model call
        answerer = Answerer(evidence, models, redis, max_inflight=1)
        for question in QUESTIONS:
            stats: dict[str, Any] = {}
            deltas, answer = 0, None
            async for event in answerer.events(AnswerRequest(question=question), stats):
                if isinstance(event, AnswerDelta):
                    deltas += 1
                elif isinstance(event, AnswerCompleted):
                    answer = event.answer.model_dump(mode="json")
            if answer is not None:  # stats fill in once the stream has ended
                show(question, answer, stats, deltas)
    await redis.aclose()
    await engine.dispose()


def show(question: str, answer: dict[str, Any], stats: dict[str, Any], deltas: int) -> None:
    routing = stats["routing"] or {}
    print(f"\nQ: {question}")
    print(
        f"route: {routing.get('route')}  metric: {routing.get('metric')}  "
        f"years: {routing.get('fiscal_years')}  tickers: {routing.get('tickers')}"
    )
    print(f"A: {answer['answer']}")
    for n, citation in enumerate(answer["citations"], start=1):
        kind = "fact" if citation["fact_id"] else "chunk"
        source = citation["fact_id"] or citation["chunk_id"][:12]
        print(f'  [{n}] {kind} {source}: "{citation["quote"]}"')
    print(
        f"refused: {answer['refused']}  degraded: {answer['degraded']}  "
        f"warnings: {answer['warnings']}  fallbacks: {stats['fallbacks']}"
    )
    print(
        f"tokens: {stats['input_tokens']} in / {stats['output_tokens']} out  "
        f"time to first token: {stats['first_token_ms']} ms  deltas: {deltas}"
    )
    print(f"stages (ms): {json.dumps(stats['timings_ms'])}")


if __name__ == "__main__":
    asyncio.run(main())
