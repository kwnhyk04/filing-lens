"""Eval harness: golden set v1 through retrieval and the answer pipeline, with 95% bootstrap
intervals, floors and reports (docs/todo.md, step 6b).

    make eval SUITE=retrieval|answer|all SPLIT=dev|test SUBSET=full|ci ARGS="..."
    uv run python -m evals.harness --compare A.json B.json   # paired differences, A minus B
    uv run python -m evals.harness --sweep A.json   # refusal threshold, from a gate-off run
    uv run python -m evals.harness --set-floors A.json   # floors from a saved report's values

ARGS: --tag=NAME calls the answer models live once, keyed under NAME, and leaves earlier replies
as earlier reports read them (the same NAME reuses that run's replies); --primary-tag=NAME does
that for the primary only, so router replies come from the cache (a repeated latency pass on the
same routes); --min-relevance=X sets the refusal gate (-100 turns it off); --thinking=default gives
Gemini its own thinking and 4,096 output tokens; --no-judge skips the judge.

A run checks the floors in evals/thresholds.json and never writes them. --set-floors applies the
floor rule (metrics.floor) to a saved report's measured values, latency included, and keeps only
tighter floors: a rerun from the cache could not, since cached replies carry no live latency.

Model replies are cached in .cache/evals/calls.jsonl (evals/calls.py), and an answer run keeps
its progress in .cache/evals/runs/, so a stopped run resumes where it stopped. Today is pinned to
the golden set's as_of date, and eval tokens count in Redis db 15, never against the dev API's
daily budget. Exit codes: 0 ok, 1 a floor broken, 2 a quota or a refused key stopped the run
(rerun later to resume), 3 the golden set or the corpus changed since the freeze (needs v2).
"""

import argparse
import asyncio
import hashlib
import itertools
import json
import math
import os
import subprocess
import sys
import time
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from redis.asyncio import Redis
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from evals import judge
from evals.calls import Cache, Call, Recorded, Stop, digest, patiently
from evals.golden import ROOT, VERSION, companies, final_labels, read_jsonl, read_manifest, sha256
from evals.metrics import (
    bootstrap,
    broken,
    floor,
    judged_at,
    mean,
    mrr_at,
    ndcg_at,
    percentile,
    pooled,
    recall_at,
    states_amount,
    tighter,
)
from filinglens_api.answering import RELEVANCE_MIN, Answerer, Models, PostgresEvidence
from filinglens_api.limits import ANSWER_TIMEOUT_S
from filinglens_api.schemas import Answer, AnswerCompleted, AnswerRequest
from filinglens_core.errors import AiUnavailableError, FilingLensError
from filinglens_core.settings import (
    EMBEDDING_MODELS,
    PROVIDER_KEYS,
    ApiSettings,
    EmbeddingColumn,
    ModelRole,
    load_settings,
)
from filinglens_db import make_engine
from filinglens_db.models import (
    Chunk,
    Company,
    EvalRun,
    Filing,
    FilingStatus,
    FinancialFact,
    Section,
)
from filinglens_llm import answer as drafting
from filinglens_llm import router
from filinglens_llm.local import REVISIONS
from filinglens_llm.providers import TIMEOUT, Gemini, Provider, provider
from filinglens_llm.validate import Quoted, citation_error, cited, split_sentences
from filinglens_retrieval import Ranking, Scope, search
from filinglens_retrieval.facts import latest_fiscal_year
from filinglens_telemetry import configure_logging

EVALS = Path(__file__).parent
REPO = EVALS.parent
CACHE = REPO / ".cache" / "evals"
CODE_PATHS = ("services", "packages", "evals", "scripts", "infra", "pyproject.toml", "uv.lock")
# Data and docs inside those paths; golden v1 has its own manifest hash in every report.
NOT_CODE = ("evals/reports", "evals/calibration", "evals/golden", "**/*.md")
REPORTS = EVALS / "reports"
THRESHOLDS = EVALS / "thresholds.json"
PROVIDERS = EVALS / "providers.json"
CALIBRATION = EVALS / "calibration" / VERSION / "result.json"
RETRIEVAL_TIMEOUT_S = 60.0  # never degraded: the measurement needs the reranker's own order
THINKING_MAX_TOKENS = 4096  # Gemini's own thinking spends output tokens (decision 3)
JUDGE_KAPPA_MIN = 0.7
EVAL_REDIS_DB = 15
# docs/context.md targets, with the kind metrics.floor reads.
TARGETS: dict[str, tuple[float, str]] = {
    "recall@10": (0.90, "accuracy"),
    "mrr@10": (0.70, "accuracy"),
    "retrieval_p95_ms": (250.0, "efficiency"),
    "numeric_exact_match": (0.92, "accuracy"),
    "citation_precision": (0.95, "accuracy"),
    "citation_coverage": (0.95, "accuracy"),
    "faithfulness": (0.92, "accuracy"),
    "correct_refusal": (0.90, "accuracy"),
    "false_refusal": (0.05, "rate"),
    "ttft_p50_ms": (1000.0, "efficiency"),
    "ttft_p95_ms": (2000.0, "efficiency"),
    "answer_p95_ms": (6000.0, "efficiency"),
    "input_tokens": (8000.0, "efficiency"),
    "output_tokens": (600.0, "efficiency"),
    "cost_usd": (0.015, "efficiency"),
    "cost_billed_usd": (0.015, "billed"),
}
JUDGED = ("citation_precision", "faithfulness")
STAGES = ("route", "facts", "retrieve", "generate", "regenerate")
LABELS = {
    "recall@10": "Retrieval recall@10",
    "mrr@10": "MRR@10",
    "ndcg@10": "nDCG@10",
    "judged@10": "Judged@10 (labeled share of the top 10)",
    "retrieval_p50_ms": "Retrieval latency p50",
    "retrieval_p95_ms": "Retrieval latency p95",
    "rerank_p50_ms": "Rerank p50",
    "rerank_p95_ms": "Rerank p95",
    "numeric_exact_match": "Numeric exact match (0.5%)",
    "comparison_match": "Comparison match (both values)",
    "citation_precision": "Citation precision (judge)",
    "citation_coverage": "Citation coverage (last reply before removal)",
    "faithfulness": "Faithfulness (judge)",
    "draft_citation_pass_rate": "Draft citation pass rate",
    "correct_refusal": "Correct refusal",
    "false_refusal": "False refusal",
    "router_accuracy": "Router accuracy (route, tickers, years, metric)",
    "route_accuracy": "Route accuracy",
    "ttft_p50_ms": "Time to first token p50",
    "ttft_p95_ms": "Time to first token p95",
    "answer_p50_ms": "Full answer p50",
    "answer_p95_ms": "Full answer p95",
    "input_tokens": "Input tokens per query",
    "output_tokens": "Output tokens per query",
    "cost_usd": "Cost per query, paid-equivalent",
    "cost_billed_usd": "Cost per query, as billed",
    "truncated": "Replies cut at max tokens",
    "errors": "Errors",
}
# Rough tokens per uncached call, for the quota estimate printed before an answer run.
ESTIMATE: dict[str, Any] = {
    "router": 800,
    "primary": {"numeric": 1500, "comparison": 2500, "textual": 5500, "unanswerable": 5000},
    "judge": {"numeric": 1200, "comparison": 2000, "textual": 3000, "unanswerable": 3000},
}


class EvalSettings(ApiSettings):
    """The API's settings plus LLM_JUDGE, which only evals read."""

    llm_judge: ModelRole = "groq:openai/gpt-oss-120b"


