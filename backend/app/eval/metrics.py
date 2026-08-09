"""
app/eval/metrics.py

Pure ranking-quality metrics for the case-match eval harness. No DB, no
I/O — every function takes plain Python sequences so it can be tested with
hand-computed fixtures (see tests/unit/test_retrieval_metrics.py) and
reused identically by both the "production settings" and "deep pool"
report sections in backend/scripts/eval_case_match_run.py.

Convention used throughout: `ranked` is the list of relevance *labels*
(0/1/2) in retrieved-rank order — i.e. `[labels_by_filename[f] for f in
retrieved_filenames]`. Callers translate filenames to labels before calling
in; these functions never see a filename.

`relevant_min` selects the grading threshold: 1 = "any relevance counts",
2 = "strong recall" — did we surface a case a consultant would actually
pitch? Every metric is meant to be reported at both thresholds; see
backend/scripts/eval_case_match_run.py's report template.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

# ---------------------------------------------------------------------------
# Gain
# ---------------------------------------------------------------------------


def gain(label: int) -> float:
    """Exponential gain used by (n)DCG: label 0/1/2 -> gain 0/1/3. Makes a
    label=2 case worth 3x a label=1 case, not 2x — a consultant treats
    "strong" and "somewhat" matches as qualitatively different, not evenly
    spaced."""
    return float(2**label - 1)


# ---------------------------------------------------------------------------
# Precision / recall / reciprocal rank
# ---------------------------------------------------------------------------


def precision_at_k(ranked: Sequence[int], k: int, *, relevant_min: int = 1) -> float:
    """Relevant items in the top k, divided by k.

    Divides by k even when fewer than k items were returned — a client who
    asked for (implicitly, via the UI) five cards and got three should have
    that shortfall counted against precision, not excused. See
    precision_at_k_returned for the excusing variant; report both."""
    if k <= 0:
        return 0.0
    hits = sum(1 for label in ranked[:k] if label >= relevant_min)
    return hits / k


def precision_at_k_returned(ranked: Sequence[int], k: int, *, relevant_min: int = 1) -> float:
    """Relevant items in the top k, divided by min(k, len(ranked)) — the
    number actually returned. Excuses truncation caused by the chunk
    budget (see rag_top_k); pair with precision_at_k, which does not."""
    n = min(k, len(ranked))
    if n <= 0:
        return 0.0
    hits = sum(1 for label in ranked[:k] if label >= relevant_min)
    return hits / n


def recall_at_k(
    ranked: Sequence[int], k: int, *, total_relevant: int, relevant_min: int = 1
) -> float:
    """Relevant items in the top k, divided by the total number of relevant
    items that exist for this profile (from the full label set, not just
    what was retrieved). 0.0 when total_relevant == 0 — there is nothing to
    recall, and this profile should be excluded from a "mean over profiles
    with >=1 relevant" aggregate rather than silently averaged in as 0."""
    if total_relevant <= 0:
        return 0.0
    hits = sum(1 for label in ranked[:k] if label >= relevant_min)
    return hits / total_relevant


def reciprocal_rank(ranked: Sequence[int], *, relevant_min: int = 1) -> float:
    """1 / (1-based rank of the first relevant item), or 0.0 if none of
    `ranked` meets `relevant_min`."""
    for i, label in enumerate(ranked):
        if label >= relevant_min:
            return 1.0 / (i + 1)
    return 0.0


# ---------------------------------------------------------------------------
# (n)DCG
# ---------------------------------------------------------------------------


def dcg_at_k(gains: Sequence[float], k: int) -> float:
    """Discounted cumulative gain over the first k entries of `gains`
    (already in ranked order). Works whether `gains` is longer, shorter,
    or exactly k long."""
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains[:k]))


def ndcg_at_k(ranked: Sequence[int], k: int, *, all_labels: Sequence[int]) -> float:
    """Normalised DCG@k. The ideal ordering (IDCG) is built from
    `all_labels` — every label judged for this profile, not just the ones
    retrieval happened to surface — so a retriever that misses a strong
    case entirely is penalised exactly as much as one that ranks it last.

    Returns 0.0 when IDCG is 0 (no relevant items exist at all for this
    profile); as with recall_at_k, exclude such profiles from a
    "mean over profiles with >=1 relevant" aggregate."""
    actual_gains = [gain(label) for label in ranked[:k]]
    ideal_gains = sorted((gain(label) for label in all_labels), reverse=True)[:k]
    idcg = dcg_at_k(ideal_gains, k)
    if idcg == 0.0:
        return 0.0
    return dcg_at_k(actual_gains, k) / idcg


# ---------------------------------------------------------------------------
# Ranking agreement (sensitivity / contrast-pair diagnostic)
# ---------------------------------------------------------------------------


def kendall_tau(rank_a: Sequence[str], rank_b: Sequence[str]) -> float:
    """Kendall's tau between two rankings of the *same* item set (e.g. two
    contrast profiles' deep-mode filename orderings). +1.0 = identical
    order, -1.0 = fully reversed, 0.0 = no correlation.

    Used to answer "does changing one intake field move the ranking at
    all?" — see backend/eval/case_match/profiles.json's contrast-pair
    profiles and eval_case_match_run.py's sensitivity report section.
    Both sequences must contain exactly the same items (order may differ);
    a mismatched pair is a caller bug, not a data condition to handle
    quietly, so this raises rather than silently truncating.
    """
    items_a, items_b = set(rank_a), set(rank_b)
    if items_a != items_b:
        raise ValueError(
            f"kendall_tau requires the same item set in both rankings; "
            f"only in rank_a: {items_a - items_b}, only in rank_b: {items_b - items_a}"
        )
    n = len(rank_a)
    if n < 2:
        return 1.0  # trivially concordant — nothing to disagree about

    pos_a = {item: i for i, item in enumerate(rank_a)}
    pos_b = {item: i for i, item in enumerate(rank_b)}
    items = list(rank_a)

    concordant = 0
    discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            da = pos_a[items[i]] - pos_a[items[j]]
            db = pos_b[items[i]] - pos_b[items[j]]
            if da * db > 0:
                concordant += 1
            elif da * db < 0:
                discordant += 1
            # da or db == 0 is impossible: positions within one ranking are unique

    total_pairs = n * (n - 1) / 2
    return (concordant - discordant) / total_pairs
