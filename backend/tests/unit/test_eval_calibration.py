"""Hand-computed fixtures for app/eval/calibration.py."""
from __future__ import annotations

import pytest

from app.eval.calibration import auc, overlap_fraction, score_distribution


class TestAuc:
    def test_hand_computed_rank_sum(self):
        # positives=[0.50, 0.40], negatives=[0.45, 0.30, 0.20]
        # pairwise: (.50>.45)=1 (.50>.30)=1 (.50>.20)=1 (.40>.45)=0 (.40>.30)=1 (.40>.20)=1
        # 5 of 6 pairs correctly ordered -> AUC = 5/6
        result = auc([0.50, 0.40], [0.45, 0.30, 0.20])
        assert result == pytest.approx(5 / 6, rel=1e-5)

    def test_tie_counts_as_half(self):
        assert auc([0.4], [0.4]) == pytest.approx(0.5)

    def test_perfect_separation(self):
        assert auc([0.9, 0.8], [0.2, 0.1]) == pytest.approx(1.0)

    def test_fully_reversed(self):
        assert auc([0.1, 0.2], [0.8, 0.9]) == pytest.approx(0.0)

    def test_empty_positives_is_undefined(self):
        assert auc([], [0.5]) is None

    def test_empty_negatives_is_undefined(self):
        assert auc([0.5], []) is None


class TestScoreDistribution:
    def test_empty_is_none(self):
        assert score_distribution([]) is None

    def test_basic_stats(self):
        dist = score_distribution([0.1, 0.2, 0.3, 0.4, 0.5])
        assert dist.n == 5
        assert dist.min == pytest.approx(0.1)
        assert dist.max == pytest.approx(0.5)
        assert dist.median == pytest.approx(0.3)
        assert dist.mean == pytest.approx(0.3)

    def test_single_value(self):
        dist = score_distribution([0.42])
        assert dist.n == 1
        assert dist.min == dist.max == dist.median == dist.mean == pytest.approx(0.42)


class TestOverlapFraction:
    def test_fraction_at_or_above_threshold(self):
        assert overlap_fraction([0.1, 0.5, 0.6, 0.9], threshold=0.5) == pytest.approx(0.75)

    def test_empty_scores_is_zero(self):
        assert overlap_fraction([], threshold=0.5) == 0.0

    def test_nothing_above_threshold(self):
        assert overlap_fraction([0.1, 0.2], threshold=0.9) == 0.0
