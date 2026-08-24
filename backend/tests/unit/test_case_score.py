"""Unit tests for app/services/case_score.py — the weighted case-match score
(Interview_Details.xlsx columns F and G).

Pure functions over fixtures: no DB, no embed server. The point of the module
is that the whole scoring model is checkable this way.
"""
from __future__ import annotations

import pytest

from app.services import case_taxonomy
from app.services.case_score import (
    ADJACENT_CREDIT,
    FREE_TEXT_DAMPING,
    CaseScore,
    client_tags_from_fields,
    score_case,
)
from app.services.client_intake import INTAKE_SCRIPT, SCORING_WEIGHTS

# A fully-answered client, one token per scoring dimension.
_CLIENT = {
    "industry": "beauty",
    "stage": "growth",
    "audience": "working_adult",
    "challenge": "low_awareness",
    "asset_channel": "social_only",
    "objective": "awareness",
}


def _case(**over) -> dict[str, set[str]]:
    """A case tagged identically to _CLIENT, with overrides."""
    tags = {k: {v} for k, v in _CLIENT.items()}
    tags.update({k: (v if isinstance(v, set) else {v}) for k, v in over.items()})
    return tags


class TestWeights:
    def test_scoring_weights_sum_to_one(self):
        # The sheet's six weights are 0.25/0.05/0.10/0.25/0.15/0.20. If a
        # future script version breaks this, tag_score stops being 0..1 and
        # every displayed percentage silently rescales.
        assert round(sum(SCORING_WEIGHTS.values()), 6) == 1.0

    def test_feasibility_fields_are_not_scored(self):
        # The sheet marks timeframe and budget "Feasibility": they shape
        # scope and pricing, and must never decide which cases surface.
        assert "timeframe" not in SCORING_WEIGHTS
        assert "budget" not in SCORING_WEIGHTS

    def test_every_scoring_dimension_has_a_vocabulary(self):
        assert set(SCORING_WEIGHTS) == set(case_taxonomy.VOCAB)


class TestExactMatch:
    def test_identical_tags_score_one(self):
        r = score_case(_CLIENT, _case(), SCORING_WEIGHTS, 0.5, alpha=1.0)
        assert r.tag_score == pytest.approx(1.0)
        assert r.final == pytest.approx(1.0)
        assert set(r.matched_dimensions) == set(_CLIENT)

    def test_no_overlap_scores_zero(self):
        nothing = {k: {"__none__"} for k in _CLIENT}
        r = score_case(_CLIENT, nothing, SCORING_WEIGHTS, 0.5, alpha=1.0)
        assert r.tag_score == pytest.approx(0.0)
        assert r.matched_dimensions == ()

    def test_case_may_carry_several_tokens_per_dimension(self):
        # A campaign serving two audiences must still match a client in
        # either one — this is why case_study_tags is many-to-many.
        r = score_case(
            _CLIENT,
            _case(audience={"gen_z_student", "working_adult"}),
            SCORING_WEIGHTS, 0.5, alpha=1.0,
        )
        assert r.tag_score == pytest.approx(1.0)

    def test_one_missed_dimension_costs_exactly_its_weight(self):
        r = score_case(_CLIENT, _case(challenge={"__none__"}), SCORING_WEIGHTS, 0.5, alpha=1.0)
        assert r.tag_score == pytest.approx(1.0 - SCORING_WEIGHTS["challenge"])


class TestMultiSelectClient:
    """A client may pick several chips per scoring question (multi-select
    intake) — the dimension's credit is then the MEAN of per-token credit."""

    def test_half_covered_multi_answer_earns_half_credit(self):
        client = dict(_CLIENT, challenge=frozenset({"low_awareness", "slow_conversion"}))
        r = score_case(client, _case(), SCORING_WEIGHTS, 0.5, alpha=1.0)
        # The case covers low_awareness but not slow_conversion → 0.5 raw.
        expected = 1.0 - SCORING_WEIGHTS["challenge"] * 0.5
        assert r.tag_score == pytest.approx(expected)
        # At least one pick matched outright, so the card may still say so.
        assert "challenge" in r.matched_dimensions

    def test_fully_covered_multi_answer_earns_full_credit(self):
        client = dict(_CLIENT, audience=frozenset({"working_adult", "gen_z_student"}))
        r = score_case(
            client,
            _case(audience={"working_adult", "gen_z_student"}),
            SCORING_WEIGHTS, 0.5, alpha=1.0,
        )
        assert r.tag_score == pytest.approx(1.0)

    def test_multi_answer_with_no_overlap_is_a_miss(self):
        client = dict(_CLIENT, objective=frozenset({"lead_data", "o2o"}))
        r = score_case(client, _case(), SCORING_WEIGHTS, 0.5, alpha=1.0)
        assert r.tag_score == pytest.approx(1.0 - SCORING_WEIGHTS["objective"])
        assert "objective" not in r.matched_dimensions

    def test_adjacent_token_in_a_multi_answer_earns_adjacent_credit(self):
        client = dict(_CLIENT, industry=frozenset({"beauty", "automotive"}))
        r = score_case(client, _case(), SCORING_WEIGHTS, 0.5, alpha=1.0)
        # beauty matches exactly (1.0), automotive misses (0.0) → mean 0.5.
        assert r.tag_score == pytest.approx(1.0 - SCORING_WEIGHTS["industry"] * 0.5)


