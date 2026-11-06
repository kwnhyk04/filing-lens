"""A metric passes or fails only where its whole 95% interval clears or misses its target (E4)."""

from typing import Any

import pytest

from evals import harness


def status(name: str, value: float, low: float | None, high: float | None) -> str:
    metrics: dict[str, dict[str, Any]] = {name: {"value": value, "low": low, "high": high}}
    harness.statuses(metrics, judge_ok=True)
    return metrics[name]["status"]


@pytest.mark.parametrize(
    ("name", "value", "low", "high", "expected"),
    [
        ("numeric_exact_match", 1.0, 0.758, 1.0, "inconclusive"),  # 12 of 12 against 0.92
        ("correct_refusal", 1.0, 0.722, 1.0, "inconclusive"),  # 10 of 10 against 0.90
        ("false_refusal", 0.044, 0.012, 0.148, "inconclusive"),  # 2 of 45 against 5%
        ("false_refusal", 0.133, 0.063, 0.262, "fail"),  # the whole interval misses 5%
        ("citation_precision", 0.993, 0.977, 1.0, "pass"),  # the whole interval clears 0.95
        ("citation_precision", 0.944, 0.833, 1.0, "inconclusive"),  # a miss it cannot prove
        ("recall@10", 0.596, 0.490, 0.698, "fail"),
        ("ttft_p50_ms", 2414.0, 2235.0, 2504.0, "fail"),
        ("cost_usd", 0.0012, 0.0010, 0.0014, "pass"),
        ("cost_usd", 0.0012, None, None, "pass"),  # no interval: the point decides
        ("ttft_p50_ms", 2414.0, None, None, "fail"),
    ],
)
def test_a_status_reads_the_interval_not_the_point(
    name: str, value: float, low: float | None, high: float | None, expected: str
) -> None:
    assert status(name, value, low, high) == expected
