"""
app/eval/calibration.py

Answers a question the ranking metrics in app/eval/metrics.py can't: is the
percentage shown next to a case card (`1 - cosine_distance`, see
app/services/case_match.py::to_match_score) a defensible number, or noise
that happens to be ordered correctly? Ranking metrics only need the order
to be right; a client reading "87% match" is trusting the *magnitude*.

Fed by deep-mode retrieval (every profile x every case gets a distance —
see eval_case_match_run.py), so this module operates on plain score/label
pairs, not on retrieved-top-k lists.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreDistribution:
    n: int
    min: float
    p10: float
    p25: float
    median: float
    p75: float
    p90: float
    max: float
    mean: float


def _percentile(sorted_values: Sequence[float], pct: float) -> float:
    """Linear-interpolation percentile (numpy's default "linear" method),
    on an already-sorted sequence. `pct` in [0, 100]."""
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return sorted_values[int(rank)]
    frac = rank - lo
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac


def score_distribution(scores: Sequence[float]) -> ScoreDistribution | None:
    """Summary stats for one label grade's set of match scores. Returns
    None for an empty input (a grade with zero judged pairs) rather than
    raising — the caller (report.py) prints "n/a" for that row."""
    if not scores:
        return None
    s = sorted(scores)
    return ScoreDistribution(
        n=len(s),
        min=s[0],
        p10=_percentile(s, 10),
        p25=_percentile(s, 25),
        median=_percentile(s, 50),
        p75=_percentile(s, 75),
        p90=_percentile(s, 90),
        max=s[-1],
        mean=sum(s) / len(s),
    )


def auc(positives: Sequence[float], negatives: Sequence[float]) -> float | None:
    """Rank-sum (Mann-Whitney) AUC: the probability that a random positive
    scores higher than a random negative, ties counting as half a win.
    Computed by direct pairwise comparison rather than rank-summing —
    the corpus is small (dozens of cases x labels), so O(n1*n2) is cheap
    and this avoids getting tie-handling in a rank-based formula wrong.

    Returns None when either side is empty (undefined) rather than raising
    or guessing 0.5 — a caller with zero negatives (e.g. every case
    labeled relevant) has nothing to measure, and the report should say so
    explicitly rather than print a number that looks meaningful.

    Interpretation (see also eval_case_match_run.py's report template):
      >= 0.80  -> the score is a defensible ordinal signal; consider
                  isotonic calibration so the % means something.
      0.65-0.80 -> order is informative, magnitude isn't; show a band,
                  not a raw percentage.
      < 0.65    -> the percentage is noise; show rank only.
    """
    if not positives or not negatives:
        return None
    wins = 0.0
    for p in positives:
        for n in negatives:
            if p > n:
                wins += 1.0
            elif p == n:
                wins += 0.5
    return wins / (len(positives) * len(negatives))


def overlap_fraction(scores: Sequence[float], threshold: float) -> float:
    """Fraction of `scores` at or above `threshold`. Used to answer e.g.
    "what fraction of label=0 pairs score above the label=2 median?" — a
    high overlap fraction is the concrete evidence behind an AUC verdict,
    the number worth quoting in the report alongside the AUC value."""
    if not scores:
        return 0.0
    return sum(1 for s in scores if s >= threshold) / len(scores)
