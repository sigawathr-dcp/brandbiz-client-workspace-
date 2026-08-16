"""Unit tests for plan._build_drafting_prompt()'s Thai-output directive.

The client workspace shows plan drafts to Thai clients, so the drafting
prompt instructs the model to write every JSON string VALUE in Thai while
keeping the JSON keys and rate-card codes untouched (rate_card.price()
looks codes up verbatim; a translated/altered code would silently drop a
budget line). This only checks the prompt text — the model call itself is
covered by test_plan_provenance.py and friends.
"""
from __future__ import annotations

from app.services.plan import _build_drafting_prompt


def _rate_item(code: str):
    class _R:
        pass

    r = _R()
    r.code = code
    r.label = "Positioning workshop"
    r.unit = "flat"
    r.currency = "THB"
    r.unit_price = 1000
    return r


def test_prompt_instructs_thai_values_and_preserves_codes():
    fields = {"industry": "Retail + online"}
    rate_items = [_rate_item("R1"), _rate_item("CONTENT-02")]

    # DB redesign: _build_drafting_prompt now takes research finding TEXTS
    # (already resolved from the normalized research_findings table) and a
    # list of case rows, not ORM objects — see app/services/plan.py.
    prompt = _build_drafting_prompt(fields, research_lines=[], cases=[], rate_items=rate_items)

    assert "Thai" in prompt
    assert "ภาษาไทย" in prompt
    assert "keep the JSON keys in English" in prompt.lower() or "JSON keys in English" in prompt
    # Every supplied rate-card code must still appear verbatim.
    assert "R1" in prompt
    assert "CONTENT-02" in prompt
    # The JSON shape's keys stay English even though the directive asks for
    # Thai values — draft_plan()'s _extract_json/rate_card_svc.price rely on
    # these exact keys.
    for key in ('"title"', '"core_idea"', '"analogous_case"', '"adapted_plan"', '"budget_items"'):
        assert key in prompt
