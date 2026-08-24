"""Unit tests for plan.build_plan_context() — the saved plan, rendered as a
system block for POST /client/chat.

Why this block exists at all: a plan is an artifact outside the message
thread (app/models/plan.py), so a follow-up question about it used to reach a
model that had never seen it. The only trace in the conversation is
draft_plan()'s own prompt + raw JSON reply — the DRAFT, not what was saved or
revised afterwards.

The rules asserted here are money rules, not formatting taste: prices come
from rate_card.price(), never from the model (see app/services/plan.py), so
the block must carry the stored figures verbatim and tell the model not to
re-price anything. Pure function, no DB — the loading half
(plan_context_for_plan) is covered in tests/integration/.
"""
from __future__ import annotations

from app.services.plan import build_plan_context


def _body() -> dict:
    return {
        "core_idea": "วางตำแหน่งแบรนด์ใหม่ให้จับกลุ่มคนทำงานรุ่นใหม่",
        "analogous_case": "คล้ายกับที่ทำให้แบรนด์ A",
        "adapted_plan": [
            {"period": "สัปดาห์ 1-2", "text": "เวิร์กช็อป positioning"},
            {"period": "สัปดาห์ 3-6", "text": "ผลิตคอนเทนต์"},
        ],
    }


def _budget() -> dict:
    return {
        "lines": [
            {
                "code": "WS-01", "label": "Positioning workshop", "section": "Strategy",
                "unit": "flat", "qty": "1", "unit_price": "80000.00", "amount": "80000.00",
            },
            {
                "code": "CONTENT-02", "label": "Content production", "section": None,
                "unit": "piece", "qty": "12", "unit_price": "5000.00", "amount": "60000.00",
            },
        ],
        "needs_expert": [{"code": "TVC-01", "qty": "1"}],
        "subtotal": "140000.00",
        "contingency": "14000.00",
        "total": "154000.00",
        "currency": "THB",
    }


def _provenance() -> dict:
    return {
        "rate_card_codes": ["WS-01", "CONTENT-02"],
        "case_files": [{"file_id": "f1", "filename": "case-brand-a.md", "score": 0.82}],
        "research_run_id": "r1",
        "research_sources": [{"source": "https://example.com/1"}, {"source": "https://example.com/2"}],
    }


def test_block_carries_identity_and_every_stored_figure():
    block = build_plan_context(
        title="แผนกลยุทธ์แบรนด์ 2026",
        version_no=3,
        body=_body(),
        budget=_budget(),
        provenance=_provenance(),
    )

    # Which plan, and which version of it — a revision must not read as v1.
    assert "แผนกลยุทธ์แบรนด์ 2026" in block
    assert "version 3" in block

    # Narrative sections.
    assert "วางตำแหน่งแบรนด์ใหม่ให้จับกลุ่มคนทำงานรุ่นใหม่" in block
    assert "คล้ายกับที่ทำให้แบรนด์ A" in block
    for period, text in (("สัปดาห์ 1-2", "เวิร์กช็อป positioning"), ("สัปดาห์ 3-6", "ผลิตคอนเทนต์")):
        assert period in block and text in block

    # Every priced line, verbatim: code, unit price, amount, and the totals.
    for figure in ("WS-01", "80000.00", "CONTENT-02", "5000.00", "60000.00",
                   "140000.00", "14000.00", "154000.00", "THB"):
        assert figure in block, figure

    # A line the rate card could not price must not look priced.
    assert "TVC-01" in block
    assert "needs an expert quote" in block

    assert "case-brand-a.md" in block
    assert "2 market-research source(s)" in block


def test_block_forbids_re_pricing_and_re_scoping():
    block = build_plan_context(
        title="Plan", version_no=1, body=_body(), budget=_budget(), provenance=None
    )
    lowered = block.lower()
    assert "quote every number exactly" in lowered
    assert "never invent, re-price or re-scope" in lowered
    assert "expert will confirm" in lowered


def test_unpriced_plan_renders_without_a_budget_section():
    """budget_out() returns None for a version with no lines and no subtotal
    (see app/services/plan.py) — that must not render an empty "Budget:"
    heading the model could read as "this plan costs nothing"."""
    block = build_plan_context(
        title="Plan", version_no=1, body=_body(), budget=None, provenance=None
    )
    assert "Budget" not in block
    assert "เวิร์กช็อป positioning" in block


def test_empty_sections_are_dropped_not_rendered_blank():
    block = build_plan_context(
        title="Plan",
        version_no=1,
        body={"core_idea": "", "analogous_case": "  ", "adapted_plan": []},
        budget=None,
        provenance={"case_files": [], "research_sources": []},
    )
    assert "Core idea:" not in block
    assert "Analogous case:" not in block
    assert "Plan:" not in block
    assert "Based on" not in block
    # The header still identifies the plan, so the model knows one exists.
    assert "version 1" in block
