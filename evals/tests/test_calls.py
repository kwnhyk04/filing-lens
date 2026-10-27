"""The eval call layer, judge replies, router scoring and the refusal sweep, on fakes: no model
is called."""

import asyncio
import json
from collections import Counter
from collections.abc import AsyncIterator, Mapping
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from evals import harness, judge
from evals.calibrate import FOLLOWUP_MODELS, draw, draw_followup, imported, spot_check
from evals.calls import Cache, Call, Recorded, Stop, patiently
from evals.harness import EvalSettings, answer_path, code_version, refusal_sweep, routed
from filinglens_api import answering
from filinglens_api.answering import PostgresEvidence
from filinglens_api.schemas import Answer, Calculation, Citation, Usage
from filinglens_core.errors import AiUnavailableError, RateLimitedError
from filinglens_core.settings import ApiSettings, load_settings
from filinglens_llm.providers import Completion
from filinglens_retrieval import Ranking, Scope

TEXTUAL = Path(__file__).parents[2] / "services/api/tests/fixtures/answers/textual.json"
ENV = {  # what load_settings(EvalSettings) needs; nothing listens on these
    "DATABASE_URL": "postgresql+asyncpg://app:p@localhost:5433/app",
    "REDIS_URL": "redis://localhost:6380/0",
    "BROKER_URL": "amqp://app:p@localhost:5672//",
    "API_KEY": "k" * 32,
    "ADMIN_API_KEY": "a" * 32,
}


class Scripted:
    """A provider that replies from a script: each item a Completion or an error to raise."""

    name = "fake:model"

    def __init__(self, *script: Completion | Exception) -> None:
        self.script = list(script)
        self.calls = 0
        self.prompts: list[str] = []  # each user prompt it was sent

    def _next(self) -> Completion:
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def complete(
        self, system: str, user: str, *, max_tokens: int, schema: Mapping[str, Any] | None = None
    ) -> Completion:
        self.prompts.append(user)
        return self._next()

    async def stream(
        self, system: str, user: str, *, max_tokens: int
    ) -> AsyncIterator[str | Completion]:
        completion = self._next()
        yield completion.text
        yield completion


def reply(text: str) -> Completion:
    return Completion("fake:model", text, 10, 5, 0.5, 0.1)


async def test_a_repeated_call_comes_from_the_cache_and_a_tag_calls_live(tmp_path: Path) -> None:
    fake, calls = Scripted(reply("first"), reply("live again")), list[Call]()
    path = tmp_path / "calls.jsonl"

    async def streamed(context: Mapping[str, Any]) -> list[str | Completion]:
        model = Recorded(fake, "primary", Cache(path), context, calls)  # a new process each time
        return [item async for item in model.stream("system", "user", max_tokens=5)]

    untagged = {"question": "x01", "path": {"primary": "fake:model"}}
    first = await streamed(untagged)
    assert await streamed(untagged) == first
    assert fake.calls == 1
    tagged = {"question": "x01", "path": {"primary": "fake:model", "tag": "d3"}}
    assert (await streamed(tagged))[0] == "live again"
    assert await streamed(untagged) == first  # the earlier reply stays under its key
    assert [call.cached for call in calls] == [False, True, False, True]
    assert calls[0].truncated  # 5 output tokens of max 5
    assert "text" not in calls[0].saved()
    model = Recorded(fake, "primary", Cache(path), {"question": "x01"}, [])
    other = Recorded(fake, "primary", Cache(path), {"question": "x02"}, [])
    assert model.key("s", "u", 5, None) != model.key("s", "u2", 5, None)
    assert model.key("s", "u", 5, None) != other.key("s", "u", 5, None)


