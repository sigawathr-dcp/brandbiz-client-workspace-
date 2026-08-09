"""Unit tests for app/eval/report.py's pure computation: per-profile
metrics, aggregation, worst-failure ranking, sensitivity, and calibration
verdicts. Markdown rendering is smoke-tested only (exact wording isn't a
contract); the numeric logic is what must be right."""
from __future__ import annotations

import pytest

from app.eval.report import (
    ProfileResult,
    aggregate,
    compute_calibration,
    compute_profile_metrics,
    compute_sensitivity,
    render_markdown,
    worst_failures,
)


def _profile(
    profile_id,
    ranked_filenames,
    ranked_labels,
    all_labels,
    judged_count=None,
    corpus_size=30,
) -> ProfileResult:
    total_relevant = sum(1 for l in all_labels if l >= 1)
    total_strong = sum(1 for l in all_labels if l >= 2)
    return ProfileResult(
        profile_id=profile_id,
        label_th="",
        ranked_filenames=ranked_filenames,
        ranked_labels=ranked_labels,
        all_labels=all_labels,
        total_relevant=total_relevant,
        total_strong=total_strong,
        judged_count=judged_count if judged_count is not None else len(all_labels),
        corpus_size=corpus_size,
    )


class TestComputeProfileMetrics:
    def test_basic_shape(self):
        result = _profile(
            "P01",
            ["a.md", "b.md", "c.md"],
            [2, 0, 1],
            [2, 2, 1] + [0] * 27,
        )
        row = compute_profile_metrics(result)
        assert row.n_returned == 3
        assert row.precision_at_k[1] == 1.0  # top-1 is label 2
        assert row.top1_filename == "a.md"
        assert row.top1_label == 2
        assert row.total_relevant == 3
        assert row.total_strong == 2
        assert row.judged_coverage == pytest.approx(30 / 30)

    def test_zero_returned(self):
        result = _profile("P11", [], [], [0] * 30)
        row = compute_profile_metrics(result)
        assert row.n_returned == 0
        assert row.top1_filename is None
        assert row.top1_label is None
        assert row.precision_at_k[5] == 0.0

    def test_partial_judged_coverage(self):
        result = _profile("P01", ["a.md"], [2], [2] + [0] * 29, judged_count=10, corpus_size=30)
        row = compute_profile_metrics(result)
        assert row.judged_coverage == pytest.approx(1 / 3)


class TestAggregate:
    def test_excludes_zero_relevant_profiles_from_recall_and_ndcg(self):
        has_relevant = _profile("P01", ["a.md"], [2], [2] + [0] * 29)
        no_relevant = _profile("P02", ["x.md"], [0], [0] * 30)
        rows = [compute_profile_metrics(has_relevant), compute_profile_metrics(no_relevant)]

        agg = aggregate(rows)

        assert agg.n_profiles == 2
        assert agg.n_profiles_with_relevant == 1
        # recall@5 mean should equal has_relevant's own recall@5 (1.0), not averaged with 0
        assert agg.mean_recall_at_k[5] == pytest.approx(1.0)
        # precision is defined for every profile regardless of relevance
        assert agg.mean_precision_at_k[1] == pytest.approx(0.5)  # (1.0 + 0.0) / 2

    def test_empty_rows(self):
        agg = aggregate([])
        assert agg.n_profiles == 0
        assert agg.mean_mrr == 0.0


