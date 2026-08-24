"""Unit tests for the post-diagnosis solution triggers (script v3).

Two things are being defended here, and they pull in opposite directions.

The trigger must FIRE reliably when the client says their revenue depends on
GP-charging platforms — that is the whole reason Questions for DSMEs.xlsx
added the question, and leaving it to the drafting model to notice was the
failure mode the rule replaces.

The trigger must NOT fire on anything short of an explicit answer, and must
never reach the matcher. A recommendation to restructure how a business
sells is not something to infer from a blank, and `own_commerce` entering
SCORING_WEIGHTS would move every case ranking shown to every client.
"""
from __future__ import annotations

import pytest

from app.services import case_taxonomy, solution_trigger
from app.services.client_intake import INTAKE_SCRIPT, SCORING_WEIGHTS

# Chip values, spelled as the profile stores them (IntakeOption.value).
HEAVY = "Heavy - mostly marketplace / delivery / platform, high GP"
MIXED = "Mixed - own channels plus external platforms"
LIGHT = "Light - mostly the brand own channels"
NONE_YET = "No owned sales channel yet"
NOT_APPLICABLE = "Not applicable to my business"

LINE_OA = "LINE OA without real CRM / data capture"
HAS_CRM = "Existing customer database / CRM"
NO_BASE = "No owned customer base yet"

OBJ_LEAD_DATA = "Capture leads / first-party data"
OBJ_AWARENESS = "Build brand awareness"


def _fields(**kw: str) -> dict[str, str]:
    return dict(kw)


class TestQuarantinedFromMatching:
    """The sheet's hard rule: ไม่ใช้คำนวณ Similarity Score / Case Matching."""

    def test_own_commerce_is_not_a_scoring_dimension(self):
        assert "own_commerce" not in SCORING_WEIGHTS

    def test_own_commerce_is_not_in_the_corpus_vocabulary(self):
        # case_study_tags share this namespace. A case study must never be
        # taggable with a fact about a client's platform dependency.
        assert "own_commerce" not in case_taxonomy.VOCAB
        with pytest.raises(ValueError):
            case_taxonomy.validate_tag("own_commerce", "platform_heavy")

    def test_adding_the_trigger_did_not_move_the_weights(self):
        # v2's six weights, unchanged by v3. If this fails, every ranking a
        # client has ever been shown has silently shifted.
        assert SCORING_WEIGHTS == {
            "industry": 0.25,
            "stage": 0.05,
            "audience": 0.10,
            "challenge": 0.25,
            "asset_channel": 0.15,
            "objective": 0.20,
        }
        assert round(sum(SCORING_WEIGHTS.values()), 6) == 1.0

    def test_trigger_vocabulary_is_derived_not_transcribed(self):
        script_tags = {
            o["tag"]
            for step in INTAKE_SCRIPT
            if step["field"] == "own_commerce"
            for o in step["options"]
        }
        assert solution_trigger.TRIGGER_VOCAB["own_commerce"] == script_tags


class TestOwnCommerceFires:
    def test_heavy_platform_dependency_fires(self):
        out = solution_trigger.evaluate(_fields(own_commerce=HEAVY))
        assert [t.key for t in out] == ["own_commerce"]

    def test_no_owned_channel_fires(self):
        out = solution_trigger.evaluate(_fields(own_commerce=NONE_YET))
        assert [t.key for t in out] == ["own_commerce"]

    @pytest.mark.parametrize("answer", [MIXED, LIGHT, NOT_APPLICABLE])
    def test_the_other_answers_do_not_fire(self, answer):
        assert solution_trigger.evaluate(_fields(own_commerce=answer)) == ()

    def test_unanswered_does_not_fire(self):
        # An abandoned intake must not acquire a recommendation.
        assert solution_trigger.evaluate({}) == ()

    def test_free_text_does_not_fire(self):
        # Free text resolves to no token. Guessing at intent here would put a
        # workstream in the plan the client never asked for.
        assert solution_trigger.evaluate(_fields(own_commerce="ขายผ่านตัวแทนจำหน่าย")) == ()

    def test_reason_records_all_three_inputs(self):
        (t,) = solution_trigger.evaluate(
            _fields(own_commerce=HEAVY, asset_channel=LINE_OA, objective=OBJ_LEAD_DATA)
        )
        assert t.reason == (
            "own_commerce=platform_heavy, asset_channel=line_oa_no_crm, objective=lead_data"
        )

    def test_reason_marks_missing_inputs_rather_than_omitting_them(self):
        (t,) = solution_trigger.evaluate(_fields(own_commerce=HEAVY))
        assert "asset_channel=unknown" in t.reason
        assert "objective=unknown" in t.reason