@dataclass(frozen=True)
class Golden:
    manifest: dict[str, Any]
    questions: list[dict[str, Any]]
    pools: list[dict[str, Any]]
    labels: dict[tuple[str, str], bool]  # the final label per (question, chunk)

    def gold(self, qid: str) -> set[str]:
        return {chunk for (q, chunk), gold in self.labels.items() if q == qid and gold}

    def judged(self, qid: str) -> set[str]:
        return {chunk for q, chunk in self.labels if q == qid}


@dataclass(frozen=True)
class Src:
    """An answer's source as the validator reads it, with a heading for the judge."""

    chunk_id: str | None
    fact_id: str | None
    heading: str
    text: str
    value: Decimal | None


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def load_golden() -> Golden:
    """The frozen set; Stop(3) when it is not frozen or a file changed since the freeze."""
    manifest = read_manifest()
    if manifest["status"] != "frozen":
        raise Stop(3, f"Golden set {VERSION} is not frozen: run python -m evals.golden freeze.")
    changed = [name for name, sha in manifest["files"].items() if sha256(ROOT / name) != sha]
    if changed:
        raise Stop(3, f"Golden set {VERSION} changed since the freeze ({', '.join(changed)}).")
    questions, pools = read_jsonl(ROOT / "questions.jsonl"), read_jsonl(ROOT / "pools.jsonl")
    return Golden(manifest, questions, pools, final_labels()[0])


async def check_corpus(engine: AsyncEngine, golden: Golden) -> None:
    """Stop(3) when the corpus moved under the set: a new 10-K, or a gold chunk or fact that
    changed or vanished (a re-seed, relabeled items)."""
    years = golden.manifest["corpus"]["latest_fiscal_years"]
    gold = {
        candidate["chunk_id"]: candidate["sha256"]
        for pool in golden.pools
        for candidate in pool["candidates"]
        if golden.labels.get((pool["id"], candidate["chunk_id"]))
    }
    # Each question's own copy: a fact shared by two questions is checked in both.
    facts = [
        (q["id"], int(f["id"]), Decimal(f["value"]))
        for q in golden.questions
        for f in q.get("facts", [])
    ]
    problems: list[str] = []
    async with engine.connect() as connection:
        for ticker, cik in companies().items():
            year = await latest_fiscal_year(connection, cik)
            if year != years[ticker]:
                problems.append(f"{ticker}'s latest fiscal year is {year}, not {years[ticker]}")
        query = select(Chunk.id, Chunk.text).where(Chunk.id.in_(list(gold)))
        texts = {
            row.id: hashlib.sha256(row.text.encode()).hexdigest()
            for row in await connection.execute(query)
        }
        problems += [
            f"gold chunk {c[:12]} changed" for c, sha in gold.items() if texts.get(c) != sha
        ]
        query = select(FinancialFact.id, FinancialFact.value).where(
            FinancialFact.id.in_({fact_id for _, fact_id, _ in facts})
        )
        values = {row.id: row.value for row in await connection.execute(query)}
        problems += [
            f"{qid}: gold fact {fact_id} changed"
            for qid, fact_id, value in facts
            if values.get(fact_id) != value
        ]
    if problems:
        shown = "\n  ".join(problems[:20])
        raise Stop(
            3, f"The corpus changed since golden {VERSION} froze, so it needs v2:\n  {shown}"
        )


async def index_version(engine: AsyncEngine, column: EmbeddingColumn) -> dict[str, Any]:
    """The embedding column and model, and a hash of the indexed chunk ids."""
    query = (
        select(Chunk.id)
        .join(Section, Section.id == Chunk.section_id)
        .join(Filing, Filing.id == Section.filing_id)
        .where(Filing.status == FilingStatus.INDEXED)
        .order_by(Chunk.id)
    )
    async with engine.connect() as connection:
        ids = [row.id for row in await connection.execute(query)]
    model = EMBEDDING_MODELS[column]
    return {
        "column": column,
        "model": f"{model}@{REVISIONS[model]}",
        "chunks": len(ids),
        "sha256": hashlib.sha256("\n".join(ids).encode()).hexdigest(),
    }


def stat(values: Sequence[Any], statistic: Callable[[Sequence[Any]], float]) -> dict[str, Any]:
    """A metric with its 95% bootstrap interval over questions; n 0 when nothing measured it."""
    if not values:
        return {"value": None, "low": None, "high": None, "n": 0}
    low, high = bootstrap(values, statistic)
    return {"value": statistic(values), "low": low, "high": high, "n": len(values)}


def count(value: int, n: int) -> dict[str, Any]:
    return {"value": value, "low": None, "high": None, "n": n}


def p50(values: Sequence[float]) -> float:
    return percentile(values, 50)


def p95(values: Sequence[float]) -> float:
    return percentile(values, 95)


async def retrieval_suite(
    engine: AsyncEngine, settings: EvalSettings, golden: Golden, questions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Each question as a query in its company scope, timed; textual ones against their gold."""

    async def ranked(q: str, scope: Scope) -> Ranking:
        ranking = await search(
            engine, q, embedding=settings.retrieval_embedding_column, scope=scope,
            rerank_model=settings.rerank_model, candidates=settings.rerank_candidates,
            max_tokens=settings.rerank_max_tokens, timeout_s=RETRIEVAL_TIMEOUT_S,
        )  # fmt: skip
        if ranking.degraded:
            raise SystemExit(f"Search degraded on {q!r}, even with a {RETRIEVAL_TIMEOUT_S} s cap.")
        return ranking

    await ranked("warm up the local models", Scope())  # loads them outside the clock
    records: list[dict[str, Any]] = []
    for question in questions:
        textual = question["category"] == "textual"
        years = (question["fiscal_years"] or None) if textual else None
        started = time.perf_counter()
        ranking = await ranked(question["question"], Scope(question.get("ciks") or None, years))
        top = [hit.chunk_id for hit in ranking.hits[:10]]
        record: dict[str, Any] = {
            "id": question["id"],
            "category": question["category"],
            "total_ms": round((time.perf_counter() - started) * 1000, 1),
            "timings_ms": ranking.timings_ms,
            "top10": top,
        }
        if textual:
            gold, judged = golden.gold(question["id"]), golden.judged(question["id"])
            record |= {
                "gold": len(gold),
                "recall": recall_at(top, gold),
                "mrr": mrr_at(top, gold),
                "ndcg": ndcg_at(top, gold),
                "judged": judged_at(top, judged),
            }
        records.append(record)
    return records


def retrieval_metrics(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    textual = [r for r in records if "recall" in r]
    metrics = {
        name: stat([r[field] for r in textual], mean)
        for name, field in (
            ("recall@10", "recall"),
            ("mrr@10", "mrr"),
            ("ndcg@10", "ndcg"),
            ("judged@10", "judged"),
        )
    }
    totals = [r["total_ms"] for r in records]
    reranks = [r["timings_ms"]["rerank_ms"] for r in records if "rerank_ms" in r["timings_ms"]]
    return metrics | {
        "retrieval_p50_ms": stat(totals, p50),
        "retrieval_p95_ms": stat(totals, p95),
        "rerank_p50_ms": stat(reranks, p50),
        "rerank_p95_ms": stat(reranks, p95),
    }


def eval_redis_url(settings: ApiSettings) -> str:
    """REDIS_URL with database 15: eval tokens never count against the dev API's budget."""
    parts = urlsplit(str(settings.redis_url.get_secret_value()))
    return urlunsplit(parts._replace(path=f"/{EVAL_REDIS_DB}"))


def code_version() -> dict[str, Any]:
    """The code a run measured: the commit, whether the source files differ from it, and a
    sha256 over them as they stand (tracked and untracked, .gitignore applied, data and docs
    left out), so a run on uncommitted code is pinned too. A calibration import or a doc edit
    between commit and run changes neither."""

    def git(*args: str) -> str:
        done = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", *args],  # noqa: S607
            cwd=REPO, capture_output=True, text=True, check=True, timeout=30,
        )  # fmt: skip
        return done.stdout

    paths = (*CODE_PATHS, *(f":(exclude,glob){path}" for path in NOT_CODE))
    listed = git("ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", *paths)
    source = hashlib.sha256()
    for name in sorted(filter(None, listed.split("\0"))):
        path = REPO / name
        if path.is_file():  # a tracked file deleted in the tree is listed but gone
            text = path.read_bytes().replace(b"\r\n", b"\n")  # a checkout may rewrite line ends
            source.update(name.encode() + b"\0" + hashlib.sha256(text).digest())
    return {
        "commit": git("rev-parse", "HEAD").strip(),
        "dirty": bool(git("status", "--porcelain", "--", *paths).strip()),
        "source_sha256": source.hexdigest(),
    }


