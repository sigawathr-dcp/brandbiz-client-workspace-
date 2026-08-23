"""Unit tests for the deterministic client-intake script (Phase 5 §3).

The script is content, not logic, so these tests focus on the one piece of
real logic: resolve_answer() must never accept an out-of-range chip index
or an empty free-text fallback — a live event booth is not the place for a
KeyError to reach the user.
"""
from __future__ import annotations

import pytest

from app.services.client_intake import (
    FIELD_LABELS,
    INTAKE_SCRIPT,
    field_manifest,
    index_of_field,
    resolve_answer,
    step_at,
    total_steps,
)


class TestScriptShape:
    def test_nine_questions(self):
        assert total_steps() == 9

    def test_every_step_has_field_question_and_options(self):
        for step in INTAKE_SCRIPT:
            assert step["field"]
            assert step["question"]
            assert len(step["options"]) >= 2
            for opt in step["options"]:
                assert opt["label"]
                assert opt["value"]

    def test_no_step_exceeds_nine_options(self):
        # IntakeChips.tsx binds 1-N to single digits via parseInt(e.key), so
        # a 10th option would be unreachable from the keyboard at a booth.
        # The sheet's 10-option industry list is why this guard exists.
        for step in INTAKE_SCRIPT:
            assert len(step["options"]) <= 9, (
                f"{step['field']} has {len(step['options'])} options"
            )

    def test_no_step_lists_its_own_free_text_option(self):
        # IntakeChips renders an "อื่นๆ" free-text row under every question
        # already; listing it as an option too would duplicate that row.
        for step in INTAKE_SCRIPT:
            for opt in step["options"]:
                assert "อื่น" not in opt["label"], (
                    f"{step['field']}: {opt['label']!r} duplicates the built-in free-text row"
                )

    def test_option_tags_are_unique_within_a_question(self):
        # tag_value is an option's stable identity for matching; two options
        # sharing a token would make the answer ambiguous to the scorer.
        for step in INTAKE_SCRIPT:
            tags = [o["tag"] for o in step["options"]]
            assert len(set(tags)) == len(tags), f"{step['field']} has duplicate tags"

    def test_option_values_are_unique_within_a_question(self):
        for step in INTAKE_SCRIPT:
            values = [o["value"] for o in step["options"]]
            assert len(set(values)) == len(values), f"{step['field']} has duplicate values"

    def test_weights_and_use_mode_agree(self):
        # The sheet's Weight column mixes numbers with the strings
        # "Feasibility" and "Solution Trigger"; the split into weight +
        # use_mode must stay coherent or a question silently drops out of the
        # score — or worse, silently enters it.
        for step in INTAKE_SCRIPT:
            assert step["use_mode"] in {"match", "feasibility", "solution_trigger"}
            if step["use_mode"] == "match":
                assert step["weight"] and 0 < step["weight"] <= 1, step["field"]
            else:
                assert step["weight"] is None, (
                    f"{step['field']} is {step['use_mode']} but carries a weight"
                )

    def test_scoring_weights_sum_to_one(self):
        total = sum(s["weight"] for s in INTAKE_SCRIPT if s["weight"])
        assert round(total, 6) == 1.0

    def test_every_scoring_question_has_a_match_tag(self):
        for step in INTAKE_SCRIPT:
            if step["use_mode"] == "match":
                assert step["match_tag"], step["field"]

    def test_every_step_has_an_insight(self):
        # Surfaced as the "insight earned" callout on the turn carrying the
        # NEXT question — see IntakeStep.insight's docstring in
        # app/services/client_intake.py for why it belongs to THIS step.
        for step in INTAKE_SCRIPT:
            assert step["insight"]
            assert step["insight"].strip() == step["insight"]

    def test_insight_count_matches_question_count(self):
        assert sum(1 for s in INTAKE_SCRIPT if s.get("insight")) == total_steps()

    def test_fields_are_unique(self):
        fields = [s["field"] for s in INTAKE_SCRIPT]
        assert len(fields) == len(set(fields))

    def test_step_at_out_of_range_returns_none(self):
        assert step_at(-1) is None
        assert step_at(total_steps()) is None
        assert step_at(total_steps() + 5) is None

    def test_step_at_in_range_returns_step(self):
        assert step_at(0) is not None
        assert step_at(total_steps() - 1) is not None


class TestFieldManifest:
    """GET /client/bootstrap serves this as intake_fields — the Profile
    tab's display contract (WorkPanel.tsx no longer keeps its own copy)."""

    def test_order_and_length_match_the_script(self):
        manifest = field_manifest()
        assert [f["key"] for f in manifest] == [s["field"] for s in INTAKE_SCRIPT]
        assert len(manifest) == total_steps()

    def test_labels_match_field_labels(self):
        for f in field_manifest():
            assert f["label"] == FIELD_LABELS[f["key"]]

    def test_options_match_the_script_in_order(self):
        # The Profile tab's edit mode (Task 5.11) renders these chips
        # directly — must stay index-aligned with resolve_answer's
        # option_index so an edit picks the same value the original
        # intake step would have.
        for f, step in zip(field_manifest(), INTAKE_SCRIPT):
            assert [o["label"] for o in f["options"]] == [o["label"] for o in step["options"]]
            assert [o["index"] for o in f["options"]] == list(range(len(step["options"])))


class TestIndexOfField:
    def test_round_trips_every_field(self):
        for i, step in enumerate(INTAKE_SCRIPT):
            assert index_of_field(step["field"]) == i

    def test_unknown_field_returns_none(self):
        assert index_of_field("not_a_real_field") is None


class TestResolveAnswer:
    def test_chip_selection_returns_option_value(self):
        step = INTAKE_SCRIPT[0]
        value = resolve_answer(step, option_index=1, free_text=None)
        assert value == step["options"][1]["value"]

    def test_free_text_is_used_when_no_option_index(self):
        step = INTAKE_SCRIPT[0]
        value = resolve_answer(step, option_index=None, free_text="  My own answer  ")
        assert value == "My own answer"

    def test_option_index_takes_precedence_over_free_text(self):
        step = INTAKE_SCRIPT[0]
        value = resolve_answer(step, option_index=0, free_text="ignored")
        assert value == step["options"][0]["value"]

    def test_out_of_range_option_index_raises(self):
        step = INTAKE_SCRIPT[0]
        with pytest.raises(ValueError):
            resolve_answer(step, option_index=len(step["options"]), free_text=None)

    def test_negative_option_index_raises(self):
        step = INTAKE_SCRIPT[0]
        with pytest.raises(ValueError):
            resolve_answer(step, option_index=-1, free_text=None)

    def test_neither_option_nor_text_raises(self):
        step = INTAKE_SCRIPT[0]
        with pytest.raises(ValueError):
            resolve_answer(step, option_index=None, free_text=None)

    def test_blank_free_text_raises(self):
        step = INTAKE_SCRIPT[0]
        with pytest.raises(ValueError):
            resolve_answer(step, option_index=None, free_text="   ")