class TestDirectiveIsShaded:
    """The sheet requires the recommendation read Existing Assets / Channel
    and Business Objective alongside the trigger answer, not fire one fixed
    sentence."""

    def test_dormant_line_oa_is_told_to_activate_not_rebuild(self):
        (t,) = solution_trigger.evaluate(
            _fields(own_commerce=HEAVY, asset_channel=LINE_OA)
        )
        assert "LINE Microsite" in t.directive
        assert "not a new platform" in t.directive

    def test_existing_crm_is_told_to_connect_not_duplicate(self):
        (t,) = solution_trigger.evaluate(
            _fields(own_commerce=HEAVY, asset_channel=HAS_CRM)
        )
        assert "second" in t.directive and "data store" in t.directive

    def test_no_owned_base_is_treated_as_foundational(self):
        (t,) = solution_trigger.evaluate(
            _fields(own_commerce=NONE_YET, asset_channel=NO_BASE)
        )
        assert "foundational" in t.directive

    def test_aligned_objective_leads_the_plan(self):
        (t,) = solution_trigger.evaluate(
            _fields(own_commerce=HEAVY, asset_channel=LINE_OA, objective=OBJ_LEAD_DATA)
        )
        assert "leading workstream" in t.directive

    def test_reach_objective_is_not_hijacked(self):
        # A client who came for awareness gets the recommendation as support,
        # never in place of what they asked for.
        (t,) = solution_trigger.evaluate(
            _fields(own_commerce=HEAVY, asset_channel=LINE_OA, objective=OBJ_AWARENESS)
        )
        assert "must NOT displace" in t.directive
        assert "leading workstream" not in t.directive

    def test_unknown_objective_still_produces_a_sized_directive(self):
        (t,) = solution_trigger.evaluate(_fields(own_commerce=HEAVY))
        assert "distinct workstream" in t.directive


class TestMultiSelectAnswers:
    """asset_channel and objective may be multi-select answers — stored as
    one joined string (client_intake.ANSWER_JOINER)."""

    def test_first_specific_asset_answer_shapes_the_build(self):
        (t,) = solution_trigger.evaluate(
            _fields(own_commerce=HEAVY, asset_channel=f"{LINE_OA}; {HAS_CRM}")
        )
        # LINE OA comes first in the stored (ordinal) order → its build wins.
        assert "LINE Microsite" in t.directive

    def test_any_aligned_objective_makes_it_lead(self):
        # Awareness picked ALONGSIDE first-party data: the data objective is
        # the stronger signal and owned commerce still leads.
        (t,) = solution_trigger.evaluate(
            _fields(
                own_commerce=HEAVY,
                asset_channel=LINE_OA,
                objective=f"{OBJ_AWARENESS}; {OBJ_LEAD_DATA}",
            )
        )
        assert "leading workstream" in t.directive

    def test_reason_records_every_token(self):
        (t,) = solution_trigger.evaluate(
            _fields(own_commerce=HEAVY, asset_channel=f"{LINE_OA}; {HAS_CRM}")
        )
        assert "asset_channel=line_oa_no_crm+has_crm" in t.reason
