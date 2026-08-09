"""
app/services/plan.py

Draft + persist Plans (Phase 5 §4, D21/D22) — the 4-part plan promoted out
of chat into a standalone, versioned artifact (see app/models/plan.py for
why it lives outside messages.content_*).

draft_plan() asks the workspace's agent for narrative sections PLUS rate-
card item codes — never a price. The price is computed by
app/services/rate_card.py::price(), never the model; a hallucinated budget
in front of a real prospect is worse than no budget (see PLAN.md Phase 5).

The drafting call itself goes through the exact same governance as any
other chat turn (prepare_chat + run_chat_collect drives the same LangGraph
as POST /client/chat) — quota, audit, and message encryption for that turn
are handled there, unchanged. Only the resulting Plan row gets its own
plan_created/plan_updated/plan_shared audit trail, since a Plan is a
distinct artifact from the chat turn that produced it.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import uuid

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import crypto
from app.agents.orchestrator import run_chat_collect
from app.models.client_intake import CaseMatch, ResearchRun
from app.models.plan import Plan, PlanVersion
from app.models.rate_card import RateCardItem
from app.models.user import User
from app.services import audit as audit_svc
from app.services import rate_card as rate_card_svc
from app.services import workspace as workspace_svc
from app.services.chat_policy import prepare_chat

_logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict:
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        raise ValueError("no JSON object found in model output")
    return json.loads(match.group(0))


async def _available_rate_card(session: AsyncSession, workspace_id: uuid.UUID) -> list[RateCardItem]:
    result = await session.execute(
        select(RateCardItem).where(
            RateCardItem.active.is_(True),
            or_(RateCardItem.workspace_id == workspace_id, RateCardItem.workspace_id.is_(None)),
        )
    )
    return list(result.scalars().all())


def _build_drafting_prompt(fields: dict, research: ResearchRun | None, cases: list[CaseMatch], rate_items: list[RateCardItem]) -> str:
    context_lines = [f"{k}: {v}" for k, v in fields.items()]
    research_lines = [f["text"] for f in (research.findings or [])] if research else []
    case_lines = [f"{c.filename} (match {round(c.score, 2)}): {c.rationale}" for c in cases]
    rate_lines = [f"{r.code} — {r.label} ({r.unit or 'unit'}, {r.currency} {r.unit_price})" for r in rate_items]

    return (
        "Draft a 4-part brand strategy plan for this client, in the exact JSON shape below. "
        "Respond with ONLY the JSON object, no prose outside it.\n\n"
        "Client context:\n" + "\n".join(context_lines) + "\n\n"
        "Market research findings:\n" + ("\n".join(research_lines) or "(none)") + "\n\n"
        "Closest matching Brandbiz case studies:\n" + ("\n".join(case_lines) or "(none)") + "\n\n"
        "Available rate-card items — use ONLY these codes in budget_items; never invent a "
        "code, never state a price yourself, the price is computed separately:\n"
        + "\n".join(rate_lines) + "\n\n"
        "JSON shape:\n"
        "{\n"
        '  "title": "short plan title",\n'
        '  "core_idea": "1-2 sentences",\n'
        '  "analogous_case": "1-2 sentences referencing the closest case study",\n'
        '  "adapted_plan": [{"period": "Wk 1-2", "text": "..."}, ...],\n'
        '  "budget_items": [{"code": "<a code from the list above>", "qty": 1}, ...]\n'
        "}"
    )


async def draft_plan(
    session: AsyncSession,
    user: User,
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    fields: dict,
) -> dict:
    """Returns {"title","core_idea","analogous_case","adapted_plan","budget","provenance","conversation_id"}.

    workspace_id is passed explicitly rather than read off user.workspace_id
    — a staff member previewing the funnel (app/deps.py::ClientContext)
    has workspace_id=None on their own row but drafts against the demo
    workspace, so the two can legitimately differ."""
    agent = await workspace_svc.get_workspace_agent(session, workspace_id)
    if agent is None:
        _logger.warning("draft_plan: workspace %s has no assigned agent", workspace_id)
        raise HTTPException(status_code=503, detail="This workspace has no assigned agent yet")

    rate_items = await _available_rate_card(session, workspace_id)
    if not rate_items:
        _logger.warning("draft_plan: workspace %s has no active rate card items", workspace_id)
        raise HTTPException(status_code=503, detail="No rate card is configured for this workspace yet")

    research = (await session.execute(
        select(ResearchRun)
        .where(
            ResearchRun.workspace_id == workspace_id,
            ResearchRun.user_id == user.id,
            ResearchRun.status == "done",
        )
        .order_by(ResearchRun.created_at.desc())
    )).scalars().first()
    case_rows = list((await session.execute(
        select(CaseMatch)
        .where(CaseMatch.workspace_id == workspace_id, CaseMatch.user_id == user.id)
        .order_by(CaseMatch.score.desc())
        .limit(3)
    )).scalars().all())

    prompt = _build_drafting_prompt(fields, research, case_rows, rate_items)

    prepared = await prepare_chat(
        session=session,
        user=user,
        conversation_id=conversation_id,
        user_content=prompt,
        requested_model="auto",
        agent_id=agent.id,
        workspace_id=workspace_id,
    )
    result = await run_chat_collect(
        session=session,
        user_id=user.id,
        user=user,
        resolved_conversation_id=prepared.resolved_conversation_id,
        user_content=prompt,
        model_code=prepared.model_code,
        history=prepared.history,
        downgrade_to_local=prepared.downgrade_to_local,
        reasons=prepared.reasons,
        image_model_code=prepared.image_model_code,
        n8n_route=prepared.n8n_route,
        rag_context=prepared.rag_context,
        citations=prepared.citations,
        system_prompt=prepared.system_prompt,
        tuning=prepared.tuning,
    )

    try:
        parsed = _extract_json(result["output"])
    except (ValueError, json.JSONDecodeError) as exc:
        # Never log the model output or the prompt here — both embed decrypted
        # client profile fields and research findings (PLAN.md §7.1). Log the
        # shape only.
        output = result.get("output") or ""
        _logger.warning(
            "draft_plan: model output not parseable as JSON (workspace=%s, output_len=%d, has_brace=%s)",
            workspace_id,
            len(output),
            "{" in output,
        )
        raise HTTPException(
            status_code=502, detail="น้องภูมิ could not draft a plan just now — please try again."
        ) from exc

    budget_items = parsed.get("budget_items") or []
    budget = await rate_card_svc.price(session, workspace_id, budget_items)

    provenance = {
        "rate_card_codes": [li["code"] for li in budget["lines"]],
        "case_files": [
            {"file_id": str(c.file_id), "filename": c.filename, "score": c.score} for c in case_rows
        ],
        "research_run_id": str(research.id) if research else None,
        # Real citations from the ResearchRun this plan drew on — the plan
        # document's provenance rail renders exactly this list, never
        # invented source names (PLAN.md Phase 5 redesign notes).
        "research_sources": list(research.citations or []) if research else [],
    }

    return {
        "title": (parsed.get("title") or "Brand strategy plan")[:500],
        "core_idea": parsed.get("core_idea") or "",
        "analogous_case": parsed.get("analogous_case") or "",
        "adapted_plan": parsed.get("adapted_plan") or [],
        "budget": budget,
        "provenance": provenance,
        "conversation_id": str(prepared.resolved_conversation_id),
    }


async def save_plan(
    session: AsyncSession, user: User, workspace_id: uuid.UUID, conversation_id: uuid.UUID | None, draft: dict
) -> Plan:
    body = {
        "core_idea": draft["core_idea"],
        "analogous_case": draft["analogous_case"],
        "adapted_plan": draft["adapted_plan"],
    }
    ct, nonce, tag, kv = crypto.encrypt(json.dumps(body))

    plan = Plan(
        workspace_id=workspace_id,
        user_id=user.id,
        conversation_id=conversation_id,
        title=draft["title"],
        version=1,
        status="draft",
        body_ciphertext=ct,
        body_nonce=nonce,
        body_tag=tag,
        key_version=kv,
        budget=draft["budget"],
        provenance=draft["provenance"],
    )
    session.add(plan)
    await session.flush()

    session.add(PlanVersion(
        plan_id=plan.id, version=1,
        body_ciphertext=ct, body_nonce=nonce, body_tag=tag, key_version=kv,
        budget=draft["budget"],
    ))
    await session.commit()
    await session.refresh(plan)

    await audit_svc.log(
        action="plan_created",
        user_id=user.id,
        resource_type="plan",
        resource_id=plan.id,
        details={"workspace_id": str(workspace_id), "title": plan.title},
    )
    return plan


def decrypt_body(plan: Plan) -> dict:
    raw = crypto.decrypt(plan.body_ciphertext, plan.body_nonce, plan.body_tag, plan.key_version)
    return json.loads(raw)


async def list_plans(session: AsyncSession, user: User, workspace_id: uuid.UUID) -> list[Plan]:
    result = await session.execute(
        select(Plan)
        .where(Plan.workspace_id == workspace_id, Plan.user_id == user.id)
        .order_by(Plan.created_at.desc())
    )
    return list(result.scalars().all())


async def get_plan(session: AsyncSession, user: User, workspace_id: uuid.UUID, plan_id: uuid.UUID) -> Plan:
    plan = (await session.execute(
        select(Plan).where(
            Plan.id == plan_id, Plan.workspace_id == workspace_id, Plan.user_id == user.id
        )
    )).scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


async def list_versions(session: AsyncSession, plan_id: uuid.UUID) -> list[PlanVersion]:
    """Backs the plan document's Versions panel. save_plan() writes exactly
    one PlanVersion row today (nothing updates a saved plan yet) — callers
    must render only what comes back here, not a fabricated v2+."""
    result = await session.execute(
        select(PlanVersion).where(PlanVersion.plan_id == plan_id).order_by(PlanVersion.version.asc())
    )
    return list(result.scalars().all())


async def create_share_token(
    session: AsyncSession, user: User, workspace_id: uuid.UUID, plan_id: uuid.UUID
) -> str:
    """Phase 6 (Export/share) — defined here since it's tightly coupled to
    Plan, wired into a router once the share-link page exists."""
    plan = await get_plan(session, user, workspace_id, plan_id)
    raw = "plan_" + secrets.token_urlsafe(24)
    plan.share_token_hash = hashlib.sha256(raw.encode()).hexdigest()
    await session.commit()
    await audit_svc.log(
        action="plan_shared", user_id=user.id, resource_type="plan", resource_id=plan.id,
    )
    return raw


async def get_plan_by_share_token(session: AsyncSession, raw_token: str) -> Plan:
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    plan = (await session.execute(
        select(Plan).where(Plan.share_token_hash == token_hash)
    )).scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="This plan link is not valid")
    return plan
