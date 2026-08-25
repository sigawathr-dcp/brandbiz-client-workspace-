"""Unit tests for chat-driven plan edits — plan_svc.revise_from_instruction()
and the two pure helpers it leans on.

Sibling file: test_plan_revise.py covers revise_plan(), the persistence half
this one calls at the end (version numbering, current_version_id, status never
changing, the audit row). Everything up to that call is here.

What these pin, in order of how much they'd cost to get wrong:

1. Money. A revision must re-price through rate_card.price() from codes the
   model returned, never carry a number the model wrote. Same rule draft_plan()
   follows (services/plan.py module docstring).
2. The call shape. history=[] and an engagement-step stamp, for the reasons
   test_plan_draft_call.py spells out — and because an UNstamped raw-JSON reply
   lands back in the free-form chat window, which is the exact bug that made
   the chat box answer with a JSON blob (chat_policy.load_history_messages).
3. Drift. Re-drafting under an instruction is the design, so a revision CAN
   quietly reword sections nobody asked about. diff_versions() is what makes
   that visible instead of silent, so it gets tested like a feature, not a
   formatting detail.

DB-free — the assembly around the call (agent lookup, rate card, version
loading, persistence) is mocked, same as test_plan_draft_call.py.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import plan as plan_svc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _rate_item(code: str = "R1", label: str = "Positioning workshop"):
    r = MagicMock()
    r.code = code
    r.label = label
    r.unit = "flat"
    r.currency = "THB"
    r.unit_price = 1000
    return r


def _engagement():
    e = MagicMock()
    e.id = uuid.uuid4()
    e.conversation_id = uuid.uuid4()
    return e


def _prepared(system_prompt: str = ""):
    p = MagicMock()
    p.resolved_conversation_id = uuid.uuid4()
    p.model_code = "gemma4:26b"
    p.history = [{"role": "user", "content": "x" * 9000}]
    p.downgrade_to_local = False
    p.reasons = []
    p.image_model_code = None
    p.n8n_route = None
    p.rag_context = ""
    p.citations = []
    p.system_prompt = system_prompt
    return p


def _base_version(version_no: int = 2, title: str = "แผนกลยุทธ์แบรนด์"):
    v = MagicMock()
    v.title = title
    v.version_no = version_no
    return v


_BASE_BODY = {
    "core_idea": "สร้างความน่าเชื่อถือ",
    "analogous_case": "อ้างอิงเคส A",
    "adapted_plan": [{"period": "เดือนที่ 1-3", "text": "ทำ Brand Audit"}],
}

_BASE_BUDGET = {
    "lines": [
        {"code": "R1", "label": "Positioning workshop", "section": None, "unit": "flat",
         "qty": "1", "unit_price": "1000.00", "amount": "1000.00"},
        {"code": "R2", "label": "Content production", "section": None, "unit": "month",
         "qty": "3", "unit_price": "2000.00", "amount": "6000.00"},
    ],
    "needs_expert": [],
    "subtotal": "7000.00", "contingency": "700.00", "total": "7700.00", "currency": "THB",
}


def _model_reply(budget_items=None) -> dict:
    """What the model returns — codes and quantities, never a price."""
    return {"output": json.dumps({
        "title": "แผนกลยุทธ์แบรนด์",
        "core_idea": "สร้างความน่าเชื่อถือ",
        "analogous_case": "อ้างอิงเคส A",
        "adapted_plan": [{"period": "เดือนที่ 1-3", "text": "ทำ Brand Audit"}],
        "budget_items": budget_items or [{"code": "R1", "qty": 1}, {"code": "R2", "qty": 5}],
    }, ensure_ascii=False)}


def _repriced() -> dict:
    """rate_card.price()'s answer — the ONLY source of the numbers below."""
    return {
        "lines": [
            {"code": "R1", "label": "Positioning workshop", "section": None, "unit": "flat",
             "qty": "1", "unit_price": "1000.00", "amount": "1000.00"},
            {"code": "R2", "label": "Content production", "section": None, "unit": "month",
             "qty": "5", "unit_price": "2000.00", "amount": "10000.00"},
        ],
        "needs_expert": [],
        "subtotal": "11000.00", "contingency": "1100.00", "total": "12100.00", "currency": "THB",
    }


def _plan_step():
    s = MagicMock()
    s.id = uuid.uuid4()
    return s


