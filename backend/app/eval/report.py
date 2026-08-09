"""
app/eval/report.py

Turns retrieval results (already joined against consultant labels) into
the case-match eval report: overall metrics under both "production
settings" (what the client sees) and "deep pool" (what the retriever
could reach), a per-profile breakdown, a severity-ranked worst-failures
list, the contrast-pair sensitivity check, and the score-calibration
verdict. Pure computation and string rendering — no DB, no I/O; fed by
backend/scripts/eval_case_match_run.py, which does the DB work and builds
the ProfileResult inputs.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass

from app.eval import metrics as m
from app.eval.calibration import ScoreDistribution, auc, overlap_fraction, score_distribution

K_VALUES: tuple[int, ...] = (1, 3, 5)


# ---------------------------------------------------------------------------
# Inputs — built by eval_case_match_run.py from case_match.match_cases() +
# app.eval.goldens.GoldenLabels
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProfileResult:
    """One profile's retrieval result in one mode, joined against labels."""

    profile_id: str
    label_th: str
    ranked_filenames: list[str]  # retrieved order (production: <=5ish; deep: full pool)
    ranked_labels: list[int]  # labels in the same order as ranked_filenames
    all_labels: list[int]  # every label for this profile's corpus (judged + defaulted-0)
    total_relevant: int  # count of all_labels >= 1
    total_strong: int  # count of all_labels >= 2
    judged_count: int  # (profile, filename) pairs actually judged (not defaulted)
    corpus_size: int  # total case files eligible for this profile


# ---------------------------------------------------------------------------
# Per-profile metrics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProfileMetricRow:
    profile_id: str
    label_th: str
    n_returned: int
    precision_at_k: dict[int, float]
    precision_at_k_returned: dict[int, float]
    recall_at_k: dict[int, float]
    strong_recall_at_k: dict[int, float]
    mrr: float
    strong_mrr: float
    ndcg_at_k: dict[int, float]
    total_relevant: int
    total_strong: int
    judged_coverage: float
    top1_filename: str | None
    top1_label: int | None


def compute_profile_metrics(
    result: ProfileResult, *, k_values: tuple[int, ...] = K_VALUES
) -> ProfileMetricRow:
    ranked = result.ranked_labels
    return ProfileMetricRow(
        profile_id=result.profile_id,
        label_th=result.label_th,
        n_returned=len(ranked),
        precision_at_k={k: m.precision_at_k(ranked, k) for k in k_values},
        precision_at_k_returned={k: m.precision_at_k_returned(ranked, k) for k in k_values},
        recall_at_k={
            k: m.recall_at_k(ranked, k, total_relevant=result.total_relevant) for k in k_values
        },
        strong_recall_at_k={
            k: m.recall_at_k(ranked, k, total_relevant=result.total_strong, relevant_min=2)
            for k in k_values
        },
        mrr=m.reciprocal_rank(ranked),
        strong_mrr=m.reciprocal_rank(ranked, relevant_min=2),
        ndcg_at_k={k: m.ndcg_at_k(ranked, k, all_labels=result.all_labels) for k in k_values},
        total_relevant=result.total_relevant,
        total_strong=result.total_strong,
        judged_coverage=(result.judged_count / result.corpus_size) if result.corpus_size else 0.0,
        top1_filename=result.ranked_filenames[0] if result.ranked_filenames else None,
        top1_label=ranked[0] if ranked else None,
    )


# ---------------------------------------------------------------------------
# Aggregate metrics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AggregateMetrics:
    n_profiles: int
    n_profiles_with_relevant: int
    n_profiles_with_strong: int
    mean_precision_at_k: dict[int, float]
    mean_precision_at_k_returned: dict[int, float]
    mean_recall_at_k: dict[int, float]  # over profiles with total_relevant > 0
    mean_strong_recall_at_k: dict[int, float]  # over profiles with total_strong > 0
    mean_mrr: float
    mean_ndcg_at_k: dict[int, float]  # over profiles with total_relevant > 0
    mean_n_returned: float


