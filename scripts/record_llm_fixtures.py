"""Record model replies for the answering tests, from live providers over the dev corpus.

Runs each question through the answer pipeline (filinglens_api.answering) with the real router and
primary models and the dev Postgres, and writes services/api/tests/fixtures/answers/<name>.json:
the question, every provider response body in call order (status, content type, body; never the
request headers, which hold the keys), the evidence the pipeline read, and its answer. Tests replay
the bodies with respx and the evidence through a fake, so validation runs on real model output.

    uv run --env-file .env python scripts/record_llm_fixtures.py [name ...]

Costs one router call and one or two primary calls per question.
"""

import asyncio
import dataclasses
import json
import os
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from redis.asyncio import Redis

from filinglens_api.answering import Answerer, Models, PostgresEvidence
from filinglens_api.schemas import AnswerCompleted, AnswerRequest
from filinglens_core.settings import ApiSettings, load_settings
from filinglens_db import make_engine
from filinglens_llm.providers import TIMEOUT, provider
from filinglens_retrieval import Ranking, Scope
from filinglens_retrieval.facts import Fact
from filinglens_telemetry import configure_logging

OUT = Path(__file__).parents[1] / "services" / "api" / "tests" / "fixtures" / "answers"
QUESTIONS = {
    "numeric": "What was Apple's total revenue in fiscal 2025?",
    "textual": "What supply chain risks does Apple describe in its latest annual report?",
    "out_of_scope": "Will Nvidia's stock price go up next year?",
    "time_trap": "What was Apple's revenue in fiscal 2027?",
}


class RecordingEvidence(PostgresEvidence):
    """PostgresEvidence that keeps every answer it gives, for the fixture."""

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.calls: list[dict[str, Any]] = []

    def _keep(self, method: str, args: dict[str, Any], result: Any) -> Any:
        self.calls.append({"method": method, "args": args, "result": _plain(result)})
        return result

    async def companies(self, tickers: Sequence[str]) -> dict[str, int]:
        found = await super().companies(tickers)
        return self._keep("companies", {"tickers": list(tickers)}, found)

    async def names(self, ciks: Sequence[int]) -> dict[int, str]:
        return self._keep("names", {"ciks": list(ciks)}, await super().names(ciks))

    async def latest_fiscal_year(self, cik: int) -> int | None:
        return self._keep("latest_fiscal_year", {"cik": cik}, await super().latest_fiscal_year(cik))

    async def fact(
        self, cik: int, concepts: Sequence[str], unit: str, fiscal_year: int | None, period: str
    ) -> Fact | None:
        found = await super().fact(cik, concepts, unit, fiscal_year, period)
        args = {"cik": cik, "unit": unit, "fiscal_year": fiscal_year, "period": period}
        return self._keep("fact", args, found)

    async def search(self, question: str, scope: Scope) -> Ranking:
        ranking = await super().search(question, scope)
        return self._keep("search", {"scope": _plain(scope)}, ranking)


def _plain(value: Any) -> Any:
    """JSON-ready: dataclasses as dicts, Decimals and dates as strings, int keys as strings."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _plain(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return str(value)


async def record(name: str, question: str, settings: ApiSettings) -> None:
    exchanges: list[dict[str, Any]] = []

    async def keep(response: httpx.Response) -> None:
        await response.aread()  # the caller reads the buffered body afterwards
        exchanges.append(
            {
                "host": response.request.url.host,
                "path": response.request.url.path,
                "status": response.status_code,
                "content_type": response.headers.get("content-type"),
                "body": response.text,
            }
        )

    engine = make_engine(settings)
    redis = Redis.from_url(str(settings.redis_url.get_secret_value()))
    async with httpx.AsyncClient(timeout=TIMEOUT, event_hooks={"response": [keep]}) as http:
        models = Models(
            router=provider(settings.llm_router, settings, http),
            primary=provider(settings.llm_primary, settings, http),
            fallback=provider(settings.llm_fallback, settings, http),
        )
        evidence = RecordingEvidence(engine, settings)
        answerer = Answerer(evidence, models, redis, max_inflight=1, allow_fallback=False)
        stats: dict[str, Any] = {}
        answer = None
        async for event in answerer.events(AnswerRequest(question=question), stats):
            if isinstance(event, AnswerCompleted):
                answer = event.answer
    await redis.aclose()
    await engine.dispose()
    fixture = {
        "question": question,
        "recorded_on": date.today().isoformat(),
        "models": {"router": settings.llm_router, "primary": settings.llm_primary},
        "exchanges": exchanges,
        "evidence": evidence.calls,
        "answer": answer.model_dump(mode="json") if answer else None,
        "stats": _plain(stats),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.json"
    path.write_text(json.dumps(fixture, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    refused = answer.refused if answer else None
    print(f"{name}: {len(exchanges)} provider calls, refused={refused} -> {path}")


def main() -> None:
    os.environ["AI_ENABLED"] = "true"  # a live run: it calls the models on purpose
    settings = load_settings(ApiSettings)
    configure_logging("record", settings.log_level)
    names = sys.argv[1:] or list(QUESTIONS)
    for name in names:
        asyncio.run(record(name, QUESTIONS[name], settings))


if __name__ == "__main__":
    main()