async def _revise(
    *,
    collect: AsyncMock,
    prepared=None,
    plan_step=None,
    base_provenance=None,
    price=None,
):
    plan = MagicMock(id=uuid.uuid4())
    revise_plan = AsyncMock(return_value=plan)
    step = plan_step or _plan_step()
    with patch.object(plan_svc.workspace_svc, "get_workspace_agent", new=AsyncMock(return_value=MagicMock(id=uuid.uuid4()))), \
            patch.object(plan_svc, "_available_rate_card", new=AsyncMock(return_value=[_rate_item(), _rate_item("R2", "Content production")])), \
            patch.object(plan_svc, "get_current_version", new=AsyncMock(side_effect=[_base_version(2), _base_version(3)])), \
            patch.object(plan_svc, "decrypt_body", new=MagicMock(return_value=dict(_BASE_BODY))), \
            patch.object(plan_svc, "budget_out", new=AsyncMock(side_effect=[_BASE_BUDGET, price or _repriced()])), \
            patch.object(plan_svc, "provenance_out", new=AsyncMock(return_value=base_provenance if base_provenance is not None else {})), \
            patch.object(plan_svc.engagement_svc, "get_step", new=AsyncMock(return_value=step)), \
            patch.object(plan_svc, "prepare_chat", new=AsyncMock(return_value=prepared or _prepared())), \
            patch.object(plan_svc, "run_chat_collect", new=collect), \
            patch.object(plan_svc.rate_card_svc, "price", new=AsyncMock(return_value=price or _repriced())), \
            patch.object(plan_svc, "revise_plan", new=revise_plan):
        result = await plan_svc.revise_from_instruction(
            AsyncMock(), MagicMock(id=uuid.uuid4()), uuid.uuid4(), _engagement(), plan,
            "เพิ่ม content production เป็น 5 เดือน",
        )
    return result, revise_plan, step


# ---------------------------------------------------------------------------
# The call shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_revision_call_sends_no_conversation_history():
    """The prompt carries the whole plan, so the transcript adds nothing — and
    it is the one input that grows without bound (test_plan_draft_call.py)."""
    collect = AsyncMock(return_value=_model_reply())
    prepared = _prepared()

    await _revise(collect=collect, prepared=prepared)

    assert collect.await_args.kwargs["history"] == []
    # prepare_chat still saw the transcript — §7.6 classification stays over
    # the full payload.
    assert len(prepared.history) == 1


@pytest.mark.asyncio
async def test_revision_turn_is_stamped_with_the_plan_step():
    """Unstamped, the ~8k prompt and the raw JSON reply rejoin the free-form
    chat window and the model starts imitating the JSON in chat — the exact
    bug chat_policy.load_history_messages was split in two to fix."""
    collect = AsyncMock(return_value=_model_reply())
    step = _plan_step()

    await _revise(collect=collect, plan_step=step)

    assert collect.await_args.kwargs["engagement_step_id"] == step.id


@pytest.mark.asyncio
async def test_revision_appends_task_mode_after_agent_instructions():
    """The agent's chat voice ("ถามทีละคำถาม") would otherwise have it ask a
    follow-up question instead of emitting JSON."""
    collect = AsyncMock(return_value=_model_reply())
    agent_voice = "คุณคือ น้อง brandbiz ... ถามทีละคำถาม"

    await _revise(collect=collect, prepared=_prepared(system_prompt=agent_voice))

    system_prompt = collect.await_args.kwargs["system_prompt"]
    assert system_prompt.startswith(agent_voice)
    assert system_prompt.endswith(plan_svc._DRAFTING_OVERRIDE)


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_budget_comes_from_the_rate_card_not_the_model():
    """The model is asked for {code, qty} and nothing else; every amount in the
    result must be one rate_card.price() produced."""
    collect = AsyncMock(return_value=_model_reply())

    result, _revise_plan, _step = await _revise(collect=collect)

    # Read back off the persisted version, so the card and a later reload show
    # the same numbers — and they are rate_card.price()'s, not the model's.
    assert result["budget"] == _repriced()
    # The prompt must not invite a price at all.
    prompt = collect.await_args.kwargs["user_content"]
    assert "never state a price yourself" in prompt


@pytest.mark.asyncio
async def test_revision_is_committed_as_the_next_version():
    """No intermediate unsaved draft: the confirmation chip already happened,
    and PlanVersion is the undo."""
    collect = AsyncMock(return_value=_model_reply())

    result, revise_plan, _step = await _revise(collect=collect)

    revise_plan.assert_awaited_once()
    # The version number is read back off the PERSISTED version, not guessed.
    assert result["version"] == 3


@pytest.mark.asyncio
async def test_instruction_is_carried_into_the_version_body():
    """revision_note rides inside the ENCRYPTED body (§7.1) so the version
    history can say why v3 differs from v2 — it must never become an audit
    details blob."""
    collect = AsyncMock(return_value=_model_reply())

    _result, revise_plan, _step = await _revise(collect=collect)

    draft = revise_plan.await_args.args[-1]
    assert draft["revision_note"] == "เพิ่ม content production เป็น 5 เดือน"