def _mean(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def aggregate(
    rows: Sequence[ProfileMetricRow], *, k_values: tuple[int, ...] = K_VALUES
) -> AggregateMetrics:
    with_relevant = [r for r in rows if r.total_relevant > 0]
    with_strong = [r for r in rows if r.total_strong > 0]
    return AggregateMetrics(
        n_profiles=len(rows),
        n_profiles_with_relevant=len(with_relevant),
        n_profiles_with_strong=len(with_strong),
        mean_precision_at_k={k: _mean(r.precision_at_k[k] for r in rows) for k in k_values},
        mean_precision_at_k_returned={
            k: _mean(r.precision_at_k_returned[k] for r in rows) for k in k_values
        },
        mean_recall_at_k={k: _mean(r.recall_at_k[k] for r in with_relevant) for k in k_values},
        mean_strong_recall_at_k={
            k: _mean(r.strong_recall_at_k[k] for r in with_strong) for k in k_values
        },
        mean_mrr=_mean(r.mrr for r in rows),
        mean_ndcg_at_k={k: _mean(r.ndcg_at_k[k] for r in with_relevant) for k in k_values},
        mean_n_returned=_mean(r.n_returned for r in rows),
    )


# ---------------------------------------------------------------------------
# Worst failures — the section that drives the next fix
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FailureEntry:
    profile_id: str
    label_th: str
    missed_strong: list[tuple[str, int]]  # (filename, 1-based deep rank) for label=2 cases not shown
    top1_filename: str | None
    top1_label: int | None
    zero_returned: bool


def worst_failures(
    production_results: Sequence[ProfileResult],
    deep_results: Mapping[str, ProfileResult],
    *,
    top_n: int = 10,
) -> list[FailureEntry]:
    """Ranked by severity: more missed strong cases first, then an
    irrelevant (label=0) top-1, then zero cases returned at all. Profiles
    with none of these problems are dropped — this list exists to point at
    what to fix next, not to enumerate every profile."""
    entries: list[FailureEntry] = []
    for prod in production_results:
        deep = deep_results.get(prod.profile_id)
        shown = set(prod.ranked_filenames)
        missed_strong: list[tuple[str, int]] = []
        if deep is not None:
            for rank, (fn, label) in enumerate(
                zip(deep.ranked_filenames, deep.ranked_labels), start=1
            ):
                if label >= 2 and fn not in shown:
                    missed_strong.append((fn, rank))

        top1_filename = prod.ranked_filenames[0] if prod.ranked_filenames else None
        top1_label = prod.ranked_labels[0] if prod.ranked_labels else None
        zero_returned = len(prod.ranked_filenames) == 0

        if missed_strong or top1_label == 0 or zero_returned:
            entries.append(
                FailureEntry(
                    profile_id=prod.profile_id,
                    label_th=prod.label_th,
                    missed_strong=missed_strong,
                    top1_filename=top1_filename,
                    top1_label=top1_label,
                    zero_returned=zero_returned,
                )
            )

    def severity(e: FailureEntry) -> tuple:
        return (
            -len(e.missed_strong),
            0 if e.top1_label == 0 else 1,
            0 if e.zero_returned else 1,
        )

    entries.sort(key=severity)
    return entries[:top_n]


# ---------------------------------------------------------------------------
# Sensitivity — contrast-pair diagnostic
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SensitivityPair:
    base_profile: str
    variant_profile: str
    differs_in_field: str
    kendall_tau: float


def compute_sensitivity(
    pairs: Sequence[tuple[str, str, str]], deep_rankings: Mapping[str, list[str]]
) -> list[SensitivityPair]:
    """`pairs` is (base_profile_id, variant_profile_id, field_that_differs).
    `deep_rankings` maps profile_id -> its deep-mode filename ranking (must
    contain the same file set for a pair to be comparable — deep mode ranks
    the whole corpus, so this always holds in practice)."""
    results = []
    for base, variant, differing_field in pairs:
        tau = m.kendall_tau(deep_rankings[base], deep_rankings[variant])
        results.append(
            SensitivityPair(
                base_profile=base, variant_profile=variant, differs_in_field=differing_field, kendall_tau=tau
            )
        )
    return results


# ---------------------------------------------------------------------------
# Score calibration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationRow:
    label: int
    distribution: ScoreDistribution | None


@dataclass(frozen=True)
class CalibrationSummary:
    by_label: list[CalibrationRow]
    auc_any: float | None  # label>=1 vs label=0
    auc_strong: float | None  # label==2 vs label=0
    overlap_zero_above_strong_median: float
    verdict: str


def _calibration_verdict(auc_any: float | None, auc_strong: float | None) -> str:
    candidates = [v for v in (auc_any, auc_strong) if v is not None]
    if not candidates:
        return "insufficient data — no label=0 pairs judged yet to compare against"
    best = max(candidates)
    if best >= 0.80:
        return "ordinal signal is defensible; consider isotonic calibration so the % means something"
    if best >= 0.65:
        return "order is informative, magnitude isn't; show a band (e.g. strong/some/none), not a raw %"
    return "the percentage is noise; no monotone transform fixes it — show rank only"


def compute_calibration(scores_by_label: Mapping[int, Sequence[float]]) -> CalibrationSummary:
    zero = list(scores_by_label.get(0, []))
    one = list(scores_by_label.get(1, []))
    two = list(scores_by_label.get(2, []))

    auc_any = auc(one + two, zero)
    auc_strong = auc(two, zero)

    two_dist = score_distribution(two)
    overlap = overlap_fraction(zero, two_dist.median) if two_dist is not None else 0.0

    return CalibrationSummary(
        by_label=[
            CalibrationRow(label=label, distribution=score_distribution(scores_by_label.get(label, [])))
            for label in (0, 1, 2)
        ],
        auc_any=auc_any,
        auc_strong=auc_strong,
        overlap_zero_above_strong_median=overlap,
        verdict=_calibration_verdict(auc_any, auc_strong),
    )


# ---------------------------------------------------------------------------
# Full run report — rendering
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunConfig:
    rag_top_k: int
    rag_max_distance: float
    embed_model: str
    chunk_tokens: int
    chunk_overlap: int
    query_variant: str
    workspace_slug: str
    impersonated_user: str
    is_preview_impersonation: bool
    git_sha: str | None


@dataclass(frozen=True)
class CorpusSummary:
    file_count: int
    chunk_count: int
    unembedded_file_count: int
    sha_drift_count: int


@dataclass(frozen=True)
class LabelSummary:
    source: str
    is_placeholder: bool
    coverage_pct: float
    n_strong: int
    n_some: int
    n_none: int


@dataclass(frozen=True)
class RunReport:
    generated_at: str
    config: RunConfig
    corpus: CorpusSummary
    labels: LabelSummary
    production_rows: list[ProfileMetricRow]
    production_aggregate: AggregateMetrics
    deep_rows: list[ProfileMetricRow]
    deep_aggregate: AggregateMetrics
    failures: list[FailureEntry]
    sensitivity: list[SensitivityPair]
    calibration: CalibrationSummary


def to_json_dict(report: RunReport) -> dict:
    return asdict(report)


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _fmt(x: float, digits: int = 3) -> str:
    return f"{x:.{digits}f}"


def render_markdown(report: RunReport) -> str:
    c, corpus, labels = report.config, report.corpus, report.labels
    lines: list[str] = []
    lines.append(f"# Case-match eval — {report.generated_at}")
    lines.append(
        f"Config: rag_top_k={c.rag_top_k} rag_max_distance={c.rag_max_distance} "
        f"embed={c.embed_model} chunk={c.chunk_tokens}/{c.chunk_overlap} "
        f"query_variant={c.query_variant}"
    )
    lines.append(
        f"Corpus: {corpus.file_count} files / {corpus.chunk_count} chunks / "
        f"{corpus.unembedded_file_count} unembedded / {corpus.sha_drift_count} sha drift"
    )
    placeholder_banner = "  ⚠ PLACEHOLDER LABELS — metrics are meaningless by construction" if labels.is_placeholder else ""
    lines.append(
        f"Labels: {labels.source}  coverage={_fmt_pct(labels.coverage_pct)}  "
        f"strong={labels.n_strong} some={labels.n_some} none={labels.n_none}{placeholder_banner}"
    )
    preview_note = " (preview-mode impersonation)" if c.is_preview_impersonation else ""
    lines.append(
        f"Impersonated: {c.impersonated_user} (workspace {c.workspace_slug}){preview_note}   "
        f"git={c.git_sha or 'unknown'}"
    )

    short_returns = [r for r in report.production_rows if r.n_returned < max(K_VALUES)]
    if short_returns:
        lines.append(
            f"⚠ {len(short_returns)} profile(s) returned fewer than {max(K_VALUES)} cases "
            f"(chunk budget — see rag_top_k)"
        )
    lines.append("")

    def _agg_table(title: str, agg: AggregateMetrics) -> list[str]:
        out = [f"## {title}", "", "| metric | value |", "|---|---|"]
        for k in K_VALUES:
            out.append(f"| P@{k} (/k) | {_fmt(agg.mean_precision_at_k[k])} |")
            out.append(f"| P@{k} (/returned) | {_fmt(agg.mean_precision_at_k_returned[k])} |")
        out.append(f"| MRR | {_fmt(agg.mean_mrr)} |")
        for k in K_VALUES:
            out.append(f"| recall@{k} | {_fmt(agg.mean_recall_at_k[k])} |")
            out.append(f"| strong-recall@{k} | {_fmt(agg.mean_strong_recall_at_k[k])} |")
            out.append(f"| nDCG@{k} | {_fmt(agg.mean_ndcg_at_k[k])} |")
        out.append(f"| mean cases returned | {_fmt(agg.mean_n_returned, 1)} |")
        out.append(
            f"| profiles with >=1 relevant / total | {agg.n_profiles_with_relevant}/{agg.n_profiles} |"
        )
        out.append("")
        return out

    lines += _agg_table("Overall — production settings (what the client sees)", report.production_aggregate)
    lines += _agg_table("Overall — deep pool (what the retriever could reach)", report.deep_aggregate)

    lines.append("## Per profile (production settings)")
    lines.append("")
    lines.append("| profile | returned | P@1 | nDCG@5 | RR | strong found/total |")
    lines.append("|---|---|---|---|---|---|")
    for r in report.production_rows:
        lines.append(
            f"| {r.profile_id} | {r.n_returned} | {_fmt(r.precision_at_k[1])} | "
            f"{_fmt(r.ndcg_at_k[5])} | {_fmt(r.mrr)} | "
            f"{int(round(r.strong_recall_at_k[5] * r.total_strong))}/{r.total_strong} |"
        )
    lines.append("")

    lines.append("## Worst failures")
    lines.append("")
    if not report.failures:
        lines.append("None — every profile's top results matched at least as well as the thresholds require.")
    for i, f in enumerate(report.failures, start=1):
        if f.zero_returned:
            lines.append(f"{i}. {f.profile_id} — 0 cases returned.")
        elif f.top1_label == 0:
            lines.append(f"{i}. {f.profile_id} — top-1 is label=0 ({f.top1_filename}).")
        if f.missed_strong:
            missed_str = ", ".join(f"{fn} (deep rank {rank})" for fn, rank in f.missed_strong[:3])
            lines.append(f"   {len(f.missed_strong)} strong case(s) missed: {missed_str}")
    lines.append("")

    lines.append("## Sensitivity (contrast pairs)")
    lines.append("")
    for s in report.sensitivity:
        lines.append(
            f"- {s.base_profile} vs {s.variant_profile} ({s.differs_in_field} differs only): "
            f"Kendall tau {_fmt(s.kendall_tau, 2)}"
        )
    lines.append("")

    lines.append("## Score calibration")
    lines.append("")
    for row in report.calibration.by_label:
        d = row.distribution
        if d is None:
            lines.append(f"- label={row.label}: n/a (no judged pairs)")
        else:
            lines.append(
                f"- label={row.label}: n={d.n} median={_fmt(d.median)} "
                f"[{_fmt(d.min)}, {_fmt(d.max)}]"
            )
    auc_any_str = _fmt(report.calibration.auc_any) if report.calibration.auc_any is not None else "n/a"
    auc_strong_str = _fmt(report.calibration.auc_strong) if report.calibration.auc_strong is not None else "n/a"
    lines.append(f"AUC(>=1 vs 0) = {auc_any_str} · AUC(2 vs 0) = {auc_strong_str}")
    lines.append(
        f"{_fmt_pct(report.calibration.overlap_zero_above_strong_median)} of label=0 pairs "
        f"score at or above the label=2 median"
    )
    lines.append(f"Verdict: {report.calibration.verdict}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Baseline diff
# ---------------------------------------------------------------------------


def _flatten_aggregate(agg: AggregateMetrics, prefix: str) -> dict[str, float]:
    flat: dict[str, float] = {}
    for k, v in agg.mean_precision_at_k.items():
        flat[f"{prefix}.mean_precision_at_{k}"] = v
    for k, v in agg.mean_recall_at_k.items():
        flat[f"{prefix}.mean_recall_at_{k}"] = v
    for k, v in agg.mean_strong_recall_at_k.items():
        flat[f"{prefix}.mean_strong_recall_at_{k}"] = v
    for k, v in agg.mean_ndcg_at_k.items():
        flat[f"{prefix}.mean_ndcg_at_{k}"] = v
    flat[f"{prefix}.mean_mrr"] = agg.mean_mrr
    flat[f"{prefix}.mean_n_returned"] = agg.mean_n_returned
    return flat


def flatten_report_metrics(report: RunReport) -> dict[str, float]:
    """Scalar metric keys used for --baseline diffing (eval_case_match_run.py).
    Deliberately a curated flat set, not a generic deep-diff of the whole
    report — most of RunReport is context/labels, not something a delta
    is meaningful for."""
    flat = {}
    flat.update(_flatten_aggregate(report.production_aggregate, "production"))
    flat.update(_flatten_aggregate(report.deep_aggregate, "deep"))
    return flat


def diff_against_baseline(current: RunReport, baseline_flat: Mapping[str, float]) -> dict[str, dict]:
    """current vs. a previously flattened baseline (usually loaded from a
    prior run's run-<ts>.json via flatten_report_metrics applied after
    reconstructing a RunReport, or persisted flat to begin with). Returns
    {metric_key: {"current":..., "baseline":..., "delta":...}} for every
    key present in both."""
    current_flat = flatten_report_metrics(current)
    diffs = {}
    for key, cur_val in current_flat.items():
        if key in baseline_flat:
            diffs[key] = {
                "current": cur_val,
                "baseline": baseline_flat[key],
                "delta": cur_val - baseline_flat[key],
            }
    return diffs
