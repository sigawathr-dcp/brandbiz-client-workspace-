"""Unit tests for the spreadsheet-phrase -> token mapping (app/eval/case_tag_map.py).

The mapping is the seam where a human's prose becomes something the scorer
can compare, and every failure mode here is silent at runtime: a phrase that
resolves to nothing makes a case look unrelated to every client forever, and
a phrase that resolves to the wrong token quietly shows the wrong case
studies to a real prospect. Neither raises in production, so the guarantees
have to be asserted here.
"""
from __future__ import annotations

import pytest

from app.eval import case_tag_map
from app.eval.case_sheet import TAG_DIMENSIONS
from app.services import case_taxonomy


class TestNamespaceIntegrity:
    """Every token the mapping can emit must exist in the vocabulary the
    intake options use — the two sides of the matcher are one namespace."""

    def test_every_component_target_is_in_the_vocabulary(self):
        for dimension, table in case_tag_map.COMPONENT_MAP.items():
            for phrase, tokens in table.items():
                for token in tokens:
                    assert case_taxonomy.is_valid(dimension, token), (
                        f"{dimension}: {phrase!r} -> {token!r} is not a real token"
                    )

    def test_every_whole_value_target_is_in_the_vocabulary(self):
        for dimension, table in case_tag_map.WHOLE_VALUE_MAP.items():
            for phrase, tokens in table.items():
                for token in tokens:
                    assert case_taxonomy.is_valid(dimension, token), (
                        f"{dimension}: {phrase!r} -> {token!r} is not a real token"
                    )

    def test_mapping_covers_exactly_the_scoring_dimensions(self):
        mapped = set(case_tag_map.COMPONENT_MAP) | set(case_tag_map.WHOLE_VALUE_MAP)
        assert mapped == set(case_taxonomy.DIMENSIONS)
        assert mapped == set(TAG_DIMENSIONS)

    def test_own_commerce_has_no_mapping_at_all(self):
        # It is a solution trigger, not a corpus tag. A case study cannot be
        # tagged with a fact about a client's platform dependency.
        assert "own_commerce" not in case_tag_map.COMPONENT_MAP
        assert "own_commerce" not in case_tag_map.WHOLE_VALUE_MAP
        with pytest.raises(ValueError):
            case_tag_map.tags_for("own_commerce", "Heavy")

    def test_no_dimension_is_both_component_and_whole_value(self):
        # tags_for() checks WHOLE_VALUE_MAP first; a dimension in both would
        # make COMPONENT_MAP dead code that still looks authoritative.
        assert not (set(case_tag_map.COMPONENT_MAP) & set(case_tag_map.WHOLE_VALUE_MAP))


class TestUnknownPhrasesFailLoudly:
    """The whole point of UNMAPPED: a phrase nobody has judged must stop the
    build, not quietly contribute nothing."""

    def test_unrecognised_component_raises(self):
        with pytest.raises(ValueError, match="unmapped component"):
            case_tag_map.tags_for("objective", "Awareness / Telepathy")

    def test_unrecognised_whole_cell_raises(self):
        with pytest.raises(ValueError, match="unmapped cell"):
            case_tag_map.tags_for("asset_channel", "Carrier pigeon / Semaphore")

    def test_deliberately_unmapped_component_is_silent(self):
        # "Trial" is an outcome, not a problem — mapped under objective,
        # deliberately not under challenge.
        assert case_tag_map.tags_for("challenge", "Launch / Trial") == ("launch_need",)
        assert case_tag_map.tags_for("objective", "Trial") == ("sales_acquisition",)

    def test_unmapped_entries_do_not_shadow_a_real_mapping(self):
        # A phrase in both tables would resolve by table order rather than by
        # judgement, which is exactly the ambiguity UNMAPPED exists to remove.
        for dimension, table in case_tag_map.COMPONENT_MAP.items():
            overlap = set(table) & case_tag_map.UNMAPPED.get(dimension, frozenset())
            assert not overlap, f"{dimension}: {sorted(overlap)} is both mapped and unmapped"

    def test_blank_cell_is_not_an_error(self):
        assert case_tag_map.tags_for("industry", "") == ()
        assert case_tag_map.tags_for("industry", "   ") == ()


class TestNormalisation:
    def test_dash_spelling_does_not_create_two_keys(self):
        # The sheet mixes "Gen Z 13-25" (hyphen) and en-dash forms.
        assert case_tag_map.tags_for("audience", "Gen Z 13–25") == ("gen_z_student",)
        assert case_tag_map.tags_for("audience", "Gen Z 13-25") == ("gen_z_student",)

    def test_case_and_spacing_are_ignored(self):
        assert case_tag_map.tags_for("objective", "  AWARENESS  ") == ("awareness",)
        assert case_tag_map.tags_for(
            "asset_channel", "SOCIAL  /  COMMUNITY"
        ) == ("social_only",)


class TestAdditiveVsExclusive:
    def test_component_dimensions_accumulate(self):
        assert case_tag_map.tags_for("objective", "Awareness / Engagement / Sales") == (
            "awareness",
            "engagement_community",
            "sales_acquisition",
        )

    def test_duplicate_components_collapse(self):
        # "Beauty / Skincare" both mean beauty; one tag, not two.
        assert case_tag_map.tags_for("industry", "Beauty / Skincare") == ("beauty",)

    def test_asset_channel_does_not_split(self):
        # The failure this prevents: reading "App / Social / Live Event" as
        # "social is the main channel" for a business whose main channel is
        # its own app.
        tokens = case_tag_map.tags_for("asset_channel", "App / Social / Live Event")
        assert "social_only" not in tokens
        assert tokens == ("multi_channel_siloed", "offline_touchpoint")


class TestJudgementCalls:
    """Mappings that are decisions rather than transcription. If one of these
    is wrong it should be changed deliberately, with this test."""

    def test_campaign_launch_is_not_a_business_stage(self):
        # Six Warner tentpoles are "Established / Campaign Launch". Reading
        # "Campaign Launch" as pre_launch would file a global studio as a
        # startup that has not opened yet.
        assert case_tag_map.tags_for("stage", "Established / Campaign Launch") == (
            "enterprise",
        )

    def test_regional_expansion_is_enterprise(self):
        # Our chip literally reads "Enterprise / Regional Expansion".
        assert case_tag_map.tags_for("stage", "Regional Expansion") == ("enterprise",)

    def test_overseas_market_is_the_tourist_overseas_chip(self):
        assert case_tag_map.tags_for("audience", "Beauty consumers / Cambodia market") == (
            "mass_market",
            "tourist_overseas",
        )

    def test_footfall_is_o2o(self):
        assert "o2o" in case_tag_map.tags_for("objective", "Awareness / Footfall / Engagement")

    def test_phone_case_brand_is_retail_not_an_app_business(self):
        assert case_tag_map.tags_for("industry", "Tech Accessories") == ("retail_fmcg",)

    def test_food_delivery_app_is_both_industries(self):
        # Grab is genuinely both, and case_study_tags is many-to-many so it
        # does not have to be resolved to a lie.
        assert case_tag_map.tags_for("industry", "Application / Food Delivery") == (
            "tech_app",
            "food_beverage",
        )