@pytest.mark.asyncio
async def test_provenance_is_carried_forward_not_re_resolved():
    """A revision draws on the SAME research run and case studies the original
    drew on; re-running the lookups would silently re-point the plan at
    whatever happens to be newest now. Only rate-card codes are recomputed."""
    collect = AsyncMock(return_value=_model_reply())
    base = {
        "case_files": [{"file_id": str(uuid.uuid4()), "filename": "case-a.pdf", "score": 0.8}],
        "research_run_id": str(uuid.uuid4()),
        "research_sources": [{"index": 1, "source": "https://example.test"}],
        "rate_card_codes": ["R1", "R2"],
    }

    _result, revise_plan, _step = await _revise(collect=collect, base_provenance=base)

    prov = revise_plan.await_args.args[-1]["provenance"]
    assert prov["case_files"] == base["case_files"]
    assert prov["research_run_id"] == base["research_run_id"]
    assert prov["research_sources"] == base["research_sources"]
    # ...recomputed from the NEW budget, not copied.
    assert prov["rate_card_codes"] == ["R1", "R2"]


# ---------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------

def test_revision_prompt_carries_the_current_plan_in_the_reply_shape():
    """Rendering the current plan in the shape the model must return makes
    "change only what was asked" a copy, not a reconstruction — the cheapest
    defence against drift there is."""
    prompt = plan_svc._build_revision_prompt(
        title="แผนกลยุทธ์แบรนด์",
        body=_BASE_BODY,
        budget=_BASE_BUDGET,
        rate_items=[_rate_item()],
        instruction="ตัดเฟส 4 ออก",
    )

    assert "Change ONLY what the instruction asks for" in prompt
    assert "ตัดเฟส 4 ออก" in prompt
    assert "แผนกลยุทธ์แบรนด์" in prompt
    # The base budget goes back as codes+qty, never as the amounts it priced to.
    assert '"code": "R1"' in prompt
    assert "1000.00" not in prompt
    # The rate card is the only budget vocabulary allowed.
    assert "Positioning workshop" in prompt


def test_budget_items_round_trip_includes_needs_expert_lines():
    """A code with no rate-card match is still part of the plan; dropping it on
    the way into a revision would silently delete scope."""
    budget = {
        "lines": [{"code": "R1", "qty": "1"}],
        "needs_expert": [{"code": "R9", "qty": "2"}],
    }
    assert plan_svc._budget_items_of(budget) == [
        {"code": "R1", "qty": "1"},
        {"code": "R9", "qty": "2"},
    ]


# ---------------------------------------------------------------------------
# Drift
# ---------------------------------------------------------------------------

def test_diff_reports_narrative_fields_that_changed():
    diff = plan_svc.diff_versions(
        base_title="A", base_body=_BASE_BODY, base_budget=_BASE_BUDGET,
        new_title="B", new_body={**_BASE_BODY, "core_idea": "ใหม่"}, new_budget=_BASE_BUDGET,
    )
    assert diff["fields"] == ["title", "core_idea"]


def test_diff_reports_unasked_drift():
    """The whole point: the client asked about the budget, and the model also
    reworded core_idea. The card has to be able to say so."""
    diff = plan_svc.diff_versions(
        base_title="A", base_body=_BASE_BODY, base_budget=_BASE_BUDGET,
        new_title="A", new_body={**_BASE_BODY, "core_idea": "เขียนใหม่โดยไม่ได้ขอ"},
        new_budget=_repriced(),
    )
    assert "core_idea" in diff["fields"]
    assert diff["budget"]["qty_changed"] == [
        {"code": "R2", "label": "Content production", "from": "3", "to": "5"}
    ]


def test_diff_reports_added_and_removed_budget_lines_with_totals():
    new_budget = {
        "lines": [{"code": "R3", "label": "PR retainer", "qty": "1", "amount": "5000.00"}],
        "needs_expert": [], "total": "5500.00",
    }
    diff = plan_svc.diff_versions(
        base_title="A", base_body=_BASE_BODY, base_budget=_BASE_BUDGET,
        new_title="A", new_body=_BASE_BODY, new_budget=new_budget,
    )
    assert [li["code"] for li in diff["budget"]["added"]] == ["R3"]
    assert sorted(li["code"] for li in diff["budget"]["removed"]) == ["R1", "R2"]
    assert diff["budget"]["total_before"] == "7700.00"
    assert diff["budget"]["total_after"] == "5500.00"


def test_diff_of_an_untouched_plan_is_empty():
    diff = plan_svc.diff_versions(
        base_title="A", base_body=_BASE_BODY, base_budget=_BASE_BUDGET,
        new_title="A", new_body=_BASE_BODY, new_budget=_BASE_BUDGET,
    )
    assert diff["fields"] == []
    assert diff["budget"]["added"] == []
    assert diff["budget"]["removed"] == []
    assert diff["budget"]["qty_changed"] == []
