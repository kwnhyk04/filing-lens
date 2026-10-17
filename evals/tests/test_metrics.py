import math
from decimal import Decimal

import pytest

from evals.metrics import (
    bootstrap,
    broken,
    cohen_kappa,
    deterministic_floor,
    floor,
    mrr_at,
    ndcg_at,
    percentile,
    recall_at,
    states_amount,
    tighter,
)


def test_kappa_matches_the_textbook_table() -> None:
    # 20 yes/yes, 5 yes/no, 10 no/yes, 15 no/no: observed 0.7, chance 0.5, kappa 0.4.
    pairs = [(True, True)] * 20 + [(True, False)] * 5 + [(False, True)] * 10 + [(False, False)] * 15
    assert abs(cohen_kappa(pairs) - 0.4) < 1e-12
    assert cohen_kappa([(True, True), (False, False)]) == 1.0
    assert cohen_kappa([(False, False)] * 3) == 1.0  # one class, always agreeing


def test_bootstrap_is_repeatable_and_brackets_the_estimate() -> None:
    pairs = [(True, True)] * 20 + [(True, False)] * 5 + [(False, True)] * 10 + [(False, False)] * 15
    low, high = bootstrap(pairs, cohen_kappa, resamples=2_000)
    assert (low, high) == bootstrap(pairs, cohen_kappa, resamples=2_000)
    assert low < cohen_kappa(pairs) < high
    assert bootstrap([3.0] * 5, lambda xs: sum(xs) / len(xs), resamples=100) == (3.0, 3.0)


def test_ranking_metrics_cap_at_the_gold_count() -> None:
    ranked, gold = ["a", "x", "b", "y"], {"a", "b", "c"}
    assert recall_at(ranked, gold) == 2 / 3
    assert mrr_at(["x", "a"], gold) == 0.5
    assert mrr_at(["x", "y"], gold) == 0.0
    ideal = 1 + 1 / math.log2(3) + 1 / math.log2(4)
    assert ndcg_at(ranked, gold) == pytest.approx((1 + 1 / math.log2(4)) / ideal)
    twelve = {str(n) for n in range(12)}  # 10 of 12 gold passages fill a perfect top 10
    assert recall_at([str(n) for n in range(10)], twelve) == 1.0
    assert ndcg_at([str(n) for n in range(10)], twelve) == pytest.approx(1.0)


def test_a_retrieval_floor_allows_one_question_less_than_measured() -> None:
    assert deterministic_floor(0.613, 14, 0.90) == pytest.approx(0.613 - 1 / 14)
    assert deterministic_floor(0.98, 14, 0.90) == 0.90  # capped at the target


def test_the_floor_rule() -> None:
    assert floor("accuracy", 0.95, 0.90, 0.98, 0.92) == 0.90  # the lower bound
    assert floor("accuracy", 0.99, 0.96, 1.0, 0.92) == 0.92  # capped at the target
    assert floor("rate", 0.03, 0.01, 0.07, 0.05) == 0.07  # false refusal: a ceiling
    assert floor("rate", 0.01, 0.0, 0.03, 0.05) == 0.05
    assert floor("efficiency", 3000, 2600, 3500, 2000) == 5250  # TTFT p95 misses 2.0 s: no cap
    assert floor("efficiency", 100, 90, 120, 250) == 180  # meets: 1.5 x the upper bound
    assert floor("efficiency", 200, 180, 220, 250) == 250  # meets, capped at the target
    assert floor("billed", 0.0, 0.0, 0.0, 0.015) == 0.0
    assert broken("accuracy", 0.89, 0.90) and not broken("accuracy", 0.90, 0.90)
    assert broken("efficiency", 5300, 5250) and not broken("rate", 0.05, 0.07)
    assert tighter("accuracy", 0.90, 0.85) == 0.90  # floors never loosen
    assert tighter("efficiency", 5250, 6000) == 5250
    assert tighter("rate", None, 0.07) == 0.07


def test_exact_match_reads_rounded_amounts_and_ignores_signs() -> None:
    revenue = Decimal("416161000000")
    assert states_amount("Apple's net sales were $416.2 billion in fiscal 2025 [1].", revenue)
    assert states_amount("Diluted earnings per share were $6.08 [1].", Decimal("6.08"))
    assert states_amount("It reported a net loss of $1.2 billion [2].", Decimal("-1200000000"))
    assert not states_amount("Net sales were $391.0 billion [1].", revenue)
    assert not states_amount("Revenue grew [1].", Decimal("1"))  # a marker is not an amount


def test_percentile_is_the_nearest_rank() -> None:
    values = [float(n) for n in range(1, 21)]
    assert percentile(values, 50) == 10.0
    assert percentile(values, 95) == 19.0
    assert percentile([7.0], 95) == 7.0
