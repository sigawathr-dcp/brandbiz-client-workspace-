"""Unit tests for app/eval/query_variants.py."""
from __future__ import annotations

from app.eval.query_variants import VARIANTS, natural_th, thai_labels, values_only
from app.services import case_match

_FIELDS = {
    "industry": "Food & beverage / café",
    "stage": "Growing, ready to expand",
    "audience": "Urban working adults",
    "challenge": "Low brand awareness",
    "goal": "Grow sales / expand",
    "horizon": "6 months",
    "budget": "฿300,000 - 800,000",
    "history": "One freelance logo project",
}


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
        assert "ธุรกิจ: ร้านอาหาร / คาเฟ่" in result

    def test_falls_back_to_raw_value_for_unmapped_chip(self):
        fields = dict(_FIELDS, industry="ร้านขายของทั่วไป")
        result = thai_labels(fields)
        assert "ร้านขายของทั่วไป" in result


class TestValuesOnly:
    def test_no_field_labels_present(self):
        result = values_only(_FIELDS)
        assert "Business:" not in result
        assert "Food & beverage / café" in result

    def test_semicolon_joined_in_script_order(self):
        result = values_only(_FIELDS)
        assert result.index("Food & beverage / café") < result.index("Growing, ready to expand")


class TestNaturalTh:
    def test_produces_one_thai_sentence_with_all_field_values(self):
        result = natural_th(_FIELDS)
        assert "ร้านอาหาร / คาเฟ่" in result
        assert "คนวัยทำงานในเมือง" in result  # Thai chip label for audience
