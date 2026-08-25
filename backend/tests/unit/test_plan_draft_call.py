"""Unit tests for HOW draft_plan() calls the model — the two ways the call
used to come back unusable and 502 the endpoint.

1. It sent prepared.history. Every draft persists its own ~8k-char prompt and
   its raw JSON reply into the same conversation, so after a few drafts the
   last-20-messages window alone filled the local model's context window; the
   server then had no budget left to generate and answered with an EMPTY
   string, which surfaced to the client as "couldn't draft a plan just now".
   The prompt is self-contained, so the transcript is dropped.

2. It ran under the workspace agent's chat instructions alone ("be friendly,
   ask one question at a time"). Handed a client profile with a messy free-text
   answer, the agent did as told — it greeted the client and asked follow-up
   questions instead of emitting JSON. A task-mode block is appended after the
   agent's own instructions so the framing is the last thing the model reads.

Everything else (agent lookup, rate card, pricing, research/case lookups) is
mocked out — this is about the call, not the assembly.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.llm.base import LLMProviderError
from app.services import plan as plan_svc


def _agent():
    a = MagicMock()
    a.id = uuid.uuid4()
    return a


def _engagement():
    e = MagicMock()
    e.id = uuid.uuid4()
    e.conversation_id = uuid.uuid4()
    return e


def _rate_item(code: str = "R1"):
    r = MagicMock()
    r.code = code
    r.label = "Positioning workshop"
    r.unit = "flat"
    r.currency = "THB"
    r.unit_price = 1000
    return r


def _prepared(history: list[dict] | None = None, system_prompt: str = ""):
    p = MagicMock()
    p.resolved_conversation_id = uuid.uuid4()
    p.model_code = "gemma4:26b"
    p.history = history if history is not None else [
        {"role": "user", "content": "x" * 9000},
        {"role": "assistant", "content": "y" * 9000},
    ]
    p.downgrade_to_local = False
    p.reasons = []
    p.image_model_code = None
    p.n8n_route = None
    p.rag_context = ""
    p.citations = []
    p.system_prompt = system_prompt
    return p


def _collect_result() -> dict:
    return {"output": json.dumps({
        "title": "Plan title",
        "core_idea": "idea",
        "analogous_case": "case",
        "adapted_plan": [{"period": "Wk 1-2", "text": "..."}],
        "budget_items": [{"code": "R1", "qty": 1}],
    })}


def _priced_budget() -> dict:
    return {
        "lines": [{"code": "R1", "label": "Positioning workshop", "section": None,
                   "unit": "flat", "qty": "1", "unit_price": "1000.00", "amount": "1000.00"}],
        "needs_expert": [], "subtotal": "1000.00", "contingency": "100.00",
        "total": "1100.00", "currency": "THB",
    }


def _plan_step():
    s = MagicMock()
    s.id = uuid.uuid4()
    return s


def _patches(prepared, collect: AsyncMock, plan_step):
    return (
        patch.object(plan_svc.workspace_svc, "get_workspace_agent", new=AsyncMock(return_value=_agent())),
        patch.object(plan_svc, "_available_rate_card", new=AsyncMock(return_value=[_rate_item()])),
        patch.object(plan_svc, "_latest_done_research", new=AsyncMock(return_value=None)),
        patch.object(plan_svc, "_latest_case_matches", new=AsyncMock(return_value=[])),
        patch.object(plan_svc.engagement_svc, "get_step", new=AsyncMock(return_value=plan_step)),
        patch.object(plan_svc, "prepare_chat", new=AsyncMock(return_value=prepared)),
        patch.object(plan_svc, "run_chat_collect", new=collect),
        patch.object(plan_svc.rate_card_svc, "price", new=AsyncMock(return_value=_priced_budget())),
    )


async def _draft(prepared, collect: AsyncMock, plan_step=None):
    p1, p2, p3, p4, p5, p6, p7, p8 = _patches(prepared, collect, plan_step or _plan_step())
    with p1, p2, p3, p4, p5, p6, p7, p8:
        return await plan_svc.draft_plan(
            AsyncMock(), MagicMock(id=uuid.uuid4()), uuid.uuid4(), _engagement(),
            {"industry": "Retail + online"},
        )


@pytest.mark.asyncio
async def test_drafting_call_sends_no_conversation_history():
    collect = AsyncMock(return_value=_collect_result())
    prepared = _prepared()

    await _draft(prepared, collect)

    assert collect.await_args.kwargs["history"] == []
    # prepare_chat still saw the full transcript — classification and the
    # PolicyEngine decision must stay conservative (§7.6).
    assert len(prepared.history) == 2


@pytest.mark.asyncio
async def test_drafting_call_appends_task_mode_after_agent_instructions():
    collect = AsyncMock(return_value=_collect_result())
    agent_voice = "คุณคือ น้อง brandbiz ... ถามทีละคำถาม"

    await _draft(_prepared(system_prompt=agent_voice), collect)

    sent = collect.await_args.kwargs["system_prompt"]
    assert sent.startswith(agent_voice)          # the agent's voice survives
    assert sent.endswith(plan_svc._DRAFTING_OVERRIDE)  # ...but task framing reads last


@pytest.mark.asyncio
async def test_drafting_call_task_mode_stands_alone_without_an_agent_prompt():
    collect = AsyncMock(return_value=_collect_result())

    await _draft(_prepared(system_prompt=""), collect)

    assert collect.await_args.kwargs["system_prompt"] == plan_svc._DRAFTING_OVERRIDE


@pytest.mark.asyncio
async def test_drafting_call_tags_its_messages_with_the_plan_step():
    """Both persisted rows carry engagement_step_id, so bootstrap's
    transcript replay (app/routers/client.py::_chat_transcript, which filters
    on engagement_step_id IS NULL) leaves the ~8k-char drafting prompt and the
    raw JSON reply out of the client's chat thread."""
    collect = AsyncMock(return_value=_collect_result())
    plan_step = _plan_step()

    await _draft(_prepared(), collect, plan_step)

    assert collect.await_args.kwargs["engagement_step_id"] == plan_step.id


@pytest.mark.asyncio
async def test_provider_failure_becomes_a_502_not_a_500():
    """A context-window overflow now raises out of the adapter instead of
    returning "" — the client must still get the friendly retry message rather
    than an unhandled 500."""
    collect = AsyncMock(side_effect=LLMProviderError("prompt used 15667 tokens"))

    with pytest.raises(HTTPException) as excinfo:
        await _draft(_prepared(), collect)

    assert excinfo.value.status_code == 502
