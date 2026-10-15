"""Reciprocal rank fusion with k = 60: hand-computed scores, tie order, properties of any input."""

from itertools import pairwise

import pytest
from hypothesis import given
from hypothesis import strategies as st

from filinglens_retrieval import RRF_K, reciprocal_rank_fusion

# Up to four retrievers' rankings; a ranking lists an id at most once.
RANKINGS = st.lists(st.lists(st.sampled_from("abcdefghij"), unique=True), max_size=4)


def test_scores_sum_reciprocal_ranks_with_k_60() -> None:
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["c", "a"]])
    assert RRF_K == 60
    assert [item for item, _ in fused] == ["a", "c", "b"]
    scores = dict(fused)
    assert scores["a"] == pytest.approx(1 / 61 + 1 / 62)
    assert scores["c"] == pytest.approx(1 / 63 + 1 / 61)
    assert scores["b"] == pytest.approx(1 / 62)
    assert reciprocal_rank_fusion([]) == []


def test_equal_scores_go_by_id() -> None:
    # x and y both rank 1st, 2nd and 3rd once, summed in different orders.
    fused = reciprocal_rank_fusion([["x", "y"], ["z", "x", "y"], ["y", "w", "x"]])
    assert [item for item, _ in fused] == ["x", "y", "z", "w"]
    assert fused[0][1] == fused[1][1]


@given(RANKINGS, st.data())
def test_every_id_once_best_first_and_list_order_never_matters(
    rankings: list[list[str]], data: st.DataObject
) -> None:
    fused = reciprocal_rank_fusion(rankings)
    assert sorted(item for item, _ in fused) == sorted({i for ranking in rankings for i in ranking})
    assert all((-a[1], a[0]) < (-b[1], b[0]) for a, b in pairwise(fused))
    assert all(0 < score <= len(rankings) / (RRF_K + 1) for _, score in fused)
    assert reciprocal_rank_fusion(data.draw(st.permutations(rankings))) == fused
    if rankings:  # an id first in every list wins
        assert reciprocal_rank_fusion([["*", *ranking] for ranking in rankings])[0][0] == "*"
