"""Hand-computed fixtures for app/eval/metrics.py.

A buggy nDCG or precision function would silently invalidate every number
the eval harness ever produces, so every value here is computed by hand in
the docstring/comment above each assertion — no test derives its expected
value from the function under test.
"""
from __future__ import annotations

import pytest

from app.eval.metrics import (
    dcg_at_k,
    gain,
    kendall_tau,
    ndcg_at_k,
    precision_at_k,
    precision_at_k_returned,
    reciprocal_rank,
    recall_at_k,
)

# Shared fixture used across several tests: a profile with 30 judged
# cases — two label=2 ("strong"), one label=1 ("some"), 27 label=0.
_ALL_LABELS = [2, 2, 1] + [0] * 27
# Retrieval returned 3 cases, in this label order:
_RANKED = [2, 0, 1]


class TestGain:
    def test_exponential_gain(self):
        assert gain(0) == 0.0
        assert gain(1) == 1.0
        assert gain(2) == 3.0


class TestPrecisionAtK:
    def test_divides_by_k(self):
        # top 3 = [2, 0, 1] -> 2 of 3 are relevant (label >= 1)
        assert precision_at_k(_RANKED, 3) == pytest.approx(2 / 3)

    def test_strong_threshold(self):
        # only the label=2 item (rank 1) counts at relevant_min=2
        assert precision_at_k(_RANKED, 3, relevant_min=2) == pytest.approx(1 / 3)

    def test_k_larger_than_returned_list_is_penalised(self):
        # only 3 items returned but k=5 -> still divides by 5
        assert precision_at_k(_RANKED, 5) == pytest.approx(2 / 5)

    def test_empty_ranked_list(self):
        assert precision_at_k([], 3) == 0.0

    def test_k_zero(self):
        assert precision_at_k(_RANKED, 0) == 0.0


class TestPrecisionAtKReturned:
    def test_divides_by_returned_count_not_k(self):
        # k=5 but only 3 returned -> divide by 3, not 5
        assert precision_at_k_returned(_RANKED, 5) == pytest.approx(2 / 3)

    def test_matches_precision_at_k_when_full(self):
        assert precision_at_k_returned(_RANKED, 3) == pytest.approx(2 / 3)

    def test_empty_ranked_list_returns_zero_not_divide_by_zero(self):
        assert precision_at_k_returned([], 5) == 0.0


class TestRecallAtK:
    def test_any_relevance(self):
        # 2 of 3 total relevant (2,2,1 -> 3 relevant total) found in top 3
        assert recall_at_k(_RANKED, 3, total_relevant=3) == pytest.approx(2 / 3)

    def test_strong_relevance(self):
        # 1 of 2 total strong (label=2) items found in top 3
        assert recall_at_k(_RANKED, 3, total_relevant=2, relevant_min=2) == pytest.approx(0.5)

    def test_zero_total_relevant_returns_zero(self):
        assert recall_at_k(_RANKED, 3, total_relevant=0) == 0.0


class TestReciprocalRank:
    def test_first_item_relevant(self):
        assert reciprocal_rank([2, 0, 1]) == 1.0

    def test_second_item_relevant(self):
        assert reciprocal_rank([0, 2, 1]) == 0.5

    def test_none_relevant(self):
        assert reciprocal_rank([0, 0, 0]) == 0.0

    def test_relevant_at_rank_five(self):
        assert reciprocal_rank([0, 0, 0, 0, 1]) == pytest.approx(0.2)

    def test_strong_threshold_skips_weak_hit(self):
        # label=1 at rank 1 doesn't count when relevant_min=2; label=2 at rank 3 does
        assert reciprocal_rank([1, 0, 2], relevant_min=2) == pytest.approx(1 / 3)


class TestDcgAtK:
    def test_hand_computed(self):
        # gains [3, 0, 1]: 3/log2(2) + 0/log2(3) + 1/log2(4) = 3 + 0 + 0.5 = 3.5
        assert dcg_at_k([3, 0, 1], 3) == pytest.approx(3.5)

    def test_truncates_to_k(self):
        assert dcg_at_k([3, 0, 1, 100], 3) == pytest.approx(3.5)


class TestNdcgAtK:
    def test_hand_computed(self):
        # actual gains (from _RANKED=[2,0,1]): [3, 0, 1] -> DCG = 3.5 (above)
        # ideal gains (from _ALL_LABELS sorted desc, top 3 labels [2,2,1]):
        #   [3, 3, 1] -> IDCG = 3/log2(2) + 3/log2(3) + 1/log2(4)
        #              = 3 + 3/1.5849625... + 0.5 = 3 + 1.8927892607143... + 0.5
        #              = 5.3927892607143...
        # nDCG@3 = 3.5 / 5.3927892607143... = 0.6490147919365...
        result = ndcg_at_k(_RANKED, 3, all_labels=_ALL_LABELS)
        assert result == pytest.approx(0.6490147919365, rel=1e-6)

    def test_idcg_zero_returns_zero(self):
        # no relevant items exist at all for this profile
        assert ndcg_at_k([0, 0, 0], 3, all_labels=[0] * 30) == 0.0

    def test_single_relevant_item_at_rank_five(self):
        # ranked = [0,0,0,0,1], all_labels has exactly one label=1 (rest 0)
        # IDCG@5 with only one relevant item = gain(1)/log2(2) = 1/1 = 1.0
        # DCG@5 = gain(1) at rank 5 = 1/log2(6) = 1/2.5849625... = 0.3868528...
        all_labels = [1] + [0] * 29
        result = ndcg_at_k([0, 0, 0, 0, 1], 5, all_labels=all_labels)
        assert result == pytest.approx(0.386853, rel=1e-5)

    def test_k_larger_than_all_labels_available(self):
        # k=10 but only 3 labels exist total -> ideal list is just those 3
        result = ndcg_at_k([1], 10, all_labels=[1, 0, 0])
        # IDCG = gain(1)/log2(2) = 1.0 ; DCG (only 1 item ranked) = 1/log2(2) = 1.0
        assert result == pytest.approx(1.0)


class TestKendallTau:
    def test_identical_order_is_fully_concordant(self):
        assert kendall_tau(["a", "b", "c"], ["a", "b", "c"]) == pytest.approx(1.0)

    def test_fully_reversed_order(self):
        assert kendall_tau(["a", "b", "c"], ["c", "b", "a"]) == pytest.approx(-1.0)

    def test_one_swap_out_of_three_pairs(self):
        # a,b,c vs a,c,b: pairs (a,b) concordant, (a,c) concordant, (b,c) discordant
        # tau = (2 - 1) / 3 = 1/3
        assert kendall_tau(["a", "b", "c"], ["a", "c", "b"]) == pytest.approx(1 / 3)

    def test_mismatched_item_sets_raises(self):
        with pytest.raises(ValueError):
            kendall_tau(["a", "b", "c"], ["a", "b", "d"])

    def test_single_item_is_trivially_concordant(self):
        assert kendall_tau(["a"], ["a"]) == 1.0

    def test_empty_is_trivially_concordant(self):
        assert kendall_tau([], []) == 1.0