class TestAdjacency:
    def test_adjacent_industry_earns_partial_credit(self):
        # The sheet's own note says industry is "ไม่ใช่เงื่อนไขตายตัว". A
        # binary match would rank a same-industry irrelevant case above an
        # adjacent-industry case that solves the exact problem.
        assert "health_supplement" in case_taxonomy.INDUSTRY_ADJACENCY["beauty"]
        r = score_case(_CLIENT, _case(industry={"health_supplement"}), SCORING_WEIGHTS, 0.5, alpha=1.0)
        expected = 1.0 - SCORING_WEIGHTS["industry"] * (1 - ADJACENT_CREDIT)
        assert r.tag_score == pytest.approx(expected)
        assert [d.reason for d in r.dimensions if d.dimension == "industry"] == ["adjacent"]

    def test_unrelated_industry_gets_nothing(self):
        assert "automotive" not in case_taxonomy.INDUSTRY_ADJACENCY["beauty"]
        r = score_case(_CLIENT, _case(industry={"automotive"}), SCORING_WEIGHTS, 0.5, alpha=1.0)
        assert r.tag_score == pytest.approx(1.0 - SCORING_WEIGHTS["industry"])

    def test_adjacency_is_symmetric(self):
        for a, neighbours in case_taxonomy.INDUSTRY_ADJACENCY.items():
            for b in neighbours:
                assert a in case_taxonomy.INDUSTRY_ADJACENCY[b], f"{a}->{b} not symmetric"

    def test_adjacency_only_applies_to_industry(self):
        # No other dimension has a neighbour map; a near-miss elsewhere is a
        # miss.
        r = score_case(_CLIENT, _case(objective={"launch"}), SCORING_WEIGHTS, 0.5, alpha=1.0)
        assert [d.reason for d in r.dimensions if d.dimension == "objective"] == ["miss"]


class TestUnknownsAreNotZero:
    """A dimension we cannot resolve must not read as 'unsuitable'."""

    def test_untagged_case_falls_back_to_damped_dense(self):
        r = score_case(_CLIENT, {}, SCORING_WEIGHTS, 0.5, alpha=1.0)
        assert r.tag_score == pytest.approx(0.5 * FREE_TEXT_DAMPING)
        assert {d.reason for d in r.dimensions} == {"inferred"}

    def test_free_text_answer_falls_back_to_damped_dense(self):
        client = dict(_CLIENT, industry=None)  # client typed something off-menu
        r = score_case(client, _case(), SCORING_WEIGHTS, 0.5, alpha=1.0)
        w = SCORING_WEIGHTS["industry"]
        assert r.tag_score == pytest.approx((1.0 - w) + w * 0.5 * FREE_TEXT_DAMPING)

    def test_damping_ranks_below_adjacency(self):
        # "a human called these neighbours" must beat "the embedding thinks
        # they're similar", even when the embedding is confident.
        assert FREE_TEXT_DAMPING < ADJACENT_CREDIT

    def test_unanswered_dimension_is_dropped_not_zeroed(self):
        # An abandoned intake should not drag every case down uniformly.
        r = score_case({"industry": "beauty"}, _case(), SCORING_WEIGHTS, 0.1, alpha=1.0)
        assert r.tag_score == pytest.approx(1.0)
        reasons = {d.dimension: d.reason for d in r.dimensions}
        assert reasons["industry"] == "exact"
        assert reasons["objective"] == "unanswered"

    def test_no_answers_at_all_scores_zero_without_dividing_by_zero(self):
        r = score_case({}, _case(), SCORING_WEIGHTS, 0.4, alpha=1.0)
        assert r.tag_score == 0.0


class TestBlend:
    def test_alpha_zero_reproduces_the_dense_score_exactly(self):
        # The rollback path and the eval harness's A/B baseline.
        r = score_case(_CLIENT, _case(), SCORING_WEIGHTS, 0.42, alpha=0.0)
        assert r.final == pytest.approx(0.42)

    def test_alpha_one_ignores_the_dense_score(self):
        r = score_case(_CLIENT, _case(), SCORING_WEIGHTS, 0.01, alpha=1.0)
        assert r.final == pytest.approx(1.0)

    def test_default_alpha_blends_both(self):
        r = score_case(_CLIENT, _case(), SCORING_WEIGHTS, 0.5, alpha=0.7)
        assert r.final == pytest.approx(0.7 * 1.0 + 0.3 * 0.5)

    @pytest.mark.parametrize("alpha", [-1.0, 2.0])
    def test_alpha_is_clamped(self, alpha):
        r = score_case(_CLIENT, _case(), SCORING_WEIGHTS, 0.5, alpha=alpha)
        assert 0.0 <= r.final <= 1.0

    @pytest.mark.parametrize("dense", [-0.3, 1.7])
    def test_dense_score_is_clamped(self, dense):
        r = score_case(_CLIENT, _case(), SCORING_WEIGHTS, dense, alpha=0.5)
        assert 0.0 <= r.final <= 1.0

    def test_per_dimension_dense_overrides_the_whole_profile_score(self):
        r = score_case(
            _CLIENT, {}, SCORING_WEIGHTS, 0.0, alpha=1.0,
            dense_by_dimension={d: 1.0 for d in SCORING_WEIGHTS},
        )
        assert r.tag_score == pytest.approx(FREE_TEXT_DAMPING)


