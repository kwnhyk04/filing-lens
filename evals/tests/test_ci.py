"""--ci: latency reported but not gated, errored questions as plain failures, and only a quota
or rate limit stop saying to rerun after the quota resets. No model or database is touched."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from evals import harness
from evals.calls import Stop

RUN = "answer eval (dev ci)"


def entry(value: float | None) -> dict[str, Any]:
    return {"value": value, "low": value, "high": value, "n": 4}


def report(**metrics: float | None) -> dict[str, Any]:
    return {
        "suite": "retrieval", "split": "dev", "subset": "full", "created_at": "now", "ci": True,
        "golden": {"version": "v1", "manifest_sha256": "0" * 64, "as_of": "2026-10-16"},
        "index": {"chunks": 3, "model": "m"},
        "config": {
            "router": "r", "primary": "gemini:g", "thinking": "minimal", "judge": None,
            "reranker": "x", "rerank_candidates": 50, "rerank_max_tokens": 512,
            "min_relevance": -3.0,
        },
        "metrics": {"retrieval": {name: entry(value) for name, value in metrics.items()}},
        "notes": [], "calls": {},
    }  # fmt: skip


@pytest.fixture
def floors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "thresholds.json"
    path.write_text(json.dumps({"retrieval:dev:full": {"recall@10": 0.5, "retrieval_p95_ms": 100}}))
    monkeypatch.setattr(harness, "THRESHOLDS", path)
    return path


def test_ci_reports_latency_without_gating_it(floors: Path) -> None:
    slow = report(**{"recall@10": 0.6, "retrieval_p95_ms": 900.0})
    assert harness.apply_floors(slow, False, True, latency=False) == ([], 1, 1)
    past, checked, unchecked = harness.apply_floors(slow, False, True)
    assert len(past) == 1 and "retrieval_p95_ms" in past[0] and (checked, unchecked) == (2, 0)
    assert "| 900 ms | 900 ms to 900 ms | 4 | not gated |" in harness.markdown(slow)
    assert "not gated" not in harness.markdown(slow | {"ci": False})


def test_ci_stops_before_any_call_when_the_setup_has_no_floors(floors: Path) -> None:
    args = argparse.Namespace(suite="all", split="dev", subset="full")
    assert harness.unfloored(args, "gemini:g") == ["answer:dev:full:gemini:g"]


def test_errored_questions_fail_plainly_with_their_reasons() -> None:
    records = {
        "answer": [
            {"id": "x01", "outcome": "answered", "judge": {"error": "reply did not parse"}},
            {"id": "x02", "outcome": "error", "error": "UpstreamError: gemini answered 503"},
            {"id": "x03", "outcome": "refused"},
        ]
    }
    failed = harness.errored(records)
    assert failed == ["x01 (judge): reply did not parse", "x02: UpstreamError: gemini answered 503"]
    code, header = harness.verdict(RUN, [], failed, 9, 0)
    assert code == 4 and header.startswith("**FAILED**") and "gemini answered 503" in header
    assert "quota resets" not in header and "not a quota stop" in header


def test_the_verdict_passes_only_when_some_floor_was_checked() -> None:
    assert harness.verdict(RUN, ["k recall@10: 0.1 is past 0.5"], [], 9, 0)[0] == 1
    assert harness.verdict(RUN, [], [], 0, 4)[0] == 4
    code, header = harness.verdict(RUN, [], [], 9, 2)
    assert code == 0 and header.startswith("**PASS**") and "does not gate" in header


def test_only_a_quota_or_rate_limit_stop_says_to_rerun_after_the_quota_resets() -> None:
    quota = harness.stopped(RUN, Stop(2, "Quota or rate limit: groq is rate limited (429)."))
    assert quota.startswith("**INCOMPLETE**") and "Rerun this job after the quota resets" in quota
    for stop in (Stop(4, "x01: groq refused the API key (401)."), Stop(3, "Golden set changed.")):
        header = harness.stopped(RUN, stop)
        assert header.startswith("**FAILED**") and str(stop) in header and "quota" not in header


@pytest.mark.parametrize(
    ("code", "title", "word"),
    [(2, "Eval incomplete (quota or rate limit)", "INCOMPLETE"), (4, "Eval failed", "FAILED")],
)
def test_a_stopped_ci_run_writes_its_verdict_and_an_error_annotation(
    code: int,
    title: str,
    word: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def stops(args: Any) -> int:
        raise Stop(code, "the reason")

    monkeypatch.setattr(harness, "CACHE", tmp_path)
    monkeypatch.setattr(harness, "evaluate", stops)
    monkeypatch.setattr(sys, "argv", ["harness", "--suite", "answer", "--subset", "ci", "--ci"])
    with pytest.raises(SystemExit) as exited:
        harness.main()
    assert exited.value.code == code
    assert f"::error title={title}::{word} {RUN}: the reason" in capsys.readouterr().out
    assert (tmp_path / "ci" / "answer-dev-ci.md").read_text().startswith(f"**{word}** {RUN}")


def test_a_ci_setup_error_fails_with_its_reason_as_exit_4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def misconfigured(args: Any) -> int:
        raise SystemExit("Invalid configuration: LLM_PRIMARY needs GEMINI_API_KEY")

    monkeypatch.setattr(harness, "CACHE", tmp_path)
    monkeypatch.setattr(harness, "evaluate", misconfigured)
    monkeypatch.setattr(sys, "argv", ["harness", "--suite", "answer", "--subset", "ci", "--ci"])
    with pytest.raises(SystemExit) as exited:
        harness.main()
    assert exited.value.code == 4
    status = (tmp_path / "ci" / "answer-dev-ci.md").read_text()
    assert status.startswith(f"**FAILED** {RUN}: Invalid configuration") and "quota" not in status
