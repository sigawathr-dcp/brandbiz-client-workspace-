"""Unit tests for the market scan's Thai-output directive.

The "External market scan · IAG" step (POST /client/research) shipped with the
Thai instruction in the Perplexity SYSTEM message only, while its user turn was
built from FIELD_LABELS (English) plus IntakeOption.value (English by design).
Sonar weights the user turn — and the sources its web search retrieves off that
turn — far more heavily than a system message, so it answered in English.

_build_research_query() is therefore Thai end to end: it repeats the language
instruction in the user turn (the pattern plan.py::_build_drafting_prompt uses,
the one prompt here that has reliably produced Thai) and renders the business
context with THAI_FIELD_LABELS + the Thai chip labels the client clicked.

This only checks the prompt text; the Perplexity call itself is not exercised
here (tests/integration/test_engagement_funnel.py deliberately skips it too).
"""
from __future__ import annotations

from app.routers.client import _RESEARCH_SYSTEM_PROMPT, _build_research_query
from app.services.client_intake import FIELD_LABELS, INTAKE_SCRIPT, THAI_FIELD_LABELS

# Thai chip LABELS, as _load_fields_th() resolves them (not the English
# IntakeOption.value that _load_fields()/build_context_query() use). Built
# from the current script: THAI_FIELD_LABELS is a UNION across script
# versions (v1's goal / horizon / history are still listed so old
# engagements render), so it can no longer be used as the field list for a
# single profile — only the current script can.
_FIELDS_TH = {
    step["field"]: step["options"][0]["label"] for step in INTAKE_SCRIPT
}
_FIRST_INDUSTRY_TH = INTAKE_SCRIPT[0]["options"][0]["label"]


def _context_of(query: str) -> str:
    """Just the 'ข้อมูลธุรกิจ: …' block. The Thai instruction above it contains
    words like 'ธุรกิจ' and 'ลูกค้า' too, so a bare query.index() would match
    the preamble instead of the field label being asserted on."""
    marker = "ข้อมูลธุรกิจ: "
    assert marker in query
    return query.split(marker, 1)[1]


def test_query_is_thai_and_carries_the_language_instruction():
    query = _build_research_query(_FIELDS_TH)

    # The directive lives in the user turn, not only in the system prompt.
    assert "ภาษาไทย" in query
    assert "ภาษาไทย" in _RESEARCH_SYSTEM_PROMPT  # belt and braces, both turns

    # Citation markers and original-language proper nouns must survive.
    assert "[n]" in query


def test_context_uses_thai_labels_and_thai_chip_values():
    context = _context_of(_build_research_query(_FIELDS_TH))

    for key, value in _FIELDS_TH.items():
        assert f"{THAI_FIELD_LABELS[key]}: {value}" in context

    # No English label may leak back in — that regression is exactly what sent
    # the whole answer back to English.
    for english_label in FIELD_LABELS.values():
        assert f"{english_label}:" not in context


def test_fields_render_in_intake_script_order():
    context = _context_of(_build_research_query(_FIELDS_TH))
    positions = [context.index(f"{THAI_FIELD_LABELS[k]}: ") for k in _FIELDS_TH]
    assert positions == sorted(positions)


def test_partial_profile_only_includes_answered_fields():
    query = _build_research_query({"industry": _FIRST_INDUSTRY_TH})
    context = _context_of(query)

    assert context == f"ธุรกิจ: {_FIRST_INDUSTRY_TH}"
    assert THAI_FIELD_LABELS["budget"] not in context
    assert "ภาษาไทย" in query  # the directive is not conditional on the context