def test_a_tag_joins_the_answer_path_only_when_set() -> None:
    stub = SimpleNamespace(
        llm_router="groq:openai/gpt-oss-20b", llm_primary="gemini:gemini-3.5-flash-lite",
        retrieval_embedding_column="embedding", rerank_candidates=50, rerank_max_tokens=512,
        rerank_model="cross-encoder/ms-marco-TinyBERT-L-2-v2",
    )  # fmt: skip
    settings = cast(ApiSettings, stub)
    untagged = answer_path(settings, {"sha256": "abc"}, "")
    # Every earlier run's cache keys hold exactly these: a new field would re-ask every model.
    assert set(untagged) == {"router", "primary", "embedder", "reranker", "rerank", "index"}
    assert answer_path(settings, {"sha256": "abc"}, "d3") == untagged | {"tag": "d3"}
    # --router-primary: a Claude run's router keys equal the Gemini run's, so it reuses its routes.
    claude = cast(ApiSettings, SimpleNamespace(**vars(stub) | {"llm_primary": "anthropic:x"}))
    routes = answer_path(claude, {"sha256": "abc"}, "", "gemini:gemini-3.5-flash-lite")
    assert routes == untagged and answer_path(claude, {"sha256": "abc"}, "") != untagged
    # The reranker's deadline is in no key: a search that met the API's 500 ms keeps its passages.
    patient = cast(ApiSettings, SimpleNamespace(**vars(stub) | {"rerank_timeout_ms": 60_000}))
    assert answer_path(patient, {"sha256": "abc"}, "") == untagged


async def test_the_answer_suite_waits_for_the_reranker_as_the_retrieval_suite_does(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Past the API's 500 ms a search keeps fused order, so an answer's passages, and the cache
    keys of its replies, would follow the runner's speed (10b's CI eval, 2026-10-21)."""
    for name, value in (ENV | {"RERANK_TIMEOUT_MS": "500"}).items():  # as .env.example sets it
        monkeypatch.setenv(name, value)
    deadlines: list[float] = []

    async def search(*args: Any, timeout_s: float, **kwargs: Any) -> Ranking:
        deadlines.append(timeout_s)
        return Ranking([], False, None, {})

    monkeypatch.setattr(answering, "search", search)
    await PostgresEvidence(cast(Any, None), harness.eval_settings()).search("q", Scope())
    assert deadlines == [harness.RETRIEVAL_TIMEOUT_S]


async def test_a_429_waits_and_the_third_in_a_row_stops_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    waits: list[float] = []

    async def no_wait(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", no_wait)
    cache = Cache(tmp_path / "calls.jsonl")
    limited = RateLimitedError("groq is rate limited (429).", retry_after_s=2)
    model = Recorded(Scripted(limited, reply("ok")), "router", cache, {}, [])
    assert (await patiently(lambda: model.complete("s", "u", max_tokens=9))).text == "ok"
    assert waits == [2]
    gemini = RateLimitedError("gemini is rate limited (429).")  # no Retry-After: 60 s
    model = Recorded(Scripted(gemini, gemini, gemini), "primary", cache, {}, [])
    with pytest.raises(Stop) as stopped:
        await patiently(lambda: model.complete("s", "u2", max_tokens=9))
    assert stopped.value.code == 2 and waits == [2, 60, 60]
    daily = RateLimitedError("groq is rate limited (429).", retry_after_s=3600)
    model = Recorded(Scripted(daily), "router", cache, {}, [])
    with pytest.raises(Stop):
        await patiently(lambda: model.complete("s", "u3", max_tokens=9))
    assert waits == [2, 60, 60]  # a long Retry-After stops at once


def test_the_judge_must_cover_every_sentence_and_citation() -> None:
    answer = "Net sales were $416.2 billion [1]. Services grew [2][3]."
    rows = [
        {"sentence": 1, "supported": "yes", "citations": [{"source": 1, "supports": True}]},
        {
            "sentence": 2,
            "supported": "partly",
            "citations": [{"source": 2, "supports": True}, {"source": 3, "supports": False}],
        },
    ]
    verdict = judge.parse(json.dumps({"sentences": rows}), answer)
    assert verdict.supported == ["yes", "partly"]
    assert verdict.supports == [True, True, False]
    with pytest.raises(judge.JudgeError):
        judge.parse(json.dumps({"sentences": rows[:1]}), answer)  # a sentence skipped
    rows[1]["citations"] = rows[1]["citations"][:1]
    with pytest.raises(judge.JudgeError):
        judge.parse(json.dumps({"sentences": rows}), answer)  # a citation skipped
    with pytest.raises(judge.JudgeError):
        judge.parse("not json", answer)


async def test_a_number_without_a_source_errors_before_any_judge_call(tmp_path: Path) -> None:
    """The textual recording's answer shows [2][3][12] with 6 citations (Gemini wrote [12] for
    C12), like x18's in the nightly run; judged live once, the judge made up a rating for 12."""
    recorded = json.loads(TEXTUAL.read_text(encoding="utf-8"))
    answer = Answer.model_validate(recorded["answer"])
    search = next(call for call in recorded["evidence"] if call["method"] == "search")
    texts = {hit["chunk_id"]: hit["text"] for hit in search["result"]["hits"]}
    sources = {
        f"C{n}": harness.Src(c.chunk_id, None, "Apple 10-K", texts[c.chunk_id or ""], None)
        for n, c in enumerate(answer.citations, 1)
    }
    suite = SimpleNamespace(judge=Scripted(), cache=Cache(tmp_path / "calls.jsonl"))
    question = {"id": "textual", "question": recorded["question"]}
    found = await harness.AnswerSuite.judged(
        cast(harness.AnswerSuite, suite), question, answer, sources
    )
    assert found == {"error": "sentence 2: given sources [2, 3], cited [2, 3, 12]", "calls": []}
    assert suite.judge.calls == 0  # no judge call spent