def prompt_hashes(as_of: date, tracked: Mapping[str, str]) -> dict[str, str]:
    """sha256 of each system prompt and response schema the answer suite sends."""

    def text(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    return {
        "router_system": text(router.system_prompt(as_of, tracked)),
        "router_schema": digest(router.schema(tracked)),
        "answer_system": text(drafting.SYSTEM),
        "judge_system": text(judge.SYSTEM),
        "judge_schema": digest(judge.SCHEMA),
    }


def answer_path(settings: ApiSettings, index: Mapping[str, Any], tag: str) -> dict[str, Any]:
    """What every answer call's cache key holds besides its prompts. A tag joins only when set,
    so untagged runs keep the keys of every earlier run, and a tagged one calls live once."""
    embedder = EMBEDDING_MODELS[settings.retrieval_embedding_column]
    path = {
        "router": settings.llm_router,
        "primary": settings.llm_primary,
        "embedder": f"{embedder}@{REVISIONS[embedder]}",
        "reranker": f"{settings.rerank_model}@{REVISIONS[settings.rerank_model]}",
        "rerank": [settings.rerank_candidates, settings.rerank_max_tokens],
        "index": index["sha256"],
    }
    return path | {"tag": tag} if tag else path


def primary_provider(settings: EvalSettings, http: httpx.AsyncClient, thinking: str) -> Provider:
    """LLM_PRIMARY; Gemini keeps its own thinking when `thinking` is "default" (decision 3)."""
    name, _, model = settings.llm_primary.partition(":")
    if name == "gemini" and thinking == "default":
        key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else ""
        return Gemini(model, key, http, minimal_thinking=False)
    return provider(settings.llm_primary, settings, http)


def routed(
    gold: Mapping[str, Any], got: Mapping[str, Any] | None, tracked: Collection[str]
) -> tuple[bool | None, bool]:
    """Whether the route matches (None when the gold leaves it open), and whether the route,
    tickers, fiscal years and metric all match; a field the gold leaves None is not scored. A gold
    ticker FilingLens does not track is right as an other company, since tickers come from the
    tracked ones."""
    route_ok = None if gold["route"] is None else got is not None and got["route"] == gold["route"]
    if got is None:
        return route_ok, False

    def same(name: str) -> bool:
        want = gold[name]
        if want is None:
            return True
        if name == "tickers":
            if any(t not in tracked for t in want) and not got.get("other_companies"):
                return False
            want = [t for t in want if t in tracked]
        return sorted(got[name]) == sorted(want) if isinstance(want, list) else got[name] == want

    fields = ("tickers", "fiscal_years", "metric")
    return route_ok, route_ok is not False and all(map(same, fields))


def refusal_cause(record: Mapping[str, Any]) -> str:
    """Which path refused: the plan (untracked company, out of scope, time trap), validation,
    the model, or the relevance gate (no answer call, and a best search score)."""
    text = record["answer"] or ""
    for cause, says in (
        ("router: untracked company", "FilingLens has no filings for"),
        ("router: out of scope", "SEC filings cannot answer"),
        ("time trap", "has filed no 10-K for fiscal"),
        ("validation: no sentence held up", "No sentence of the answer held up"),
    ):
        if says in text:
            return cause
    if any(call["role"] == "primary" for call in record["calls"]):
        return "model: insufficient evidence"
    return "relevance gate" if record["top_score"] is not None else "no search hits"


def false_refusals(records: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    """Answerable questions refused, by cause: question ids."""
    found: dict[str, list[str]] = {}
    for record in records:
        if record["expect"] == "answer" and record["outcome"] == "refused":
            found.setdefault(refusal_cause(record), []).append(record["id"])
    return found


def scores(
    question: Mapping[str, Any],
    answer: Answer | None,
    routing: Mapping[str, Any] | None,
    calls: Sequence[Call],
    sources: Mapping[str, Src],
    tracked: Collection[str],
) -> dict[str, Any]:
    """One question's results: router match, exact match, and the citation checks of its replies
    (first-draft quotes, and coverage of the last reply before sentence removal)."""
    route_ok, router_ok = routed(question["routing"], routing, tracked)
    out: dict[str, Any] = {"route_ok": route_ok, "router_ok": router_ok}
    said = answer.answer if answer is not None and not answer.refused else ""
    if question["category"] == "numeric":
        out["exact"] = bool(said) and states_amount(said, Decimal(question["facts"][0]["value"]))
    if question["category"] == "comparison":
        facts = question["facts"]
        out["both"] = bool(said) and all(states_amount(said, Decimal(f["value"])) for f in facts)
    replies = [call for call in calls if call.role == "primary"]
    if not replies:
        return out
    chunks = {s.chunk_id: s.text for s in sources.values() if s.chunk_id is not None}

    def passes(alias: str, quote: str) -> bool:
        source = sources.get(alias)
        if source is None or source.chunk_id is None:
            return False
        return citation_error(Quoted(source.chunk_id, None, quote), chunks, ()) is None

    draft = drafting.read_reply(replies[0].text)
    quotes = [(alias, q) for alias, given in draft.quotes.items() if alias[0] == "C" for q in given]
    out["draft_quotes"] = [sum(passes(alias, q) for alias, q in quotes), len(quotes)]
    last = drafting.read_reply(replies[-1].text)
    if not last.insufficient:
        held = [
            any(
                alias in sources
                and (
                    sources[alias].fact_id is not None
                    or any(passes(alias, q) for q in last.quotes.get(alias, []))
                )
                for alias in cited(sentence)
            )
            for sentence in split_sentences(last.text)
        ]
        out["coverage"] = [sum(held), len(held)]
    out["regenerated"] = len(replies) > 1
    out["truncated"] = any(call.truncated for call in replies)
    return out


async def load_sources(engine: AsyncEngine, aliases: Mapping[str, str]) -> dict[str, Src]:
    """An answer's sources by alias (C1, F1), read back from the database."""
    chunk_ids = [ref for alias, ref in aliases.items() if alias[0] == "C"]
    fact_ids = [int(ref) for alias, ref in aliases.items() if alias[0] == "F"]
    chunk_query = (
        select(Chunk.id, Chunk.text, Section.item, Filing.cik, Filing.form_type, Filing.fiscal_year)
        .join(Section, Section.id == Chunk.section_id)
        .join(Filing, Filing.id == Section.filing_id)
        .where(Chunk.id.in_(chunk_ids))
    )
    fact_query = select(FinancialFact).where(FinancialFact.id.in_(fact_ids))
    async with engine.connect() as connection:
        rows = await connection.execute(select(Company.cik, Company.name, Company.ticker))
        names = {row.cik: f"{row.name} ({row.ticker})" for row in rows}
        chunks = {row.id: row for row in await connection.execute(chunk_query)}
        facts = {str(row.id): row for row in await connection.execute(fact_query)}
    found: dict[str, Src] = {}
    for alias, ref in aliases.items():
        if alias[0] == "C" and (chunk := chunks.get(ref)) is not None:
            heading = (
                f"{names.get(chunk.cik, chunk.cik)} | {chunk.form_type} fiscal"
                f" {chunk.fiscal_year} | Item {chunk.item}"
            )
            found[alias] = Src(ref, None, heading, chunk.text, None)
        elif alias[0] == "F" and (fact := facts.get(ref)) is not None:
            period = (
                f"{fact.period_start} to {fact.period_end}"
                if fact.period_start
                else f"at {fact.period_end}"
            )
            heading = (
                f"{names.get(fact.cik, fact.cik)} | {fact.label} ({fact.taxonomy}:"
                f"{fact.concept}) | {period} | {fact.form} filed {fact.filed_on}"
            )
            found[alias] = Src(None, ref, heading, f"{fact.value:,f} {fact.unit}", fact.value)
    return found


class AnswerSuite:
    """Golden questions through the Answerer as POST /v1/answers runs them (no fallback, today
    pinned), each model call cached and recorded; the judge then scores each answer given."""

    def __init__(
        self,
        args: argparse.Namespace,
        settings: EvalSettings,
        engine: AsyncEngine,
        golden: Golden,
        index: Mapping[str, Any],
    ) -> None:
        self.args, self.settings, self.engine = args, settings, engine
        self.as_of = date.fromisoformat(golden.manifest["as_of"])
        self.cache = Cache(CACHE / "calls.jsonl")
        self.http = httpx.AsyncClient(timeout=TIMEOUT)
        self.redis = Redis.from_url(eval_redis_url(settings))
        self.evidence = PostgresEvidence(engine, settings)
        self.router = provider(settings.llm_router, settings, self.http)
        self.primary = primary_provider(settings, self.http, args.thinking)
        self.judge = provider(settings.llm_judge, settings, self.http)
        self.tracked: dict[str, str] = {}  # the router's companies, read when the run starts
        gemini = settings.llm_primary.startswith("gemini:")
        self.options = {"thinking": args.thinking} if gemini else {}
        if args.primary_tag:  # a new key for the primary only: router replies stay cached
            self.options |= {"tag": args.primary_tag}
        self.max_tokens = THINKING_MAX_TOKENS if gemini and args.thinking == "default" else None
        self.path = answer_path(settings, index, args.tag)
        run = {
            "files": golden.manifest["files"],
            "split": args.split,
            "subset": args.subset,
            "path": self.path,
            "options": self.options,
            "max_tokens": self.max_tokens,
            "rerank_timeout_ms": settings.rerank_timeout_ms,
            "min_relevance": args.min_relevance,
            "judge": settings.llm_judge if args.judge else None,
        }
        self.run_file = CACHE / "runs" / f"{digest(run)[:16]}.jsonl"

    def context(self, qid: str) -> dict[str, Any]:
        return {"question": qid, "path": self.path}

    def models(self, qid: str, calls: list[Call]) -> Models:
        route = Recorded(self.router, "router", self.cache, self.context(qid), calls)
        primary = Recorded(
            self.primary, "primary", self.cache, self.context(qid), calls,
            options=self.options, max_tokens=self.max_tokens,
        )  # fmt: skip
        return Models(router=route, primary=primary, fallback=primary)

    async def run(self, questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Each question once, resuming this configuration's run; errors are retried."""
        self.run_file.parent.mkdir(parents=True, exist_ok=True)
        records = {row["id"]: row for row in read_jsonl(self.run_file)}
        todo = [q for q in questions if records.get(q["id"], {}).get("outcome", "error") == "error"]
        if len(todo) < len(questions):
            print(f"Resuming {self.run_file.name}: {len(questions) - len(todo)} questions done.")
        self.tracked = await self.evidence.tracked()
        self.estimate(todo)
        if todo:
            await self.evidence.search("warm up the local models", Scope())  # no model call
        for n, question in enumerate(todo, 1):
            started = time.perf_counter()
            record = await self.one(question)
            append_jsonl(self.run_file, record)
            records[question["id"]] = record
            live = sum(not call["cached"] for call in record["calls"])
            error = f": {record['error']}" if record["error"] else ""
            print(
                f"[{n}/{len(todo)}] {question['id']} {record['outcome']}{error} ({live} live,"
                f" {len(record['calls']) - live} cached calls,"
                f" {time.perf_counter() - started:.1f} s)",
                flush=True,
            )
        return [records[q["id"]] for q in questions]

    async def one(self, question: dict[str, Any]) -> dict[str, Any]:
        qid = question["id"]

        async def attempt() -> tuple[Answer | None, dict[str, Any], list[Call], str | None]:
            calls: list[Call] = []
            answerer = Answerer(
                self.evidence, self.models(qid, calls), self.redis, max_inflight=1,
                allow_fallback=False, today=lambda: self.as_of,
                min_relevance=self.args.min_relevance,
            )  # fmt: skip
            stats: dict[str, Any] = {}
            answer, error = None, None
            try:
                async with asyncio.timeout(ANSWER_TIMEOUT_S):
                    request = AnswerRequest(question=question["question"])
                    async for event in answerer.events(request, stats):
                        if isinstance(event, AnswerCompleted):
                            answer = event.answer
            except TimeoutError:
                error = f"no answer within {ANSWER_TIMEOUT_S} s"
            except AiUnavailableError as exc:  # a refused key or no credits: no use going on
                raise Stop(2, f"{qid}: {exc}") from exc
            except FilingLensError as exc:
                error = f"{type(exc).__name__}: {exc}"
            return answer, stats, calls, error or (None if answer else "no answer")

        answer, stats, calls, error = await patiently(attempt)
        sources = await load_sources(self.engine, stats.get("sources") or {})
        given = None if error else answer
        record: dict[str, Any] = {
            "id": qid,
            "category": question["category"],
            "kind": question["kind"],
            "expect": question["expect"],
            "outcome": "error" if given is None else "refused" if given.refused else "answered",
            "error": error,
            "answer": given.answer if given else None,
            "citations": [c.model_dump(mode="json") for c in given.citations] if given else [],
            "warnings": given.warnings if given else [],
            "degraded": given.degraded if given else False,
            "routing": stats.get("routing"),
            "timings_ms": stats.get("timings_ms", {}),
            "first_token_ms": stats.get("first_token_ms"),
            "input_tokens": stats.get("input_tokens", 0),
            "output_tokens": stats.get("output_tokens", 0),
            "top_score": stats.get("top_score"),
            "early_search": stats.get("early_search"),
            "sources": stats.get("sources", {}),
            "calls": [call.saved() for call in calls],
            "live": all(not call.cached for call in calls),
        }
        record |= scores(question, given, stats.get("routing"), calls, sources, self.tracked)
        if given is not None and not given.refused and self.args.judge:
            record["judge"] = await self.judged(question, given, sources)
        return record

    async def judged(
        self, question: Mapping[str, Any], answer: Answer, sources: Mapping[str, Src]
    ) -> dict[str, Any]:
        """The judge's verdict on the final answer: supported sentences and supporting
        citations, each as (hits, total)."""
        by_id = {source.chunk_id or source.fact_id: source for source in sources.values()}
        cites: dict[int, judge.Cited] = {}
        for n, citation in enumerate(answer.citations, 1):
            source = by_id.get(citation.chunk_id or citation.fact_id)
            if source is None:
                return {"error": f"citation {n} is not among the answer's sources"}
            cites[n] = judge.Cited(source.heading, citation.quote, source.text)
        prompt = judge.user_prompt(question["question"], answer.answer, cites)
        calls: list[Call] = []
        model = Recorded(self.judge, "judge", self.cache, {"question": question["id"]}, calls)
        try:
            completion = await patiently(
                lambda: model.complete(
                    judge.SYSTEM, prompt, max_tokens=judge.MAX_TOKENS, schema=judge.SCHEMA
                )
            )
            verdict = judge.parse(completion.text, answer.answer)
        except AiUnavailableError as exc:
            raise Stop(2, f"judge: {exc}") from exc
        except (FilingLensError, judge.JudgeError) as exc:
            return {"error": str(exc), "calls": [call.saved() for call in calls]}
        return {
            "faithful": [verdict.supported.count("yes"), len(verdict.supported)],
            "precise": [sum(verdict.supports), len(verdict.supports)],
            "supported": verdict.supported,
            "supports": verdict.supports,
            "calls": [call.saved() for call in calls],
        }

    def estimate(self, todo: list[dict[str, Any]]) -> None:
        """Print the calls and tokens this run may spend per model, against its daily limits.
        Router replies are looked up in the cache; answers and verdicts count as uncached."""
        if not todo:
            return
        need: dict[str, list[int]] = {}

        def add(model: str, tokens: int) -> None:
            entry = need.setdefault(model, [0, 0])
            entry[0] += 1
            entry[1] += tokens

        system = router.system_prompt(self.as_of, self.tracked)
        schema = router.schema(self.tracked)
        for question in todo:
            probe = Recorded(self.router, "router", self.cache, self.context(question["id"]), [])
            key = probe.key(system, question["question"], router.MAX_TOKENS, schema)
            if self.cache.get(key) is None:
                add(self.router.name, ESTIMATE["router"])
            if question["expect"] == "answer" or question["kind"] == "absent":
                add(self.primary.name, ESTIMATE["primary"][question["category"]])
                if self.args.judge:
                    add(self.judge.name, ESTIMATE["judge"][question["category"]])
        limits = json.loads(PROVIDERS.read_text(encoding="utf-8"))
        print(f"At most, for {len(todo)} questions (cached replies cost nothing):")
        for model, (calls, tokens) in need.items():
            daily = (limits.get(model) or {}).get("limits", {})
            print(
                f"  {model}: {calls} calls, about {tokens:,} tokens; daily limits"
                f" {daily.get('requests_per_day', 'unlisted')} requests,"
                f" {daily.get('tokens_per_day', 'unlisted')} tokens"
            )

    async def close(self) -> None:
        await self.http.aclose()
        await self.redis.aclose()


def paid_cost(record: Mapping[str, Any], prices: Mapping[str, Any]) -> float | None:
    """The answer path's calls at listed paid prices; None when a model has no price."""
    total = 0.0
    for call in record["calls"]:
        price = (prices.get(call["model"]) or {}).get("price_per_million")
        if not price:
            return None
        total += call["input_tokens"] * price["input"] + call["output_tokens"] * price["output"]
    return total / 1e6


def answer_metrics(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    def share(rows: list[dict[str, Any]], hit: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
        return stat([float(bool(hit(r))) for r in rows], mean)

    def pairs(rows: list[dict[str, Any]], field: str) -> list[tuple[int, int]]:
        return [(r[field][0], r[field][1]) for r in rows if r.get(field) and r[field][1]]

    numeric = [r for r in records if r["category"] == "numeric"]
    comparison = [r for r in records if r["category"] == "comparison"]
    refuse = [r for r in records if r["expect"] == "refuse"]
    answerable = [r for r in records if r["expect"] == "answer"]
    verdicts = [r["judge"] for r in records if "faithful" in (r.get("judge") or {})]
    counted = [r for r in records if r["outcome"] != "error"]
    live = [r for r in counted if r["live"]]
    reached = [r for r in live if any(call["role"] == "primary" for call in r["calls"])]
    ttft = [r["first_token_ms"] for r in reached if r["first_token_ms"] is not None]
    totals = [r["timings_ms"]["total_ms"] for r in reached]
    prices = json.loads(PROVIDERS.read_text(encoding="utf-8"))
    costs = [paid_cost(r, prices) for r in counted]
    metrics = {
        "numeric_exact_match": share(numeric, lambda r: r.get("exact")),
        "comparison_match": share(comparison, lambda r: r.get("both")),
        "citation_precision": stat(pairs(verdicts, "precise"), pooled),
        "citation_coverage": stat(pairs(records, "coverage"), pooled),
        "faithfulness": stat(pairs(verdicts, "faithful"), pooled),
        "draft_citation_pass_rate": stat(pairs(records, "draft_quotes"), pooled),
        "correct_refusal": share(refuse, lambda r: r["outcome"] == "refused"),
        "false_refusal": share(answerable, lambda r: r["outcome"] == "refused"),
        "router_accuracy": share(records, lambda r: r["router_ok"]),
        "route_accuracy": share(
            [r for r in records if r["route_ok"] is not None], lambda r: r["route_ok"]
        ),
        "ttft_p50_ms": stat(ttft, p50),
        "ttft_p95_ms": stat(ttft, p95),
        "answer_p50_ms": stat(totals, p50),
        "answer_p95_ms": stat(totals, p95),
    }
    for stage in STAGES:
        values = [r["timings_ms"][f"{stage}_ms"] for r in live if f"{stage}_ms" in r["timings_ms"]]
        metrics[f"{stage}_p50_ms"] = stat(values, p50)
        metrics[f"{stage}_p95_ms"] = stat(values, p95)
    priced = [cost for cost in costs if cost is not None] if None not in costs else []
    return metrics | {
        "input_tokens": stat([r["input_tokens"] for r in counted], mean),
        "output_tokens": stat([r["output_tokens"] for r in counted], mean),
        "cost_usd": stat(priced, mean),
        "cost_billed_usd": {"value": 0.0, "low": 0.0, "high": 0.0, "n": len(counted)},
        "truncated": count(sum(bool(r.get("truncated")) for r in records), len(records)),
        "errors": count(len(records) - len(counted), len(records)),
    }


def calibration() -> dict[str, Any] | None:
    """The judge's agreement with a human (make calibrate), once measured."""
    return json.loads(CALIBRATION.read_text(encoding="utf-8")) if CALIBRATION.exists() else None


def calibrated(result: Mapping[str, Any] | None) -> bool:
    return result is not None and result["kappa"] >= JUDGE_KAPPA_MIN


def statuses(metrics: dict[str, dict[str, Any]], judge_ok: bool) -> None:
    """Pass, fail or not measured against each docs/context.md target, in place."""
    for name, entry in metrics.items():
        if name not in TARGETS:
            continue
        target, kind = TARGETS[name]
        if entry["value"] is None:
            entry["status"] = "not measured"
        elif name in JUDGED and not judge_ok:
            entry["status"] = "not measured: judge not calibrated"
        elif name == "retrieval_p95_ms":
            entry["status"] = "not measured: the target is at about 250k chunks"
        else:
            met = entry["value"] >= target if kind == "accuracy" else entry["value"] <= target
            entry["status"] = "pass" if met else "fail"


def shown(name: str, value: float | None) -> str:
    if value is None:
        return "-"
    if name.endswith("_ms"):
        return f"{value:,.0f} ms"
    if name.endswith("tokens"):
        return f"{value:,.0f}"
    if name.startswith("cost"):
        return f"${value:.4f}"
    if name in ("truncated", "errors"):
        return f"{value:.0f}"
    return f"{value:.3f}"


def notes(report: Mapping[str, Any]) -> list[str]:
    found: list[str] = []
    records = report["records"]
    if "retrieval" in records:
        textual = sum("recall" in r for r in records["retrieval"])
        wide = "very wide" if report["split"] == "test" else "wide"
        found += [
            f"Retrieval quality rests on {textual} textual questions, so its intervals are {wide}."
            " Their passage gold is AI-labeled, spot-checked by a non-expert; it is not"
            " human-verified (evals/eval-card.md).",
            f"Retrieval latency is measured at {report['index']['chunks']:,} chunks, in the eval"
            " process on this PC's CPU, each question a query in its company scope; the 250 ms"
            " target is for about 250k chunks, which this corpus cannot test.",
        ]
    if "answer" in records:
        answers = records["answer"]
        live = [r for r in answers if r["live"] and r["outcome"] != "error"]
        result = report["judge_calibration"]
        found += [
            f"Latency comes only from questions whose model calls were all live: {len(live)} of"
            f" {len(answers)}.",
            "Citation coverage is measured on the last reply before sentence removal; final"
            " answers are 100% covered by construction, since validation drops each sentence"
            " without a passing citation.",
            f"Judge metrics count: Cohen's kappa {result['kappa']:.2f} against labels by"
            f" {result.get('labeler', 'a human')}, not by the judge."
            if result is not None and calibrated(result)
            else "The judge is not calibrated (make calibrate needs kappa 0.7 or more), so"
            " citation precision and faithfulness count as not measured.",
            "Cost as billed is $0 on the free tiers; the paid-equivalent uses the prices in"
            " evals/providers.json.",
        ]
        if causes := false_refusals(answers):
            listed = "; ".join(
                f"{cause} {len(ids)} ({', '.join(ids)})" for cause, ids in causes.items()
            )
            found.append(f"False refusals by cause: {listed}.")
        errors = [f"{r['id']} ({r['error']})" for r in answers if r["outcome"] == "error"]
        if errors:
            found.append("Errors: " + "; ".join(errors))
    return found


def markdown(report: Mapping[str, Any]) -> str:
    config, golden, index = report["config"], report["golden"], report["index"]
    lines = [
        f"# Eval: {report['suite']}, {report['split']}, {report['subset']}",
        "",
        f"{report['created_at']} · golden set {golden['version']} (manifest"
        f" {golden['manifest_sha256'][:12]}, today pinned to {golden['as_of']}) · index"
        f" {index['chunks']:,} chunks, {index['model']}",
        "",
        f"Models: router `{config['router']}`, primary `{config['primary']}` (thinking"
        f" {config['thinking']}), judge `{config['judge']}`; reranker `{config['reranker']}`,"
        f" {config['rerank_candidates']} candidates, {config['rerank_max_tokens']} tokens;"
        f" refusal gate {config['min_relevance']}.",
    ]
    if code := report.get("code"):
        changes = " with uncommitted changes" if code["dirty"] else ""
        lines += [
            "",
            f"Code: commit `{code['commit'][:12]}`{changes}; source sha256"
            f" `{code['source_sha256'][:16]}`.",
        ]
    if prompts := report.get("prompts"):
        hashed = ", ".join(f"{name} `{value[:12]}`" for name, value in prompts.items())
        lines += ["", f"Prompt and schema sha256: {hashed}."]
    for suite, metrics in report["metrics"].items():
        lines += [
            "",
            f"## {suite.title()}",
            "",
            "| Metric | Target | Measured | 95% CI | n | Status |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for name, entry in metrics.items():
            if entry["n"] == 0 and name not in TARGETS:
                continue  # such as a stage no question reached
            target = shown(name, TARGETS[name][0]) if name in TARGETS else "-"
            interval = (
                f"{shown(name, entry['low'])} to {shown(name, entry['high'])}"
                if entry["low"] is not None
                else "-"
            )
            label = LABELS.get(name, name.removesuffix("_ms").replace("_", " ").capitalize())
            lines.append(
                f"| {label} | {target} | {shown(name, entry['value'])} | {interval} |"
                f" {entry['n']} | {entry.get('status', '')} |"
            )
    lines += ["", "Notes:", "", *(f"- {note}" for note in report["notes"])]
    if report["calls"]:
        lines += ["", "| Model | Calls | Live | Input tokens | Output tokens |"]
        lines.append("| --- | --- | --- | --- | --- |")
        for model, n in report["calls"].items():
            lines.append(
                f"| `{model}` | {n['calls']} | {n['live']} | {n['input_tokens']:,} |"
                f" {n['output_tokens']:,} |"
            )
    return "\n".join(lines) + "\n"


def call_totals(records: Mapping[str, list[dict[str, Any]]]) -> dict[str, dict[str, int]]:
    totals: dict[str, dict[str, int]] = {}
    for record in records.get("answer", []):
        for call in record["calls"] + (record.get("judge") or {}).get("calls", []):
            entry = totals.setdefault(
                call["model"], {"calls": 0, "live": 0, "input_tokens": 0, "output_tokens": 0}
            )
            entry["calls"] += 1
            entry["live"] += not call["cached"]
            entry["input_tokens"] += call["input_tokens"]
            entry["output_tokens"] += call["output_tokens"]
    return totals


def previous(report: Mapping[str, Any]) -> dict[str, Any] | None:
    """The latest earlier report with the same suite, split and subset."""
    same: list[dict[str, Any]] = []
    for path in [*REPORTS.glob("*.json"), *REPORTS.glob("runs/*.json")]:
        earlier = json.loads(path.read_text(encoding="utf-8"))
        if all(earlier.get(key) == report[key] for key in ("suite", "split", "subset")):
            same.append(earlier)
    return max(same, key=lambda earlier: earlier["created_at"], default=None)


def print_deltas(report: Mapping[str, Any], before: Mapping[str, Any] | None) -> None:
    if before is None:
        print("No earlier report with this suite, split and subset.")
        return
    print(f"Against the report of {before['created_at']}:")
    for suite, metrics in report["metrics"].items():
        for name, entry in metrics.items():
            old = before["metrics"].get(suite, {}).get(name, {}).get("value")
            if entry["value"] is not None and old is not None and entry["value"] != old:
                print(f"  {name}: {shown(name, old)} -> {shown(name, entry['value'])}")


def write_report(report: Mapping[str, Any]) -> Path:
    """evals/reports/runs/<UTC time>-<suite>-<split>-<subset>.json and .md; the full test run
    of every suite goes to evals/reports/<date>.json and .md."""
    final = (report["suite"], report["split"], report["subset"]) == ("all", "test", "full")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    name = f"{stamp}-{report['suite']}-{report['split']}-{report['subset']}"
    base = REPORTS / date.today().isoformat() if final else REPORTS / "runs" / name
    base.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(report, indent=1, ensure_ascii=False, default=str) + "\n"
    base.with_suffix(".json").write_text(body, encoding="utf-8", newline="\n")
    base.with_suffix(".md").write_text(markdown(report), encoding="utf-8", newline="\n")
    return base.with_suffix(".md")


def apply_floors(report: Mapping[str, Any], set_floors: bool, judge_ok: bool) -> list[str]:
    """Metrics past their floors in thresholds.json; with set_floors, tighten the floors by the
    rule in metrics.floor, never loosening one."""
    floors = json.loads(THRESHOLDS.read_text(encoding="utf-8")) if THRESHOLDS.exists() else {}
    past: list[str] = []
    for suite, metrics in report["metrics"].items():
        key = f"{suite}:{report['split']}:{report['subset']}"
        limits = floors.setdefault(key, {})
        for name, limit in limits.items():
            value = metrics.get(name, {}).get("value")
            if value is not None and broken(TARGETS[name][1], value, limit):
                past.append(f"{key} {name}: {shown(name, value)} is past {shown(name, limit)}")
        if not set_floors:
            continue
        for name, (target, kind) in TARGETS.items():
            entry = metrics.get(name)
            if entry is None or entry["value"] is None or (name in JUDGED and not judge_ok):
                continue
            new = floor(kind, entry["value"], entry["low"], entry["high"], target)
            limits[name] = round(tighter(kind, limits.get(name), new), 6)
    if set_floors:
        body = json.dumps(floors, indent=1, sort_keys=True) + "\n"
        THRESHOLDS.write_text(body, encoding="utf-8", newline="\n")
    return past


async def save_run(engine: AsyncEngine, report: Mapping[str, Any]) -> None:
    """One eval_runs row: the configuration and every metric's value."""
    keys = ("suite", "split", "subset", "golden", "index", "code", "prompts")
    config = report["config"] | {key: report.get(key) for key in keys}
    metrics = {
        suite: {name: entry["value"] for name, entry in values.items()}
        for suite, values in report["metrics"].items()
    }
    row = {"dataset_version": f"golden-{VERSION}", "config": config, "metrics": metrics}
    async with engine.begin() as connection:
        await connection.execute(insert(EvalRun).values(**row))


async def evaluate(args: argparse.Namespace) -> int:
    answers = args.suite in ("all", "answer")
    if answers:
        os.environ["AI_ENABLED"] = "true"  # an answer run calls the models on purpose
    os.environ.setdefault("HF_HUB_OFFLINE", "1")  # pinned local models load from HF_HOME
    settings = load_settings(EvalSettings)
    configure_logging("eval", "WARNING")
    if answers and args.judge:
        field = PROVIDER_KEYS[settings.llm_judge.partition(":")[0]]
        secret = getattr(settings, field) if field else None
        if field and not (secret and secret.get_secret_value()):
            raise SystemExit(f"LLM_JUDGE needs {field.upper()}.")
    golden = load_golden()
    questions = [
        q
        for q in golden.questions
        if q["split"] == args.split and (args.subset == "full" or q["ci"])
    ]
    if not questions:
        raise SystemExit(f"No {args.subset} questions in {args.split}: the ci subset is in dev.")
    code = code_version()  # before any call: the code this run measures
    engine = make_engine(settings)
    try:
        await check_corpus(engine, golden)
        index = await index_version(engine, settings.retrieval_embedding_column)
        embedder = EMBEDDING_MODELS[settings.retrieval_embedding_column]
        config = {
            "router": settings.llm_router,
            "primary": settings.llm_primary,
            "thinking": args.thinking,
            "judge": settings.llm_judge if answers and args.judge else None,
            "embedder": f"{embedder}@{REVISIONS[embedder]}",
            "reranker": f"{settings.rerank_model}@{REVISIONS[settings.rerank_model]}",
            "rerank_candidates": settings.rerank_candidates,
            "rerank_max_tokens": settings.rerank_max_tokens,
            "rerank_timeout_ms": settings.rerank_timeout_ms,
            "min_relevance": args.min_relevance,
            "tag": args.tag or None,
            "primary_tag": args.primary_tag or None,
        }
        print(
            f"Golden set {VERSION}: {len(questions)} {args.split} questions ({args.subset});"
            f" index {index['chunks']:,} chunks; today pinned to {golden.manifest['as_of']}."
        )
        records: dict[str, list[dict[str, Any]]] = {}
        metrics: dict[str, dict[str, dict[str, Any]]] = {}
        suite = None
        if args.suite in ("all", "retrieval"):
            records["retrieval"] = await retrieval_suite(engine, settings, golden, questions)
            metrics["retrieval"] = retrieval_metrics(records["retrieval"])
        if answers:
            suite = AnswerSuite(args, settings, engine, golden, index)
            try:
                records["answer"] = await suite.run(questions)
            finally:
                await suite.close()
            metrics["answer"] = answer_metrics(records["answer"])
        result = calibration()
        for values in metrics.values():
            statuses(values, calibrated(result))
        report: dict[str, Any] = {
            "suite": args.suite,
            "split": args.split,
            "subset": args.subset,
            "created_at": now(),
            "golden": {
                "version": VERSION,
                "as_of": golden.manifest["as_of"],
                "manifest_sha256": sha256(ROOT / "manifest.json"),
            },
            "index": index,
            "config": config,
            "code": code,
            "prompts": prompt_hashes(suite.as_of, suite.tracked) if suite else None,
            "judge_calibration": result,
            "metrics": metrics,
            "calls": call_totals(records),
            "records": records,
        }
        report["notes"] = notes(report)
        before = previous(report)
        path = write_report(report)
        await save_run(engine, report)
        if suite is not None:
            suite.run_file.unlink(missing_ok=True)  # complete: a rerun starts over, from the cache
        print(f"Report: {path}")
        print_deltas(report, before)
        past = apply_floors(report, False, calibrated(result))  # floors come from --set-floors
        for line in past:
            print(f"Floor broken: {line}")
        return 1 if past else 0
    finally:
        await engine.dispose()


def compare(first: Path, second: Path) -> None:
    """Paired differences per question, first report minus second, with 95% bootstrap CIs. The
    primary call's own times (its first reply, when live) also pair questions whose router reply
    came from the cache: after a 429 retry, or a --thinking change under the same --tag."""
    a, b = (json.loads(path.read_text(encoding="utf-8")) for path in (first, second))

    def pair(record: Mapping[str, Any], field: str) -> tuple[int, int] | None:
        found = record.get(field) or (record.get("judge") or {}).get(field)
        return (found[0], found[1]) if found and found[1] else None

    def primary(record: Mapping[str, Any], field: str) -> float | None:
        call = next((c for c in record.get("calls", []) if c["role"] == "primary"), None)
        return None if call is None or call["cached"] else call[field]

    checks: list[tuple[str, str, Callable[[Mapping[str, Any]], Any], Callable[..., float]]] = [
        ("retrieval", "mrr@10", lambda r: r.get("mrr"), mean),
        ("retrieval", "recall@10", lambda r: r.get("recall"), mean),
        ("answer", "numeric_exact_match", lambda r: r.get("exact"), mean),
        ("answer", "draft_citation_pass_rate", lambda r: pair(r, "draft_quotes"), pooled),
        ("answer", "citation_precision", lambda r: pair(r, "precise"), pooled),
        ("answer", "faithfulness", lambda r: pair(r, "faithful"), pooled),
        ("answer", "primary_first_token_p50_s", lambda r: primary(r, "first_token_s"), p50),
        ("answer", "primary_first_token_p95_s", lambda r: primary(r, "first_token_s"), p95),
        ("answer", "primary_total_p50_s", lambda r: primary(r, "latency_s"), p50),
        ("answer", "primary_total_p95_s", lambda r: primary(r, "latency_s"), p95),
    ]
    print(f"{first.name} minus {second.name}:")
    for suite, name, value, statistic in checks:
        left = {r["id"]: value(r) for r in a["records"].get(suite, [])}
        right = {r["id"]: value(r) for r in b["records"].get(suite, [])}
        both = sorted(left.keys() & right.keys())
        pairs = [(left[q], right[q]) for q in both if left[q] is not None and right[q] is not None]
        if not pairs:
            continue

        def difference(
            items: Sequence[tuple[Any, Any]], statistic: Callable[..., float] = statistic
        ) -> float:
            return statistic([x for x, _ in items]) - statistic([y for _, y in items])

        low, high = bootstrap(pairs, difference)
        left_value, right_value = statistic([x for x, _ in pairs]), statistic([y for _, y in pairs])
        print(
            f"  {name}: {left_value:.3f} vs {right_value:.3f}, difference {difference(pairs):+.3f}"
            f" (95% CI {low:+.3f} to {high:+.3f}, n={len(pairs)})"
        )
    for report, path in ((a, first), (b, second)):
        latencies = [
            f"{name} {shown(name, entry['value'])}"
            for values in report["metrics"].values()
            for name, entry in values.items()
            if name.endswith("_ms") and name.split("_")[0] in ("rerank", "generate", "ttft")
        ]
        print(f"  {path.name}: {', '.join(latencies)}")


def refusal_sweep(records: Sequence[Mapping[str, Any]], max_false: float = 0.05) -> dict[str, Any]:
    """Decision 2's rule on a gate-off run: for each range of thresholds t, the correct and false
    refusal rates if the gate also refused each search-only answer with a top score under t.

    The best range has the most correct refusal with false refusal at most `max_false` (then the
    least false refusal), and t is its midpoint; None when the range is unbounded. Errors and
    degraded searches are left out, and an answer with a fact is never gated.
    """
    kept = [r for r in records if r["outcome"] != "error" and not r["degraded"]]
    gated = {
        r["id"]: r["top_score"]
        for r in kept
        if r["top_score"] is not None and not any(alias[0] == "F" for alias in r["sources"])
    }
    refuse = [r for r in kept if r["expect"] == "refuse"]
    answer = [r for r in kept if r["expect"] == "answer"]
    bounds = [-math.inf, *sorted(set(gated.values())), math.inf]
    ranges: list[dict[str, Any]] = []
    for low, high in itertools.pairwise(bounds):  # any t in (low, high] gates scores <= low

        def refused(r: Mapping[str, Any], low: float = low) -> bool:
            return r["outcome"] == "refused" or gated.get(r["id"], math.inf) <= low

        ranges.append(
            {
                "low": low,
                "high": high,
                "correct": sum(map(refused, refuse)) / len(refuse),
                "false": sum(map(refused, answer)) / len(answer),
                "gated": sorted(q for q, score in gated.items() if score <= low),
            }
        )
    excluded = len(records) - len(kept)
    allowed = [row for row in ranges if row["false"] <= max_false]
    if not allowed:  # other refusal paths alone break the limit, so no threshold meets the rule
        return {"ranges": ranges, "best": None, "excluded": excluded}
    top = max(row["correct"] for row in allowed)
    least = min(row["false"] for row in allowed if row["correct"] == top)
    best = [row for row in allowed if (row["correct"], row["false"]) == (top, least)]
    low, high = best[0]["low"], best[-1]["high"]
    t = (low + high) / 2 if math.isfinite(low) and math.isfinite(high) else None
    return {"ranges": ranges, "best": {"low": low, "high": high, "t": t}, "excluded": excluded}


def sweep(path: Path) -> None:
    """Print decision 2's sweep for a gate-off answer report (--min-relevance=-100)."""
    report = json.loads(path.read_text(encoding="utf-8"))
    if report["config"]["min_relevance"] > -100:
        raise SystemExit("The sweep needs a gate-off run: ARGS=--min-relevance=-100.")
    records = report["records"]["answer"]
    result = refusal_sweep(records)
    print(f"{path.name}: {len(records)} questions, {result['excluded']} left out (error, degraded)")
    for row in result["ranges"]:
        print(
            f"  t in ({row['low']:.3f}, {row['high']:.3f}]: correct refusal"
            f" {row['correct']:.3f}, false refusal {row['false']:.3f}, gated {row['gated']}"
        )
    best = result["best"]
    if best is None:
        lowest = result["ranges"][0]["false"]
        print(f"No threshold meets the rule: false refusal is {lowest:.3f} with the gate off.")
    else:
        print(f"Best range ({best['low']:.3f}, {best['high']:.3f}], t = {best['t']}")
    for cause, ids in false_refusals(records).items():
        print(f"  False refusals with the gate off, {cause}: {len(ids)} ({', '.join(ids)})")
    scored = sorted(
        (r for r in records if r["top_score"] is not None), key=lambda r: r["top_score"]
    )
    for r in scored:
        facts = any(alias[0] == "F" for alias in r["sources"])
        print(
            f"  {r['top_score']:8.3f} {r['id']} expect {r['expect']}, {r['outcome']}"
            f"{', has a fact' if facts else ''}{', degraded' if r['degraded'] else ''}"
        )


def set_floors(path: Path) -> None:
    """Write to thresholds.json the floors the rule gives a saved report's measured values, for
    every metric with a target (quality, tokens, cost and latency), keeping only tighter ones."""
    report = json.loads(path.read_text(encoding="utf-8"))
    for line in apply_floors(report, True, calibrated(report.get("judge_calibration"))):
        print(f"Past an earlier floor, which stays: {line}")
    floors = json.loads(THRESHOLDS.read_text(encoding="utf-8"))
    for suite in report["metrics"]:
        key = f"{suite}:{report['split']}:{report['subset']}"
        listed = ", ".join(f"{name} {shown(name, v)}" for name, v in sorted(floors[key].items()))
        print(f"{key}: {listed}")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m evals.harness", description=__doc__)
    parser.add_argument("--suite", choices=("all", "retrieval", "answer"), default="all")
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--subset", choices=("full", "ci"), default="full")
    parser.add_argument("--tag", default="", help="call the answer models live once, under TAG")
    parser.add_argument("--primary-tag", default="", help="call only the primary live, under TAG")
    parser.add_argument("--min-relevance", type=float, default=RELEVANCE_MIN)
    parser.add_argument("--thinking", choices=("minimal", "default"), default="minimal")
    parser.add_argument("--no-judge", dest="judge", action="store_false")
    parser.add_argument(
        "--set-floors", type=Path, metavar="REPORT", help="floors from a saved report's values"
    )
    parser.add_argument("--compare", nargs=2, type=Path, metavar="REPORT")
    parser.add_argument("--sweep", type=Path, metavar="REPORT", help="refusal threshold sweep")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])
    if args.compare:
        compare(*args.compare)
        return
    if args.sweep:
        sweep(args.sweep)
        return
    if args.set_floors:
        set_floors(args.set_floors)
        return
    try:
        code = asyncio.run(evaluate(args))
    except Stop as stop:
        print(stop, file=sys.stderr)
        code = stop.code
    sys.exit(code)


if __name__ == "__main__":
    main()
