"""The eval call layer, judge replies, router scoring and the refusal sweep, on fakes: no model
is called."""

import asyncio
import json
from collections import Counter
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from evals import harness, judge
from evals.calibrate import FOLLOWUP_MODELS, draw, draw_followup, imported, spot_check
from evals.calls import Cache, Call, Recorded, Stop, patiently
from evals.harness import EvalSettings, answer_path, code_version, refusal_sweep, routed
from filinglens_core.errors import RateLimitedError
from filinglens_core.settings import ApiSettings
from filinglens_llm.providers import Completion


class Scripted:
    """A provider that replies from a script: each item a Completion or an error to raise."""

    name = "fake:model"

    def __init__(self, *script: Completion | Exception) -> None:
        self.script = list(script)
        self.calls = 0

    def _next(self) -> Completion:
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def complete(
        self, system: str, user: str, *, max_tokens: int, schema: Mapping[str, Any] | None = None
    ) -> Completion:
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
    }
    report = {"suite": "all", "split": "test", "subset": "full"} | {
        "judge_calibration": {"kappa": 0.84},
        "metrics": {"answer": answer, "retrieval": {"recall@10": entry(0.60, 0.45, 0.75)}},
    }
    saved = tmp_path / "report.json"
    saved.write_text(json.dumps(report), encoding="utf-8")
    harness.set_floors(saved)
    floors = json.loads(thresholds.read_text(encoding="utf-8"))
    assert floors["answer:test:full"] == {
        "numeric_exact_match": 0.9,  # min(low, target)
        "faithfulness": 0.9,  # counted: the run's judge was calibrated
        "false_refusal": 0.2,  # a ceiling: max(high, target)
        "ttft_p95_ms": 5250.0,  # a known miss: high x 1.5
        "input_tokens": 4800.0,  # meets its target: min(high x 1.5, target)
    }
    assert floors["retrieval:test:full"] == {"recall@10": 0.45}
    answer["ttft_p95_ms"] = entry(2800.0, 2400.0, 3000.0)
    saved.write_text(json.dumps(report), encoding="utf-8")
    harness.set_floors(saved)
    tightened = json.loads(thresholds.read_text(encoding="utf-8"))["answer:test:full"]
    assert tightened["ttft_p95_ms"] == 4500.0  # floors only tighten
    answer["ttft_p95_ms"] = entry(4000.0, 3600.0, 4400.0)
    saved.write_text(json.dumps(report), encoding="utf-8")
    harness.set_floors(saved)  # a slower run: past the floor, which stays
    kept = json.loads(thresholds.read_text(encoding="utf-8"))["answer:test:full"]
    assert kept["ttft_p95_ms"] == 4500.0


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