K1_TEXT = (
    "Fiscal 2024: 391,035,000,000 USD. Fiscal 2025: 416,161,000,000 USD. Fiscal 2025 is higher by"
    " 25,126,000,000 USD, 6.43% more than fiscal 2024."
)
C09_SOURCES = {  # load_sources: two facts, and the calculation, whose lines come with its citation
    "F1": harness.Src(None, "37437", "2025", "416,161,000,000 USD", Decimal(416_161_000_000)),
    "F2": harness.Src(None, "37409", "2024", "391,035,000,000 USD", Decimal(391_035_000_000)),
    "K1": harness.Src(None, None, "Calculated by FilingLens", "", None),
}


async def test_the_judge_reads_a_calculation_under_the_numbers_of_its_facts(
    tmp_path: Path,
) -> None:
    url = "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/"
    answer = Answer(
        answer="Revenue rose from $391.0 billion to $416.2 billion, up $25.1 billion [1][2][3].",
        citations=[
            Citation(fact_id="37409", quote="391,035,000,000 USD", filing_url=url),
            Citation(fact_id="37437", quote="416,161,000,000 USD", filing_url=url),
            Citation(calculation=Calculation(inputs=[1, 2]), quote=K1_TEXT, filing_url=url),
        ],
        degraded=False,
        usage=Usage(input_tokens=1, output_tokens=1, cost_usd=0),
    )
    verdicts = [{"source": n, "supports": True} for n in (1, 2, 3)]
    rows = [{"sentence": 1, "supported": "yes", "citations": verdicts}]
    suite = SimpleNamespace(
        judge=Scripted(reply(json.dumps({"sentences": rows}))), cache=Cache(tmp_path / "c.jsonl")
    )
    question = {"id": "c09", "question": "How did Apple's revenue change in fiscal 2025?"}
    found = await harness.AnswerSuite.judged(
        cast(harness.AnswerSuite, suite), question, answer, C09_SOURCES
    )
    assert found["precise"] == [3, 3]
    prompt = suite.judge.prompts[0]
    assert f'[3] Calculated by FilingLens from sources 1 and 2\nQuote given: "{K1_TEXT}"' in prompt


def test_coverage_counts_a_sentence_a_calculation_holds() -> None:
    text = 'Net sales rose $25.1 billion [K1].\n\nSources:\n[K1] "25,126,000,000 USD"'
    calls = [Call("primary", "fake:model", "k", False, 10, 5, 0.5, 0.1, False, text)]
    question = {"category": "comparison", "facts": [], "routing": {"route": None}}
    found = harness.scores(question, None, None, calls, C09_SOURCES, {"AAPL"})
    assert (found["coverage"], found["draft_quotes"]) == ([1, 1], [0, 0])


def test_router_scoring_skips_what_the_gold_leaves_open() -> None:
    tracked = {"AAPL"}
    gold = {"route": "numeric", "tickers": ["AAPL"], "fiscal_years": [2025], "metric": "revenue"}
    got = gold | {"fiscal_period": "FY", "other_companies": []}
    assert routed(gold, got, tracked) == (True, True)
    assert routed(gold, got | {"fiscal_years": [2024]}, tracked) == (True, False)
    assert routed(gold, None, tracked) == (False, False)
    absent = {"route": None, "tickers": ["AAPL"], "fiscal_years": None, "metric": None}
    assert routed(absent, got | {"route": "textual"}, tracked) == (None, True)
    netflix = gold | {"tickers": ["NFLX"]}  # untracked: right only as an other company
    assert routed(netflix, got | {"tickers": [], "other_companies": ["Netflix"]}, tracked)[1]
    assert not routed(netflix, got | {"tickers": []}, tracked)[1]