class TestBreakdown:
    def test_contributions_sum_to_the_tag_score(self):
        r = score_case(_CLIENT, _case(industry={"health_supplement"}), SCORING_WEIGHTS, 0.5, alpha=1.0)
        assert sum(d.contribution for d in r.dimensions) == pytest.approx(r.tag_score)

    def test_dimensions_render_in_interview_order(self):
        r = score_case(_CLIENT, _case(), SCORING_WEIGHTS, 0.5, alpha=1.0)
        assert [d.dimension for d in r.dimensions] == list(SCORING_WEIGHTS)

    def test_matched_dimensions_lists_only_exact_hits(self):
        r = score_case(
            _CLIENT,
            _case(industry={"health_supplement"}, objective={"launch"}),
            SCORING_WEIGHTS, 0.5, alpha=1.0,
        )
        assert "industry" not in r.matched_dimensions  # adjacent, not exact
        assert "objective" not in r.matched_dimensions  # miss
        assert "challenge" in r.matched_dimensions

    def test_result_is_immutable(self):
        r = score_case(_CLIENT, _case(), SCORING_WEIGHTS, 0.5, alpha=1.0)
        assert isinstance(r, CaseScore)
        with pytest.raises(Exception):
            r.final = 0.0  # type: ignore[misc]


class TestClientTagsFromFields:
    def test_chip_values_resolve_to_tokens(self):
        fields = {
            step["field"]: step["options"][0]["value"]
            for step in INTAKE_SCRIPT
        }
        tags = client_tags_from_fields(fields)
        assert tags["industry"] == frozenset({INTAKE_SCRIPT[0]["options"][0]["tag"]})
        assert set(tags) == set(case_taxonomy.DIMENSIONS)

    def test_multi_select_values_split_into_a_token_set(self):
        fields = {step["field"]: step["options"][0]["value"] for step in INTAKE_SCRIPT}
        fields["industry"] = "; ".join(
            [INTAKE_SCRIPT[0]["options"][0]["value"], INTAKE_SCRIPT[0]["options"][1]["value"]]
        )
        tags = client_tags_from_fields(fields)
        assert tags["industry"] == frozenset(
            {INTAKE_SCRIPT[0]["options"][0]["tag"], INTAKE_SCRIPT[0]["options"][1]["tag"]}
        )

    def test_free_text_resolves_to_none_not_a_crash(self):
        fields = {step["field"]: step["options"][0]["value"] for step in INTAKE_SCRIPT}
        fields["industry"] = "สตูดิโอโยคะสำหรับผู้หญิงวัยทำงาน"
        assert client_tags_from_fields(fields)["industry"] is None

    def test_feasibility_fields_are_not_returned(self):
        fields = {step["field"]: step["options"][0]["value"] for step in INTAKE_SCRIPT}
        tags = client_tags_from_fields(fields)
        assert "timeframe" not in tags and "budget" not in tags

    def test_v1_vocabulary_is_skipped_not_crashed_on(self):
        # An engagement pinned to script v1 answers goal / horizon / history,
        # which have no dimension in the v2 tag vocabulary. Those ride the
        # dense half of the blend instead of raising.
        v1 = {
            "industry": "Food & beverage / café",
            "goal": "Grow sales / expand",
            "horizon": "6 months",
            "history": "One freelance logo project",
        }
        tags = client_tags_from_fields(v1)
        assert "goal" not in tags and "history" not in tags
        assert tags["industry"] is None  # v1's chip value is not a v2 chip value


class TestTaxonomy:
    def test_validate_tag_rejects_a_typo(self):
        with pytest.raises(ValueError, match="controlled vocabulary"):
            case_taxonomy.validate_tag("industry", "beuaty")

    def test_validate_tag_rejects_a_feasibility_dimension(self):
        with pytest.raises(ValueError, match="unknown tag dimension"):
            case_taxonomy.validate_tag("budget", "under_300k")

    def test_vocabulary_matches_the_script_options(self):
        for step in INTAKE_SCRIPT:
            if step["use_mode"] != "match":
                continue
            assert case_taxonomy.VOCAB[step["match_tag"]] == frozenset(
                o["tag"] for o in step["options"]
            )
