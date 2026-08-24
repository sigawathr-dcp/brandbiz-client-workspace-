"""Unit tests for app/eval/query_variants.py."""
from __future__ import annotations

from app.eval.query_variants import VARIANTS, natural_th, thai_labels, values_only
from app.services import case_match
from app.services.client_intake import INTAKE_SCRIPT

# Derived from the script, not transcribed: intake v2 renamed goal ->
# objective / horizon -> timeframe and replaced history with asset_channel,
# which silently invalidated the hand-written version of this fixture.
_FIELDS = {step["field"]: step["options"][0]["value"] for step in INTAKE_SCRIPT}

_IND = INTAKE_SCRIPT[0]
_IND_VALUE, _IND_TH = _IND["options"][0]["value"], _IND["options"][0]["label"]
_STAGE_VALUE = INTAKE_SCRIPT[1]["options"][0]["value"]
_AUD = next(s for s in INTAKE_SCRIPT if s["field"] == "audience")
_AUD_TH = _AUD["options"][0]["label"]


class TestVariantRegistry:
    def test_prod_is_the_actual_production_function_not_a_copy(self):
        # Identity check, not equality — an eval that reimplemented
        # build_context_query would silently stop measuring production.
        assert VARIANTS["prod"] is case_match.build_context_query

    def test_every_variant_is_callable_and_returns_nonempty_string(self):
        for name, builder in VARIANTS.items():
            result = builder(_FIELDS)
            assert isinstance(result, str)
            assert result.strip(), f"variant {name!r} returned an empty string"


class TestThaiLabels:
    def test_uses_thai_field_and_chip_labels(self):
        result = thai_labels(_FIELDS)
        assert f"ธุรกิจ: {_IND_TH}" in result

    def test_falls_back_to_raw_value_for_unmapped_chip(self):
        fields = dict(_FIELDS, industry="ร้านขายของทั่วไป")
        result = thai_labels(fields)
        assert "ร้านขายของทั่วไป" in result


class TestValuesOnly:
    def test_no_field_labels_present(self):
        result = values_only(_FIELDS)
        assert "Business:" not in result
        assert _IND_VALUE in result

    def test_semicolon_joined_in_script_order(self):
        result = values_only(_FIELDS)
        assert result.index(_IND_VALUE) < result.index(_STAGE_VALUE)


class TestNaturalTh:
    def test_produces_one_thai_sentence_with_all_field_values(self):
        result = natural_th(_FIELDS)
        assert _IND_TH in result
        assert _AUD_TH in result  # Thai chip label for audience