def test_the_calibration_sample_mixes_strata_without_repeats() -> None:
    def items(stratum: str, reply: str, questions: int, per: int) -> list[dict[str, Any]]:
        return [
            {"id": f"q{q:02d}", "stratum": stratum, "reply": reply, "index": i}
            | {"sentence": f"Sentence {i} of q{q:02d}."}  # a constructed one repeats its source
            for q in range(questions)
            for i in range(per)
        ]

    found = {
        "failing": items("failing", "draft", 1, 1),
        "constructed": items("constructed", "final", 40, 1),
        "passing": items("passing", "final", 40, 3),
    }
    sample = draw(found)
    assert Counter(item["stratum"] for item in sample) == {
        "failing": 1,
        "constructed": 9,
        "passing": 20,
    }
    assert max(Counter(item["id"] for item in sample).values()) <= 2
    keys = [(item["id"], item["reply"], item["index"]) for item in sample]
    assert len(keys) == len(set(keys))  # never one sentence as both natural and constructed
    assert draw(found) == sample  # a fixed seed


def test_set_floors_applies_the_rule_to_a_saved_reports_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    thresholds = tmp_path / "thresholds.json"
    monkeypatch.setattr(harness, "THRESHOLDS", thresholds)

    def entry(value: float, low: float, high: float) -> dict[str, float]:
        return {"value": value, "low": low, "high": high, "n": 20}

    answer = {
        "numeric_exact_match": entry(0.95, 0.90, 1.0),
        "faithfulness": entry(0.94, 0.90, 0.97),
        "false_refusal": entry(0.10, 0.0, 0.20),
        "ttft_p95_ms": entry(3000.0, 2500.0, 3500.0),  # live latency, past its 2,000 ms target
        "input_tokens": entry(3000.0, 2800.0, 3200.0),
        "cost_billed_usd": entry(0.0, 0.0, 0.0),
    }
    report = {"suite": "all", "split": "test", "subset": "full"} | {
        "config": {"primary": "gemini:gemini-3.5-flash-lite"},
        "judge_calibration": {"kappa": 0.84},
        "metrics": {"answer": answer, "retrieval": {"recall@10": entry(0.60, 0.45, 0.75)}},
    }
    saved = tmp_path / "report.json"
    saved.write_text(json.dumps(report), encoding="utf-8")
    harness.set_floors(saved)
    floors = json.loads(thresholds.read_text(encoding="utf-8"))
    free = "answer:test:full:gemini:gemini-3.5-flash-lite"  # answer floors go per primary model
    assert floors[free] == {
        "numeric_exact_match": 0.763869,  # min(Wilson low of 19 of 20, target)
        "faithfulness": 0.9,  # counted: the run's judge was calibrated
        "false_refusal": 0.301034,  # a ceiling: max(Wilson high of 2 of 20, target)
        "ttft_p95_ms": 5250.0,  # a known miss: high x 1.5
        "input_tokens": 4800.0,  # meets its target: min(high x 1.5, target)
        "cost_billed_usd": 0.0,  # the free setup bills nothing
    }
    assert floors["retrieval:test:full"] == {"recall@10": 0.55}  # no model call: value - 1/n
    answer["ttft_p95_ms"] = entry(2800.0, 2400.0, 3000.0)
    saved.write_text(json.dumps(report), encoding="utf-8")
    harness.set_floors(saved)
    tightened = json.loads(thresholds.read_text(encoding="utf-8"))[free]
    assert tightened["ttft_p95_ms"] == 4500.0  # floors only tighten
    answer["ttft_p95_ms"] = entry(4000.0, 3600.0, 4400.0)
    saved.write_text(json.dumps(report), encoding="utf-8")
    harness.set_floors(saved)  # a slower run: past the floor, which stays
    kept = json.loads(thresholds.read_text(encoding="utf-8"))[free]
    assert kept["ttft_p95_ms"] == 4500.0
    claude = report | {
        "config": {"primary": "anthropic:claude-haiku-5-5"},
        "metrics": {"answer": {"cost_billed_usd": entry(0.0006, 0.0005, 0.0007)}},
    }
    saved.write_text(json.dumps(claude), encoding="utf-8")
    before = thresholds.read_text(encoding="utf-8")
    with pytest.raises(SystemExit, match="never set floors"):  # measured beside, never gated
        harness.set_floors(saved)
    assert thresholds.read_text(encoding="utf-8") == before


