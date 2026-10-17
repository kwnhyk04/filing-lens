"""Eval statistics without numpy: ranking metrics, exact match, percentiles, Cohen's kappa,
percentile bootstrap intervals and the floor rule (docs/memory.md, step 6b)."""

import math
import random
import re
from collections.abc import Callable, Sequence
from decimal import Decimal

from filinglens_llm.validate import amounts_match, find_amounts, numbers_in

RESAMPLES = 10_000
SEED = 20261016  # fixed, so a rerun gives the same interval
NUMBERED = re.compile(r"\[\d+\]")  # an answer's citation markers, not amounts


def recall_at(ranked: Sequence[str], gold: set[str], k: int = 10) -> float:
    """Gold passages in the top k over min(gold count, k)."""
    return len(gold.intersection(ranked[:k])) / min(len(gold), k)


def mrr_at(ranked: Sequence[str], gold: set[str], k: int = 10) -> float:
    """1 / rank of the first gold passage in the top k; 0 when none is there."""
    return next((1 / rank for rank, item in enumerate(ranked[:k], 1) if item in gold), 0.0)


def ndcg_at(ranked: Sequence[str], gold: set[str], k: int = 10) -> float:
    """Binary gains; the ideal ranking puts min(gold count, k) gold passages first."""
    dcg = sum(1 / math.log2(rank + 1) for rank, item in enumerate(ranked[:k], 1) if item in gold)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(len(gold), k) + 1))
    return dcg / ideal


def judged_at(ranked: Sequence[str], judged: set[str], k: int = 10) -> float:
    """Share of the top k that carries a label, gold or not."""
    top = ranked[:k]
    return sum(item in judged for item in top) / len(top) if top else 0.0


def states_amount(text: str, value: Decimal) -> bool:
    """Whether answer text states `value` within 0.5%, compared in absolute values, so "a net
    loss of $1.2 billion" matches -1.2e9."""
    plain = NUMBERED.sub("", text)
    found = [amount for amount, percent in find_amounts(plain) if not percent] + numbers_in(plain)
    return any(amounts_match(abs(amount), abs(value)) for amount in found)


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def pooled(pairs: Sequence[tuple[float, float]]) -> float:
    """Sum of numerators over sum of denominators, for (hits, total) per question."""
    return sum(n for n, _ in pairs) / sum(d for _, d in pairs)


def percentile(values: Sequence[float], p: float) -> float:
    """Nearest rank: the smallest value with at least p% of the values at or below it."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)]


def cohen_kappa(pairs: Sequence[tuple[bool, bool]]) -> float:
    """Agreement of two raters on yes/no labels beyond chance; 1.0 when both always agree."""
    n = len(pairs)
    observed = sum(a == b for a, b in pairs) / n
    first, second = sum(a for a, _ in pairs) / n, sum(b for _, b in pairs) / n
    chance = first * second + (1 - first) * (1 - second)
    return 1.0 if chance == 1 else (observed - chance) / (1 - chance)


def bootstrap[T](
    items: Sequence[T], statistic: Callable[[Sequence[T]], float], resamples: int = RESAMPLES
) -> tuple[float, float]:
    """95% percentile interval of `statistic` over `items` resampled with replacement.

    Resampling per-question differences gives the paired bootstrap of two configurations.
    """
    rng = random.Random(SEED)  # noqa: S311 - resampling, not security
    values = sorted(
        statistic([items[rng.randrange(len(items))] for _ in items]) for _ in range(resamples)
    )
    return values[int(0.025 * resamples)], values[int(0.975 * resamples) - 1]


def floor(kind: str, value: float, low: float, high: float, target: float) -> float:
    """The floor rule. Accuracy: min(low, target). False refusal: a ceiling of max(high,
    target). Efficiency meeting its target: min(high x 1.5, target); missing it: high x 1.5,
    so a known miss doesn't fail every run. Cost as billed: 0 on the free setup, which bills
    nothing; a setup that spends credits (Claude) gets the efficiency rule."""
    if kind == "accuracy":
        return min(low, target)
    if kind == "rate":
        return max(high, target)
    if kind == "billed" and value == 0:
        return 0.0
    return min(high * 1.5, target) if value <= target else high * 1.5


def deterministic_floor(value: float, n: int, target: float) -> float:
    """Retrieval accuracy (user rule, 2026-10-17): the measured value less one question's share,
    capped at the target. Retrieval calls no model, so the same code on the same corpus gives
    the same numbers; a bootstrap lower bound reflects only which questions the set holds and
    would let a real drop pass, while one share still tolerates one near-tie flipping."""
    return min(value - 1 / n, target)


def broken(kind: str, value: float, limit: float) -> bool:
    """Whether a value breaks its floor (accuracy) or its ceiling (everything else)."""
    return value < limit if kind == "accuracy" else value > limit


def tighter(kind: str, old: float | None, new: float) -> float:
    """Floors only tighten: an accuracy floor only rises, a ceiling only falls."""
    if old is None:
        return new
    return max(old, new) if kind == "accuracy" else min(old, new)
