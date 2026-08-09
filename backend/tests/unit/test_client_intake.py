"""Unit tests for the deterministic client-intake script (Phase 5 §3).

The script is content, not logic, so these tests focus on the one piece of
real logic: resolve_answer() must never accept an out-of-range chip index
or an empty free-text fallback — a live event booth is not the place for a
KeyError to reach the user.
"""
from __future__ import annotations

import pytest

from app.services.client_intake import (
    INTAKE_SCRIPT,
    resolve_answer,
    step_at,
    total_steps,
)


class TestScriptShape:
    def test_eight_questions(self):
        assert total_steps() == 8

    def test_every_step_has_field_question_and_options(self):
        for step in INTAKE_SCRIPT:
            assert step["field"]
            assert step["question"]
            assert len(step["options"]) >= 2
            for opt in step["options"]:
                assert opt["label"]
                assert opt["value"]

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