def test_the_judge_can_never_be_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ENV | {"LLM_JUDGE": "anthropic:claude-haiku-5-5"}  # its reference labels came from Claude
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(SystemExit, match=r"LLM_JUDGE: .*cannot be Claude"):
        load_settings(EvalSettings)


async def test_credits_gone_in_an_eval_stop_the_run_with_exit_4_not_as_a_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Gone:
        """The Answerer once the pinned model's credits are gone (no fallback in evals)."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def events(self, *args: Any) -> AsyncIterator[Any]:
            raise AiUnavailableError("anthropic:claude-haiku-5-5 is off for the credit period.")
            yield  # an async generator, as Answerer.events is

    monkeypatch.setattr(harness, "Answerer", Gone)
    suite = SimpleNamespace(
        evidence=None, redis=None, as_of=date(2026, 10, 16), models=lambda qid, calls: None,
        args=SimpleNamespace(min_relevance=-3.0, judge=False),
    )  # fmt: skip
    question = {"id": "x01", "question": "What does Apple make?"}
    with pytest.raises(Stop) as stopped:
        await harness.AnswerSuite.one(cast(harness.AnswerSuite, suite), question)
    assert stopped.value.code == 4  # credits do not come back when a quota resets


def test_the_code_version_pins_the_source_as_it_stands() -> None:
    version = code_version()
    assert len(version["commit"]) == 40 and len(version["source_sha256"]) == 64
    assert code_version() == version  # nothing changed in between


def test_the_follow_up_sample_draws_the_first_model_before_topping_up() -> None:
    def items(model: str, questions: int, per: int) -> list[dict[str, Any]]:
        return [
            {"id": f"q{q:02d}", "model": model, "reply": "draft", "index": i}
            | {"sentence": f"Sentence {i} of q{q:02d} by {model}."}
            for q in range(questions)
            for i in range(per)
        ]

    pools = [items("4b", 3, 3), items("4a", 10, 1)]  # 4b: 3 questions, at most 2 each
    sample = draw_followup(pools)
    assert Counter(item["model"] for item in sample) == {"4b": 6, "4a": 4}
    assert max(Counter(item["id"] for item in sample).values()) <= 2
    assert draw_followup(pools) == sample  # a fixed seed
    assert EvalSettings.model_fields["llm_judge"].default not in FOLLOWUP_MODELS


def test_the_spot_check_counts_unsupported_sentences_the_judge_failed() -> None:
    sample = [{"model": "4b"}, {"model": "4a"}, {"model": "4a"}, {"model": "4a"}]
    labels = {0: False, 1: False, 2: True, 3: False}
    verdicts = {0: "partly", 1: "yes", 2: "yes", 3: None}  # s04's reply did not parse
    result = spot_check(sample, verdicts, labels)
    assert (result["unsupported"], result["caught"], result["unscored"]) == (3, 1, 1)
    assert (result["supported"], result["supported_yes"]) == (1, 1)
    assert "kappa" not in result


def test_imported_labels_must_cover_each_sentence_once() -> None:
    sample = [{"stratum": "passing"}, {"stratum": "constructed"}]
    rows = [
        {"id": "s01", "label": "y", "labeler": "claude", "why": "states it"},
        {"id": "s02", "label": "n", "labeler": "claude", "why": "off topic"},
    ]
    assert imported(sample, rows) == ({0: True, 1: False}, "claude")
    for broken in (rows[:1], [*rows, rows[0]], [rows[0], rows[1] | {"label": "maybe"}]):
        with pytest.raises(SystemExit):
            imported(sample, broken)


def test_the_sweep_takes_the_midpoint_of_the_best_range_under_5_percent_false_refusal() -> None:
    chunks, fact = {"C1": "chunk"}, {"F1": "1", "C1": "chunk"}

    def record(qid: str, expect: str, outcome: str, top: float | None, **extra: Any) -> dict:
        return {"id": qid, "expect": expect, "outcome": outcome, "top_score": top,
                "sources": chunks, "degraded": False} | extra  # fmt: skip

    records = [
        record("a", "refuse", "answered", 0.5),
        record("b", "refuse", "answered", -4.0),
        record("c", "answer", "answered", 3.0),
        record("d", "answer", "answered", -6.0, sources=fact),  # a fact: never gated
        record("e", "refuse", "refused", None),
        record("f", "answer", "error", None),  # left out
        record("g", "answer", "answered", 1.0, degraded=True),  # left out
    ]
    result = refusal_sweep(records)
    assert result["best"] == {"low": 0.5, "high": 3.0, "t": 1.75}  # gates a and b, not c
    assert result["excluded"] == 2
    assert [row["correct"] for row in result["ranges"]] == [1 / 3, 2 / 3, 1.0, 1.0]
    assert result["ranges"][-1]["false"] == 0.5  # gating c too breaks the 5% limit


CLAUDE = "anthropic:claude-haiku-5-5"
REFUSED: list[tuple[str, list[str], dict[str, str], str]] = [
    ("the official eval", [], {"LLM_PRIMARY": CLAUDE}, "official eval runs the free models"),
    ("--ci", ["--claude-primary", "--ci"], {}, "local only"),
    ("a CI runner", ["--claude-primary"], {"CI": "true"}, "local only"),
    ("no key", ["--claude-primary"], {"ANTHROPIC_API_KEY": ""}, "needs ANTHROPIC_API_KEY"),
]


@pytest.mark.parametrize(
    ("argv", "env", "refusal"), [row[1:] for row in REFUSED], ids=[row[0] for row in REFUSED]
)
def test_claude_answers_an_eval_only_in_the_labelled_local_configuration(
    monkeypatch: pytest.MonkeyPatch, argv: list[str], env: dict[str, str], refusal: str
) -> None:
    monkeypatch.delenv("CI", raising=False)  # GitHub sets it on its runners
    for name, value in (ENV | {"ANTHROPIC_API_KEY": "sk-test"} | env).items():
        monkeypatch.setenv(name, value)
    with pytest.raises(SystemExit, match=refusal):
        harness.answer_model(harness.parse_args(argv), harness.eval_settings())


FREE: str = EvalSettings.model_fields["llm_primary"].default  # the official run's answer model


# .env's LLM_PRIMARY: the free default, or Claude first as production runs it (README).
@pytest.mark.parametrize("primary", [FREE, CLAUDE], ids=["free primary", "Claude primary"])
def test_the_claude_configuration_swaps_the_answer_model_and_keeps_the_official_routes(
    monkeypatch: pytest.MonkeyPatch, primary: str
) -> None:
    monkeypatch.delenv("CI", raising=False)
    for name, value in (ENV | {"ANTHROPIC_API_KEY": "sk-test", "LLM_PRIMARY": primary}).items():
        monkeypatch.setenv(name, value)
    args = harness.parse_args(["--claude-primary"])
    assert harness.answer_model(args, harness.eval_settings()).llm_primary == CLAUDE
    assert args.router_primary == FREE  # the official free run's routes: a fair comparison


def test_the_official_eval_keeps_the_free_models(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in (ENV | {"LLM_PRIMARY": FREE}).items():
        monkeypatch.setenv(name, value)
    official = harness.eval_settings()
    assert harness.answer_model(harness.parse_args([]), official) is official  # untouched


def test_a_claude_run_never_sets_floors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    thresholds = tmp_path / "thresholds.json"  # a broken refusal must not reach the repo's file
    monkeypatch.setattr(harness, "THRESHOLDS", thresholds)
    report = {"config": {"primary": CLAUDE, "label": harness.CLAUDE_LABEL}, "metrics": {}}
    path = tmp_path / "claude.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(SystemExit, match="never set floors"):
        harness.set_floors(path)
    assert not thresholds.exists()


def test_a_claude_run_is_labelled_and_reported_beside_the_official_run() -> None:
    official = {
        "created_at": "2026-10-17T15:49:12+00:00",
        "config": {"primary": "gemini:gemini-3.5-flash-lite"},
        "metrics": {"answer": {"false_refusal": {"value": 0.096}}},
    }
    claude = {
        "suite": "answer", "split": "dev", "subset": "full",
        "config": {"primary": CLAUDE, "label": harness.CLAUDE_LABEL},
        "metrics": {"answer": {"false_refusal": {"value": 0.12}}},
    }  # fmt: skip
    lines = harness.side_by_side(claude, official)
    assert harness.CLAUDE_LABEL in lines[1] and official["created_at"] in lines[1]
    official_value, claude_value = (harness.shown("false_refusal", v) for v in (0.096, 0.12))
    assert any(official_value in line and claude_value in line for line in lines)
    assert harness.run_name(claude, "20261021T120000Z").endswith("-answer-dev-full-claude-primary")
