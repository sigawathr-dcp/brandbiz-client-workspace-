"""Unit tests for draft_plan()'s provenance.research_sources.

The plan document's provenance rail renders real citations from the
ResearchRun a plan drew on, never invented source names (PLAN.md Phase 5
redesign notes) — so draft_plan() must copy the run's ResearchCitation rows
verbatim into provenance["research_sources"], and must not fabricate them
when there is no completed research run to draw on.

DB redesign: draft_plan() now resolves its research run via the
engagement's own step 2 record (app/services/engagement.py) rather than a
bare (workspace_id, user_id) filter — see app/services/plan.py::
_latest_done_research/_latest_case_matches, which this test patches
directly rather than replicating their internal query shape (that shape is
covered by the integration suite; this test is about provenance assembly).

Everything except the provenance assembly (agent lookup, rate card
availability, the drafting LLM call, pricing, the research/case lookups
themselves) is mocked out.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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


def _prepared():
    p = MagicMock()
    p.resolved_conversation_id = uuid.uuid4()
    p.model_code = "gemma4:26b"
    p.history = []
    p.downgrade_to_local = False
    p.reasons = []
    p.image_model_code = None
    p.n8n_route = None
    p.rag_context = ""
    p.citations = []
    p.system_prompt = ""
    p.temperature = 0.5
    return p


def _collect_result() -> dict:
    payload = {
        "title": "Plan title",
        "core_idea": "idea",
        "analogous_case": "case",
        "adapted_plan": [{"period": "Wk 1-2", "text": "..."}],
        "budget_items": [{"code": "R1", "qty": 1}],
    }
    return {"output": json.dumps(payload)}


def _priced_budget() -> dict:
    return {
        "lines": [{"code": "R1", "label": "Positioning workshop", "section": None,
                    "unit": "flat", "qty": "1", "unit_price": "1000.00", "amount": "1000.00"}],
        "needs_expert": [], "subtotal": "1000.00", "contingency": "100.00",
        "total": "1100.00", "currency": "THB",
    }


@pytest.mark.asyncio
async def test_research_sources_copies_real_citations():
    workspace_id = uuid.uuid4()
    user = MagicMock()
    user.id = uuid.uuid4()
    engagement = _engagement()
    fields = {"industry": "Retail + online"}

    research = MagicMock()
    research.id = uuid.uuid4()

    citation = MagicMock()
    citation.url = "example.com"
    citation_result = MagicMock()
    citation_result.scalars.return_value.all.return_value = [citation]
    session = AsyncMock()
    session.execute = AsyncMock(return_value=citation_result)

    with (
        patch.object(plan_svc.workspace_svc, "get_workspace_agent", new=AsyncMock(return_value=_agent())),
        patch.object(plan_svc, "_available_rate_card", new=AsyncMock(return_value=[_rate_item()])),
        patch.object(plan_svc, "_latest_done_research", new=AsyncMock(return_value=research)),
        patch.object(plan_svc, "_research_finding_texts", new=AsyncMock(return_value=["finding"])),
        patch.object(plan_svc, "_latest_case_matches", new=AsyncMock(return_value=[])),
        patch.object(plan_svc, "prepare_chat", new=AsyncMock(return_value=_prepared())),
        patch.object(plan_svc, "run_chat_collect", new=AsyncMock(return_value=_collect_result())),
        patch.object(plan_svc.rate_card_svc, "price", new=AsyncMock(return_value=_priced_budget())),
    ):
        result = await plan_svc.draft_plan(session, user, workspace_id, engagement, fields)

    assert result["provenance"]["research_sources"] == [{"index": 1, "source": "example.com"}]
    assert result["provenance"]["research_run_id"] == str(research.id)


@pytest.mark.asyncio
async def test_research_sources_empty_when_no_completed_research_run():
    workspace_id = uuid.uuid4()
    user = MagicMock()
    user.id = uuid.uuid4()
    engagement = _engagement()
    fields = {"industry": "Retail + online"}

    session = AsyncMock()

    with (
        patch.object(plan_svc.workspace_svc, "get_workspace_agent", new=AsyncMock(return_value=_agent())),
        patch.object(plan_svc, "_available_rate_card", new=AsyncMock(return_value=[_rate_item()])),
        patch.object(plan_svc, "_latest_done_research", new=AsyncMock(return_value=None)),  # no run yet
        patch.object(plan_svc, "_latest_case_matches", new=AsyncMock(return_value=[])),
        patch.object(plan_svc, "prepare_chat", new=AsyncMock(return_value=_prepared())),
        patch.object(plan_svc, "run_chat_collect", new=AsyncMock(return_value=_collect_result())),
        patch.object(plan_svc.rate_card_svc, "price", new=AsyncMock(return_value=_priced_budget())),
    ):
        result = await plan_svc.draft_plan(session, user, workspace_id, engagement, fields)

    assert result["provenance"]["research_sources"] == []
    assert result["provenance"]["research_run_id"] is None
