"""The about category: questions about FilingLens itself, and the near-misses that must not be taken
for them, beside the frozen golden set, which stays as it was. Its own file, no floors, never in CI.

    make eval-about ARGS="--claude-first"

Only the router's model runs: a question for the filings stops at a stand-in for the answer model,
and FilingLens's own answers come from a template and the database, so a live run costs one router
call per question (a second on a retry or a second look). Replies are cached as the harness caches
them, and --tag=NAME asks live again. Exit 0 when every question landed where it should and said
what it should, 1 when one did not, and the harness's codes for a stopped run.
"""

import asyncio
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from evals import harness
from evals.calls import Call, Stop
from evals.golden import read_jsonl
from filinglens_api.answering import Models
from filinglens_core.errors import UpstreamError
from filinglens_db import make_engine
from filinglens_llm.providers import Completion, Provider
from filinglens_telemetry import configure_logging

QUESTIONS = Path(__file__).parent / "golden" / "about.jsonl"
REACHED = "a question for the filings reached the answer model"
STOPPED = f"UpstreamError: {REACHED}"  # as the suite records the error


class NoAnswerModel:
    """In the answer model's place: a question for the filings stops here, and costs nothing."""

    name = "none:no-answer-model"

    async def complete(
        self, system: str, user: str, *, max_tokens: int, schema: Any = None
    ) -> Completion:
        raise UpstreamError(REACHED)

    def stream(self, system: str, user: str, *, max_tokens: int) -> Any:
        raise UpstreamError(REACHED)


class AboutSuite(harness.AnswerSuite):
    """The answer suite's calls and cache, with no answer model and a run file of its own."""

    def __init__(self, *setup: Any) -> None:
        super().__init__(*setup)
        self.run_file = self.run_file.with_name(f"about-{self.run_file.name}")

    def models(self, qid: str, calls: list[Call]) -> Models:
        stand_in = cast(Provider, NoAnswerModel())
        return replace(super().models(qid, calls), primary=stand_in, fallback=stand_in)


def landed(record: Mapping[str, Any]) -> str:
    """Where a question ended: FilingLens's own data, a refusal, the filings, or an error."""
    if record["outcome"] == "answered":
        return "own_data"
    if record["outcome"] == "refused":  # after a search, it reached the filings' relevance gate
        return "filings" if record.get("top_score") is not None else "refuse"
    return "filings" if record["error"] == STOPPED else "error"


def problems(question: Mapping[str, Any], record: Mapping[str, Any]) -> list[str]:
    where = landed(record)
    if where != question["expect"]:
        return [f"landed on {where}, not {question['expect']}"]
    said = record["answer"]
    return [f"says no {words}" for words in question.get("says", []) if words not in said]


def summary(
    questions: Sequence[Mapping[str, Any]], records: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """How many landed right, how many the router's own reply routed right (settle may still put a
    wrong one right), and how many of the questions with figures said them."""
    pairs = list(zip(questions, records, strict=True))
    said = [(q, r) for q, r in pairs if q.get("says")]
    return {
        "questions": len(pairs),
        "landed": sum(landed(r) == q["expect"] for q, r in pairs),
        "router_route": sum(r["route_ok"] is True for r in records),
        "says": [sum(not problems(q, r) for q, r in said), len(said)],
    }


def write_report(
    folder: Path,
    config: Mapping[str, Any],
    totals: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = folder / f"{stamp}-about.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    report = {"config": config, "summary": totals, "records": records}
    body = json.dumps(report, indent=1, ensure_ascii=False, default=str) + "\n"
    path.write_text(body, encoding="utf-8", newline="\n")
    return path


async def evaluate(args: Any) -> int:
    os.environ["AI_ENABLED"] = "true"  # a run calls the router on purpose
    os.environ.setdefault("HF_HUB_OFFLINE", "1")  # pinned local models load from HF_HOME
    settings = harness.answer_model(args, harness.eval_settings())
    configure_logging("eval", "WARNING")
    golden = harness.load_golden()
    questions = read_jsonl(QUESTIONS)
    engine = make_engine(settings)
    try:
        await harness.check_corpus(engine, golden)  # the figures in `says` are this corpus's
        index = await harness.index_version(engine, settings.retrieval_embedding_column)
        suite = AboutSuite(args, settings, engine, golden, index)
        try:
            records = await suite.run(questions)
        finally:
            await suite.close()
        suite.run_file.unlink(missing_ok=True)  # complete: a rerun starts over, from the cache
    finally:
        await engine.dispose()
    totals = summary(questions, records)
    config = {"router": settings.llm_router, "tag": args.tag or None}
    path = write_report(harness.REPORTS / "runs", config, totals, records)
    print(f"Report: {path}")
    print(
        f"{totals['landed']} of {totals['questions']} landed where they should; the router's own"
        f" route matched on {totals['router_route']}; {totals['says'][0]} of {totals['says'][1]}"
        " said their figures."
    )
    wrong = [
        (question["id"], problem)
        for question, record in zip(questions, records, strict=True)
        for problem in problems(question, record)
    ]
    for qid, problem in wrong:
        print(f"{qid}: {problem}")
    return 1 if wrong else 0


def main() -> None:
    args = harness.parse_args([*sys.argv[1:], "--no-judge"])
    try:
        code = asyncio.run(evaluate(args))
    except Stop as stop:
        print(stop, file=sys.stderr)
        code = stop.code
    sys.exit(code)


if __name__ == "__main__":
    main()