class TestWorstFailures:
    def test_missed_strong_case_is_flagged(self):
        # production only returned 1 case (label=1); deep pool shows the
        # strong (label=2) case exists at deep rank 3 but wasn't surfaced
        prod = _profile("P07", ["weak.md"], [1], [2, 1] + [0] * 28)
        deep = _profile(
            "P07",
            ["other1.md", "other2.md", "strong.md", "weak.md"],
            [0, 0, 2, 1],
            [2, 1] + [0] * 28,
        )
        failures = worst_failures([prod], {"P07": deep})
        assert len(failures) == 1
        assert failures[0].missed_strong == [("strong.md", 3)]

    def test_irrelevant_top1_is_flagged(self):
        prod = _profile("P03", ["bad.md"], [0], [1] + [0] * 29)
        failures = worst_failures([prod], {})
        assert len(failures) == 1
        assert failures[0].top1_label == 0
        assert failures[0].top1_filename == "bad.md"

    def test_zero_returned_is_flagged(self):
        prod = _profile("P11", [], [], [0] * 30)
        failures = worst_failures([prod], {})
        assert failures[0].zero_returned

    def test_clean_profile_is_not_flagged(self):
        prod = _profile("P01", ["good.md"], [2], [2] + [0] * 29)
        deep = _profile("P01", ["good.md"], [2], [2] + [0] * 29)
        failures = worst_failures([prod], {"P01": deep})
        assert failures == []

    def test_sorted_by_missed_strong_count_descending(self):
        few_missed = _profile("P_few", ["a.md"], [1], [2, 1] + [0] * 28)
        few_deep = _profile("P_few", ["b.md", "a.md"], [2, 1], [2, 1] + [0] * 28)
        many_missed = _profile("P_many", ["a.md"], [1], [2, 2, 2, 1] + [0] * 26)
        many_deep = _profile(
            "P_many", ["b.md", "c.md", "d.md", "a.md"], [2, 2, 2, 1], [2, 2, 2, 1] + [0] * 26
        )
        failures = worst_failures(
            [few_missed, many_missed], {"P_few": few_deep, "P_many": many_deep}
        )
        assert failures[0].profile_id == "P_many"
        assert failures[1].profile_id == "P_few"

    def test_top_n_truncates(self):
        profiles = [
            _profile(f"P{i}", [], [], [0] * 30) for i in range(5)
        ]
        failures = worst_failures(profiles, {}, top_n=2)
        assert len(failures) == 2


class TestSensitivity:
    def test_identical_rankings_have_tau_one(self):
        rankings = {"P01": ["a.md", "b.md", "c.md"], "P01b": ["a.md", "b.md", "c.md"]}
        result = compute_sensitivity([("P01", "P01b", "goal")], rankings)
        assert result[0].kendall_tau == pytest.approx(1.0)
        assert result[0].differs_in_field == "goal"

    def test_reversed_rankings_have_tau_negative_one(self):
        rankings = {"P01": ["a.md", "b.md", "c.md"], "P01b": ["c.md", "b.md", "a.md"]}
        result = compute_sensitivity([("P01", "P01b", "budget")], rankings)
        assert result[0].kendall_tau == pytest.approx(-1.0)


class TestCalibration:
    def test_strong_separation_gives_high_auc_verdict(self):
        scores = {0: [0.1, 0.2, 0.15], 1: [0.5, 0.55], 2: [0.9, 0.85]}
        summary = compute_calibration(scores)
        assert summary.auc_strong == pytest.approx(1.0)
        assert "defensible" in summary.verdict

    def test_full_overlap_gives_noise_verdict(self):
        scores = {0: [0.5, 0.5, 0.5], 1: [0.5], 2: [0.5, 0.5]}
        summary = compute_calibration(scores)
        assert summary.auc_strong == pytest.approx(0.5)
        assert "noise" in summary.verdict

    def test_no_negatives_is_insufficient_data(self):
        scores = {1: [0.5], 2: [0.9]}
        summary = compute_calibration(scores)
        assert summary.auc_any is None
        assert "insufficient data" in summary.verdict


class TestRenderMarkdownSmoke:
    def test_renders_without_error_and_contains_key_sections(self):
        from app.eval.report import (
            CorpusSummary,
            LabelSummary,
            RunConfig,
            RunReport,
        )

        prod = _profile("P01", ["a.md"], [2], [2] + [0] * 29)
        row = compute_profile_metrics(prod)
        agg = aggregate([row])
        calibration = compute_calibration({0: [0.1], 1: [0.5], 2: [0.9]})

        report = RunReport(
            generated_at="2026-08-12T00:00Z",
            config=RunConfig(
                rag_top_k=5,
                rag_max_distance=0.6,
                embed_model="bge-m3:latest",
                chunk_tokens=500,
                chunk_overlap=50,
                query_variant="prod",
                workspace_slug="brandbiz-demo",
                impersonated_user="seat-1",
                is_preview_impersonation=False,
                git_sha="abc123",
            ),
            corpus=CorpusSummary(file_count=30, chunk_count=47, unembedded_file_count=0, sha_drift_count=0),
            labels=LabelSummary(
                source="labels.csv", is_placeholder=False, coverage_pct=1.0, n_strong=1, n_some=0, n_none=29
            ),
            production_rows=[row],
            production_aggregate=agg,
            deep_rows=[row],
            deep_aggregate=agg,
            failures=[],
            sensitivity=[],
            calibration=calibration,
        )

        md = render_markdown(report)
        assert "Case-match eval" in md
        assert "Overall — production settings" in md
        assert "Overall — deep pool" in md
        assert "Worst failures" in md
        assert "Score calibration" in md
