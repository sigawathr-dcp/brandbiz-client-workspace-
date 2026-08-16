"""
app/routers/client.py

Client-workspace endpoints (Phase 5 §3-4, D21/D22; restructured by the
"Client Workspace — Database Redesign" plan) — require_client_context-gated
(a real client seat uses its own workspace; internal staff with no
workspace of their own preview the seeded demo workspace instead — see
app/deps.py::ClientContext):
  GET  /client/bootstrap      — workspace, agent, engagement journey
  POST /client/engagements    — start a fresh engagement (a returning
                                    client's second brief)
  POST /client/intake/answer  — record an answer, return the next step
  PATCH /client/intake/fields — correct an already-answered field (Task 5.11)
  POST /client/chat            — chat with the workspace's agent (SSE)
  POST /client/research        — run the market scan (Perplexity)
  POST /client/cases           — match against the case library (RAG)
  POST /client/plan/draft      — draft a plan (not saved yet)
  POST /client/plans           — save a drafted plan as an artifact
  PUT  /client/plans/{id}      — save a re-drafted plan as the next version
                                    of an existing plan (Task 5.11)
  GET  /client/plans           — list this seat's saved plans
  GET  /client/plans/{id}      — one plan, decrypted
  GET  /client/plans/{id}/versions/{v} — one historical version's body, read-only (Task 5.12)
  POST /client/plans/{id}/rating — rate a plan (upserted; surfaced on the
                                    expert leads inbox, app/routers/admin_leads.py)

Every governance path (PolicyEngine.decide, quota, audit, encryption) is
inherited unchanged from the internal chat path — this router only decides
WHICH agent a client seat's chat is forced through; it never bypasses how
that call is gated.

DB redesign summary: every step's state now lives on one
app.models.engagement.EngagementStep row (see app/services/engagement.py),
replacing three separate status vocabularies and the old bootstrap helper
that queried audit_log as if it were application state to tell "case
matching never ran" from "ran, found zero matches". Interview answers are
now rows (app/models/intake.py::IntakeAnswer) instead of one encrypted
JSON blob.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import crypto
from app.agents.orchestrator import _compute_cost, run_chat_stream
from app.config import settings
from app.db import get_db
from app.deps import ClientContext, require_client_context
from app.llm.base import ChatMessage
from app.llm.router import PERPLEXITY_MODEL_CODE, get_router
from app.models.client_intake import (
    CaseMatch,
    CaseMatchExecution,
    CaseStudy,
    ResearchCitation,
    ResearchFinding,
    ResearchRun,
)
from app.models.engagement import Engagement, EngagementStep
from app.models.file import File
from app.models.intake import IntakeAnswer, IntakeOption
from app.services import agent as agent_svc
from app.services import audit as audit_svc
from app.services import case_match as case_match_svc
from app.services.case_card import CaseCard
from app.services import client_intake as intake_svc
from app.services import engagement as engagement_svc
from app.services import lead as lead_svc
from app.services import plan as plan_svc
from app.services import plan_rating as plan_rating_svc
from app.services import quota as quota_svc
from app.services import rate_limit as rate_limit_svc
from app.services import skill as skill_svc
from app.services import workspace as workspace_svc
from app.services.chat_policy import prepare_chat
from app.services.classifier import detect_tier
from app.services.policy_engine import PolicyEngine

router = APIRouter(prefix="/client", tags=["client-workspace"])

_logger = logging.getLogger(__name__)


def _require_enabled() -> None:
    if not settings.client_surface_enabled:
        _logger.warning("client router: client_surface_enabled is False, rejecting request")
        raise HTTPException(status_code=503, detail="Client workspaces are disabled")


# ---------------------------------------------------------------------------
# Intake-answer helpers
# ---------------------------------------------------------------------------

async def _load_fields(session: AsyncSession, step1: EngagementStep) -> dict[str, str]:
    """Read the seat's live (non-superseded) intake answers as
    {field_key: display_value} — a chip pick resolves through its
    IntakeOption.value; free text is decrypted."""
    rows = (
        await session.execute(
            select(IntakeAnswer).where(
                IntakeAnswer.engagement_step_id == step1.id, IntakeAnswer.superseded_at.is_(None)
            )
        )
    ).scalars().all()

    fields: dict[str, str] = {}
    for row in rows:
        if row.option_id is not None:
            value = (
                await session.execute(select(IntakeOption.value).where(IntakeOption.id == row.option_id))
            ).scalar_one()
        else:
            value = crypto.decrypt(row.value_ciphertext, row.value_nonce, row.value_tag, row.key_version)
        fields[row.field_key] = value
    return fields


async def _record_answer(
    session: AsyncSession,
    step1: EngagementStep,
    *,
    question_id: uuid.UUID,
    field_key: str,
    option_id: uuid.UUID | None,
    free_text_value: str | None,
    source: str,
) -> None:
    """Supersede any live answer for this field, then insert the new one —
    append-only, so PATCH /client/intake/fields leaves real edit history
    behind instead of the old blob-overwrite (the intake_edited audit row
    only ever recorded {"field": name}, never old/new)."""
    await session.execute(
        update(IntakeAnswer)
        .where(IntakeAnswer.engagement_step_id == step1.id, IntakeAnswer.field_key == field_key,
               IntakeAnswer.superseded_at.is_(None))
        .values(superseded_at=datetime.now(timezone.utc))
    )
    if option_id is not None:
        session.add(IntakeAnswer(
            engagement_step_id=step1.id, question_id=question_id, field_key=field_key,
            option_id=option_id, source=source,
        ))
    else:
        ct, nonce, tag, kv = crypto.encrypt(free_text_value or "")
        session.add(IntakeAnswer(
            engagement_step_id=step1.id, question_id=question_id, field_key=field_key,
            value_ciphertext=ct, value_nonce=nonce, value_tag=tag, key_version=kv, source=source,
        ))


async def _resolve_answer_value(
    session: AsyncSession,
    engagement: Engagement,
    index: int,
    *,
    option_index: int | None,
    free_text: str | None,
) -> tuple[dict, str, uuid.UUID, uuid.UUID | None, str]:
    """Resolve a chip/free-text answer against the script — no DB write.
    Returns (step_def, resolved_value, question_id, option_id, source)."""
    step_def = await intake_svc.step_at_db(session, engagement.intake_script_id, index)
    if step_def is None:
        raise HTTPException(status_code=400, detail="Unknown intake step")
    try:
        value = intake_svc.resolve_answer(step_def, option_index=option_index, free_text=free_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    question_id = await intake_svc.question_id_at_db(session, engagement.intake_script_id, index)
    option_id = None
    source = "free_text"
    if option_index is not None:
        option_id = await intake_svc.option_id_at_db(session, question_id, option_index)
        source = "chip"
    return step_def, value, question_id, option_id, source


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ChipOut(BaseModel):
    index: int
    label: str


class CurrentStepOut(BaseModel):
    field: str
    question: str
    options: list[ChipOut]


async def _current_step_out(session: AsyncSession, engagement: Engagement, step_index: int) -> CurrentStepOut | None:
    step_def = await intake_svc.step_at_db(session, engagement.intake_script_id, step_index)
    if step_def is None:
        return None
    return CurrentStepOut(
        field=step_def["field"],
        question=step_def["question"],
        options=[ChipOut(index=i, label=o["label"]) for i, o in enumerate(step_def["options"])],
    )


class IntakeFieldOut(BaseModel):
    key: str
    label: str
    options: list[ChipOut] = []


class PlanSummaryOut(BaseModel):
    id: uuid.UUID
    title: str
    version: int


class BootstrapOut(BaseModel):
    workspace: dict
    agent: dict | None
    conversation_id: uuid.UUID | None
    # engagement_id lets the frontend call POST /client/engagements
    # relative to "the current one" later, and active_plan_id replaces the
    # old `bb:activePlan:${workspaceId}` localStorage key — which plan a
    # PUT /client/plans/{id} revision targets is server state now.
    engagement_id: uuid.UUID
    active_plan_id: uuid.UUID | None
    step: int
    total_steps: int
    completed: bool
    fields: dict[str, str]
    intake_fields: list[IntakeFieldOut]
    current_step: CurrentStepOut | None
    plan_count: int
    is_preview: bool
    internal_app_enabled: bool
    # 'idle' | 'pending' | 'done' | 'error' — 'pending' is deliberately
    # never surfaced (see engagement_steps' 5-state status: a step stuck at
    # 'running' with no way to finish reports as 'error' here, same
    # behavior as before the redesign, now driven by one real status
    # column instead of a hardcoded {"pending": "error"} map).
    research_status: str = "idle"
    research: dict | None = None
    cases_status: str = "idle"
    cases: dict | None = None
    plans: list[PlanSummaryOut] = []


class IntakeAnswerIn(BaseModel):
    option_index: int | None = None
    free_text: str | None = None


class IntakeAnswerOut(BaseModel):
    step: int
    total_steps: int
    completed: bool
    completion_message: str | None
    current_step: CurrentStepOut | None
    insight: str | None = None
    fields: dict[str, str] = Field(default_factory=dict)


class IntakeFieldEditIn(BaseModel):
    field: str
    option_index: int | None = None
    free_text: str | None = None


class IntakeEditIn(BaseModel):
    updates: list[IntakeFieldEditIn] = Field(min_length=1)


class IntakeEditOut(BaseModel):
    fields: dict[str, str]
    changed: list[str]
    step: int
    total_steps: int
    completed: bool


class ClientChatIn(BaseModel):
    conversation_id: uuid.UUID | None = None
    content: str


_STATUS_OUT = {"idle": "idle", "running": "pending", "done": "done", "failed": "error"}


async def _research_out(session: AsyncSession, run: ResearchRun) -> dict:
    findings = (
        await session.execute(
            select(ResearchFinding.text).where(ResearchFinding.research_run_id == run.id).order_by(ResearchFinding.ordinal)
        )
    ).scalars().all()
    citations = (
        await session.execute(
            select(ResearchCitation).where(ResearchCitation.research_run_id == run.id).order_by(ResearchCitation.ordinal)
        )
    ).scalars().all()
    return {
        "id": str(run.id),
        "findings": [{"text": t} for t in findings],
        "citations": [{"index": i + 1, "source": c.url} for i, c in enumerate(citations)],
    }


def _cases_out(rows: list[tuple[CaseMatch, str, uuid.UUID, CaseCard | None]]) -> dict:
    return {
        "matches": [
            {
                "file_id": str(file_id),
                "filename": filename,
                "score": round(row.score, 2),
                "rationale": row.rationale,
                "title": card.title if card else None,
                "client": card.client if card else None,
                "category": card.category if card else None,
                "source_url": card.source_url if card else None,
                "summary": card.summary if card else None,
                "image_url": card.image_url if card else None,
            }
            for row, filename, file_id, card in rows
        ]
    }


async def _latest_research_run(session: AsyncSession, step2_id: uuid.UUID) -> ResearchRun | None:
    return (
        await session.execute(
            select(ResearchRun).where(ResearchRun.engagement_step_id == step2_id).order_by(ResearchRun.created_at.desc()).limit(1)
        )
    ).scalars().first()


async def _latest_case_run(session: AsyncSession, step3_id: uuid.UUID) -> CaseMatchExecution | None:
    return (
        await session.execute(
            select(CaseMatchExecution).where(CaseMatchExecution.engagement_step_id == step3_id)
            .order_by(CaseMatchExecution.created_at.desc()).limit(1)
        )
    ).scalars().first()


async def _case_matches_for_run(session: AsyncSession, run_id: uuid.UUID) -> dict:
    rows = (
        await session.execute(
            select(CaseMatch, File.filename, File.id, CaseStudy)
            .join(CaseStudy, CaseStudy.id == CaseMatch.case_study_id)
            .join(File, File.id == CaseStudy.file_id)
            .where(CaseMatch.case_match_run_id == run_id)
            .order_by(CaseMatch.rank)
        )
    ).all()
    return {
        "matches": [
            {
                "file_id": str(file_id),
                "filename": filename,
                "score": round(match.score, 2),
                "rationale": match.rationale,
                "title": card.title,
                "client": card.client_name,
                "category": card.category,
                "source_url": card.source_url,
                "summary": card.summary,
                "image_url": card.image_url,
            }
            for match, filename, file_id, card in rows
        ]
    }


async def _journey_status(
    session: AsyncSession, steps: dict[str, EngagementStep]
) -> tuple[str, dict | None, str, dict | None]:
    """Replays the latest research run + case match run for bootstrap, in
    the same response shape POST /client/research and POST /client/cases
    return. Step status now comes straight from engagement_steps — no more
    querying audit_log to distinguish 'never ran' from 'ran, found
    nothing' (see app/models/client_intake.py::CaseMatchExecution)."""
    market = steps["market"]
    research_status = _STATUS_OUT.get(market.status, "idle")
    research_out: dict | None = None
    if market.status == "done":
        run = await _latest_research_run(session, market.id)
        if run is not None:
            research_out = await _research_out(session, run)

    cases = steps["cases"]
    cases_status = _STATUS_OUT.get(cases.status, "idle")
    cases_out: dict | None = None
    if cases.status == "done":
        run = await _latest_case_run(session, cases.id)
        if run is not None:
            cases_out = await _case_matches_for_run(session, run.id)

    return research_status, research_out, cases_status, cases_out


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/bootstrap", response_model=BootstrapOut)
async def bootstrap(
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> BootstrapOut:
    _require_enabled()
    workspace = await workspace_svc.get_workspace(session, ctx.workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    agent = await workspace_svc.get_workspace_agent(session, ctx.workspace_id)
    engagement = await engagement_svc.get_or_create_active(session, ctx.user, ctx.workspace_id)
    steps = await engagement_svc.get_steps(session, engagement.id)
    step1 = steps["interview"]

    fields = await _load_fields(session, step1)
    total_steps = await intake_svc.total_steps_db(session, engagement.intake_script_id)
    current_index = step1.progress_current or 0
    completed = step1.status == "done"

    plans = await plan_svc.list_plans(session, ctx.user, ctx.workspace_id)
    plan_summaries = []
    for p in plans:
        version = await plan_svc.get_current_version(session, p)
        plan_summaries.append(PlanSummaryOut(id=p.id, title=version.title, version=version.version_no))

    research_status, research_out, cases_status, cases_out = await _journey_status(session, steps)

    agent_out = None
    if agent is not None:
        skill_ids = await skill_svc.get_agent_skill_ids(session, agent.id)
        file_ids = await agent_svc.get_agent_file_ids(session, agent.id)
        agent_out = {
            "id": str(agent.id),
            "name": agent.name,
            "avatar_color": agent.avatar_color,
            "skill_count": len(skill_ids),
            "file_count": len(file_ids),
            "web_search": bool((agent.capabilities or {}).get("web_search", False)),
        }

    return BootstrapOut(
        workspace={"id": str(workspace.id), "name": workspace.name, "slug": workspace.slug},
        agent=agent_out,
        conversation_id=engagement.conversation_id,
        engagement_id=engagement.id,
        active_plan_id=engagement.active_plan_id,
        step=current_index,
        total_steps=total_steps,
        completed=completed,
        fields=fields,
        intake_fields=[IntakeFieldOut(**f) for f in await intake_svc.field_manifest_db(session, engagement.intake_script_id)],
        current_step=await _current_step_out(session, engagement, current_index),
        plan_count=len(plans),
        is_preview=ctx.is_preview,
        internal_app_enabled=settings.client_internal_access_enabled,
        research_status=research_status,
        research=research_out,
        cases_status=cases_status,
        cases=cases_out,
        plans=plan_summaries,
    )


@router.post("/engagements", response_model=BootstrapOut)
async def start_engagement(
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> BootstrapOut:
    """Start a fresh engagement — a returning client's second brief. The
    old schema's uq_client_profiles_workspace_user made this impossible;
    engagements.status lets a seat hold one ACTIVE engagement plus
    unlimited completed/abandoned ones (see app/models/engagement.py)."""
    _require_enabled()
    await engagement_svc.start_new(session, ctx.user, ctx.workspace_id)
    return await bootstrap(ctx, session)


@router.post("/intake/answer", response_model=IntakeAnswerOut)
async def answer_intake(
    body: IntakeAnswerIn,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> IntakeAnswerOut:
    _require_enabled()
    engagement = await engagement_svc.get_or_create_active(session, ctx.user, ctx.workspace_id)
    step1 = await engagement_svc.get_step(session, engagement.id, "interview")
    total_steps = await intake_svc.total_steps_db(session, engagement.intake_script_id)
    current_index = step1.progress_current or 0
    if current_index >= total_steps:
        raise HTTPException(status_code=400, detail="Intake is already complete")

    step_def, value, question_id, option_id, source = await _resolve_answer_value(
        session, engagement, current_index,
        option_index=body.option_index, free_text=body.free_text,
    )
    await _record_answer(
        session, step1, question_id=question_id, field_key=step_def["field"],
        option_id=option_id, free_text_value=None if option_id is not None else value, source=source,
    )

    next_index = current_index + 1
    completed = next_index >= total_steps
    completion_message = None
    if completed:
        await engagement_svc.mark_step(
            session, step1, "done", progress_current=next_index, progress_total=total_steps, commit=False,
        )
        completion_message = intake_svc.INTAKE_COMPLETE_MESSAGE
    else:
        await engagement_svc.mark_step(
            session, step1, "running", progress_current=next_index, progress_total=total_steps, commit=False,
        )
    await session.commit()

    fields = await _load_fields(session, step1)

    await audit_svc.log(
        action="intake_answered",
        user_id=ctx.user.id,
        resource_type="workspace",
        resource_id=ctx.workspace_id,
        details={"field": step_def["field"], "step": current_index},
    )

    return IntakeAnswerOut(
        step=next_index,
        total_steps=total_steps,
        completed=completed,
        completion_message=completion_message,
        current_step=await _current_step_out(session, engagement, next_index),
        insight=step_def.get("insight"),
        fields=fields,
    )


@router.patch("/intake/fields", response_model=IntakeEditOut)
async def edit_intake_fields(
    body: IntakeEditIn,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> IntakeEditOut:
    """Correct one or more already-answered intake fields (Task 5.11 —
    editable company profile). Deliberately does NOT touch
    engagement_steps' interview progress: this is a correction to answers
    already given, not a re-run of the scripted intake. Only a question
    the client has already reached (idx < progress_current) may be
    edited, so this can never skip ahead of the script or pre-fill a
    question not yet asked.

    Rate-limited per user (not per IP — D23 puts every booth attendee in
    one shared workspace, likely behind one NAT IP) so a resubmit can't be
    spammed against the LLM-backed pipeline it triggers downstream.
    """
    _require_enabled()
    rate_limit_svc.check(f"intake_edit:{ctx.user.id}", limit=1, window_seconds=60)

    engagement = await engagement_svc.get_or_create_active(session, ctx.user, ctx.workspace_id)
    step1 = await engagement_svc.get_step(session, engagement.id, "interview")
    current_index = step1.progress_current or 0
    fields_before = await _load_fields(session, step1)

    changed: list[str] = []
    for update in body.updates:
        idx = await intake_svc.index_of_field_db(session, engagement.intake_script_id, update.field)
        if idx is None:
            raise HTTPException(status_code=400, detail=f"Unknown field: {update.field}")
        if idx >= current_index:
            raise HTTPException(status_code=400, detail=f"'{update.field}' hasn't been asked yet")

        step_def, value, question_id, option_id, source = await _resolve_answer_value(
            session, engagement, idx,
            option_index=update.option_index, free_text=update.free_text,
        )
        if fields_before.get(update.field) == value:
            continue  # no-op — no new row, no audit entry, nothing worth regenerating
        await _record_answer(
            session, step1, question_id=question_id, field_key=step_def["field"],
            # source='edit' (not the chip/free_text the resolver returned)
            # — this row is a correction to an already-answered question,
            # not the original answer; distinguishing the two is exactly
            # what the old single-blob client_profiles.fields_ciphertext
            # could never record.
            option_id=option_id, free_text_value=None if option_id is not None else value, source="edit",
        )
        changed.append(update.field)

    if changed:
        await session.commit()
        for field in changed:
            await audit_svc.log(
                action="intake_edited",
                user_id=ctx.user.id,
                resource_type="workspace",
                resource_id=ctx.workspace_id,
                details={"field": field},
            )
    else:
        await session.rollback()

    fields = await _load_fields(session, step1)
    total_steps = await intake_svc.total_steps_db(session, engagement.intake_script_id)
    return IntakeEditOut(
        fields=fields,
        changed=changed,
        step=current_index,
        total_steps=total_steps,
        completed=step1.status == "done",
    )


@router.post("/chat")
async def client_chat(
    body: ClientChatIn,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    _require_enabled()
    agent = await workspace_svc.get_workspace_agent(session, ctx.workspace_id)
    if agent is None:
        raise HTTPException(status_code=503, detail="This workspace has no assigned agent yet")

    prepared = await prepare_chat(
        session=session,
        user=ctx.user,
        conversation_id=body.conversation_id,
        user_content=body.content,
        requested_model="auto",
        agent_id=agent.id,  # forced — never trust a client-supplied agent_id
        workspace_id=ctx.workspace_id,
    )
    return StreamingResponse(
        run_chat_stream(
            session=session,
            user_id=ctx.user.id,
            user=ctx.user,
            resolved_conversation_id=prepared.resolved_conversation_id,
            user_content=body.content,
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
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


_RESEARCH_SYSTEM_PROMPT = (
    "You are a market research analyst for a Thai brand strategy agency. "
    "Search international and Thai-language sources as needed. "
    "Write your entire answer in Thai (ภาษาไทย), in natural business Thai that a Thai "
    "brand strategist would use with a client. "
    "Keep brand names, company names, report/publisher names and metric names in their "
    "original language. Keep the [n] citation markers exactly as produced. "
    "Use short markdown bullets. Do not add a preamble or a closing summary."
)


@router.post("/research")
async def run_research(
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """The "External market scan · IAG" step. IAG ≈ Perplexity (per
    DSME_ai.md's mapping) — routed through PolicyEngine.decide() at the
    Perplexity model code exactly like an internal user's chat would be.
    """
    _require_enabled()
    user = ctx.user
    engagement = await engagement_svc.get_or_create_active(session, user, ctx.workspace_id)
    step1 = await engagement_svc.get_step(session, engagement.id, "interview")
    if step1.status != "done":
        raise HTTPException(status_code=400, detail="Complete the intake before running research")
    step2 = await engagement_svc.get_step(session, engagement.id, "market")

    fields = await _load_fields(session, step1)
    query = (
        "Research the current market and competitor landscape for this business, "
        "with concrete, recent, actionable findings a brand strategist could use "
        "in a client-facing plan. Business context: " + case_match_svc.build_context_query(fields)
    )

    tier = detect_tier(query)
    estimated_tokens = max(1, len(query) // 4)
    decision = await PolicyEngine(session).decide(user, PERPLEXITY_MODEL_CODE, tier, estimated_tokens)
    if not decision.allowed or decision.downgrade_to_local:
        await audit_svc.log(
            action="model_blocked",
            user_id=user.id,
            resource_type="workspace",
            resource_id=ctx.workspace_id,
            details={
                "model_requested": PERPLEXITY_MODEL_CODE,
                "reasons": [r.value if hasattr(r, "value") else str(r) for r in decision.reasons],
            },
        )
        raise HTTPException(
            status_code=403, detail="Market research is not available for this workspace right now"
        )

    await engagement_svc.mark_step(session, step2, "running")

    ct, nonce, tag, kv = crypto.encrypt(query)
    run = ResearchRun(
        engagement_step_id=step2.id,
        query_ciphertext=ct, query_nonce=nonce, query_tag=tag, key_version=kv,
        status="running",
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    full_text = ""
    citations_raw: list[str] = []
    tokens_in = tokens_out = 0
    try:
        client = get_router().get(PERPLEXITY_MODEL_CODE)
        async for chunk in client.stream_chat([
            ChatMessage(role="system", content=_RESEARCH_SYSTEM_PROMPT),
            ChatMessage(role="user", content=query),
        ]):
            full_text += chunk.content
            if chunk.metadata and chunk.metadata.get("citations"):
                citations_raw = chunk.metadata["citations"]
            if chunk.prompt_tokens:
                tokens_in = chunk.prompt_tokens
            if chunk.completion_tokens:
                tokens_out = chunk.completion_tokens
    except Exception as exc:
        run.status = "failed"
        run.error_detail = str(exc)[:500]
        await session.commit()
        await engagement_svc.mark_step(session, step2, "failed", error_code="research_call_failed", error_detail=str(exc)[:500])
        raise HTTPException(
            status_code=502, detail="Market research is temporarily unavailable"
        ) from exc

    findings_text = [s.strip() for s in full_text.split("\n") if s.strip()]
    for i, text in enumerate(findings_text):
        session.add(ResearchFinding(research_run_id=run.id, ordinal=i, text=text))
    for i, url in enumerate(citations_raw):
        session.add(ResearchCitation(research_run_id=run.id, ordinal=i, url=url))

    run.model_used = PERPLEXITY_MODEL_CODE
    run.status = "done"
    run.tokens_input = tokens_in
    run.tokens_output = tokens_out
    run.completed_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(run)

    cost = await _compute_cost(session, PERPLEXITY_MODEL_CODE, tokens_in, tokens_out)
    await quota_svc.consume(session, user, tokens_in, tokens_out, cost)

    await engagement_svc.mark_step(session, step2, "done")

    await audit_svc.log(
        action="research_run",
        user_id=user.id,
        resource_type="workspace",
        resource_id=ctx.workspace_id,
        details={"research_run_id": str(run.id), "citation_count": len(citations_raw)},
    )

    return await _research_out(session, run)


@router.post("/cases")
async def run_case_match(
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Score the client's profile against the case library attached to the
    workspace's agent — via app/services/case_match.match_cases().

    Each call is a NEW case_match_runs row with its own append-only
    case_matches rows (the old table deleted-and-reinserted this seat's
    rows every call, destroying match history). Readers always take the
    LATEST done run for this engagement's step, so a re-run still can't
    leak stale/duplicate cases into a drafted plan.
    """
    _require_enabled()
    user = ctx.user
    engagement = await engagement_svc.get_or_create_active(session, user, ctx.workspace_id)
    step1 = await engagement_svc.get_step(session, engagement.id, "interview")
    if step1.status != "done":
        raise HTTPException(status_code=400, detail="Complete the intake before matching cases")
    step3 = await engagement_svc.get_step(session, engagement.id, "cases")

    agent = await workspace_svc.get_workspace_agent(session, ctx.workspace_id)
    agent_file_ids = await agent_svc.get_agent_file_ids(session, agent.id) if agent else None

    fields = await _load_fields(session, step1)
    await engagement_svc.mark_step(session, step3, "running")

    match_run = await case_match_svc.match_cases(
        session,
        user,
        fields,
        agent_file_ids=agent_file_ids,
        effective_workspace_id=ctx.workspace_id,
    )

    ct, nonce, tag, kv = crypto.encrypt(match_run.query)
    run = CaseMatchExecution(
        engagement_step_id=step3.id,
        query_ciphertext=ct, query_nonce=nonce, query_tag=tag, key_version=kv,
        status="done", match_count=len(match_run.results), completed_at=datetime.now(timezone.utc),
    )
    session.add(run)
    await session.flush()

    rows: list[tuple[CaseMatch, str, uuid.UUID, CaseCard | None]] = []
    for r in match_run.results:
        case_study = (
            await session.execute(select(CaseStudy).where(CaseStudy.file_id == r.file_id))
        ).scalar_one_or_none()
        if case_study is None:
            # Newly ingested/never-cataloged file — catalog it now instead
            # of failing the whole match (app/services/case_card.py already
            # parsed it into `r.card`).
            case_study = CaseStudy(
                workspace_id=ctx.workspace_id, file_id=r.file_id,
                title=r.card.title if r.card else None,
                client_name=r.card.client if r.card else None,
                category=r.card.category if r.card else None,
                source_url=r.card.source_url if r.card else None,
                image_url=r.card.image_url if r.card else None,
                summary=r.card.summary if r.card else None,
            )
            session.add(case_study)
            await session.flush()

        match = CaseMatch(
            case_match_run_id=run.id, case_study_id=case_study.id, rank=r.rank,
            score=r.score, rationale=r.rationale,
        )
        session.add(match)
        rows.append((match, r.filename, r.file_id, r.card))
    await session.commit()

    await engagement_svc.mark_step(session, step3, "done")

    await audit_svc.log(
        action="case_matched",
        user_id=user.id,
        resource_type="workspace",
        resource_id=ctx.workspace_id,
        details={"match_count": len(rows), "case_match_run_id": str(run.id)},
    )

    return _cases_out(rows)


# ---------------------------------------------------------------------------
# Plans (Phase 4)
# ---------------------------------------------------------------------------

class SavePlanIn(BaseModel):
    title: str
    core_idea: str
    analogous_case: str
    adapted_plan: list[dict]
    budget: dict
    provenance: dict
    conversation_id: uuid.UUID | None = None


class PlanVersionOut(BaseModel):
    version: int
    created_at: datetime


class PlanVersionBodyOut(BaseModel):
    version: int
    created_at: datetime
    title: str
    core_idea: str
    analogous_case: str
    adapted_plan: list[dict]
    budget: dict | None
    provenance: dict | None


class PlanRatingIn(BaseModel):
    score: int = Field(ge=1, le=10)
    comment: str | None = Field(default=None, max_length=2000)


class PlanRatingOut(BaseModel):
    score: int
    comment: str | None
    created_at: datetime


class PlanOut(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    version: int
    core_idea: str
    analogous_case: str
    adapted_plan: list[dict]
    budget: dict | None
    provenance: dict | None
    created_at: datetime
    agent_name: str | None = None
    versions: list[PlanVersionOut] = []
    rating: PlanRatingOut | None = None


async def _plan_out(session: AsyncSession, plan, *, agent_name: str | None = None, with_versions: bool = False, rating=None) -> PlanOut:
    version = await plan_svc.get_current_version(session, plan)
    body = plan_svc.decrypt_body(version)
    versions_out: list[PlanVersionOut] = []
    if with_versions:
        versions = await plan_svc.list_versions(session, plan.id)
        versions_out = [PlanVersionOut(version=v.version_no, created_at=v.created_at) for v in versions]
    return PlanOut(
        id=plan.id,
        title=version.title,
        status=plan.status,
        version=version.version_no,
        core_idea=body.get("core_idea", ""),
        analogous_case=body.get("analogous_case", ""),
        adapted_plan=body.get("adapted_plan", []),
        budget=await plan_svc.budget_out(session, version),
        provenance=await plan_svc.provenance_out(session, version),
        created_at=plan.created_at,
        agent_name=agent_name,
        versions=versions_out,
        rating=(
            PlanRatingOut(score=rating.score, comment=rating.comment, created_at=rating.created_at)
            if rating is not None else None
        ),
    )


@router.post("/plan/draft")
async def draft_plan(
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Draft the 4-part plan but do not save it — the frontend shows this
    as a preview with a "Save as a plan" action (POST /client/plans)
    before it becomes a durable artifact."""
    _require_enabled()
    engagement = await engagement_svc.get_or_create_active(session, ctx.user, ctx.workspace_id)
    step1 = await engagement_svc.get_step(session, engagement.id, "interview")
    if step1.status != "done":
        _logger.warning(
            "plan/draft: workspace %s user %s intake incomplete at step %d",
            ctx.workspace_id, ctx.user.id, step1.progress_current or 0,
        )
        raise HTTPException(status_code=400, detail="Complete the intake before drafting a plan")
    step4 = await engagement_svc.get_step(session, engagement.id, "plan")

    fields = await _load_fields(session, step1)
    if step4.status == "idle":
        await engagement_svc.mark_step(session, step4, "running")
    try:
        draft = await plan_svc.draft_plan(session, ctx.user, ctx.workspace_id, engagement, fields)
    except HTTPException:
        if step4.status != "done":
            await engagement_svc.mark_step(session, step4, "failed", error_code="draft_failed")
        raise
    return draft


@router.post("/plans", status_code=201, response_model=PlanOut)
async def save_plan(
    body: SavePlanIn,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PlanOut:
    _require_enabled()
    engagement = await engagement_svc.get_or_create_active(session, ctx.user, ctx.workspace_id)
    plan = await plan_svc.save_plan(session, ctx.user, ctx.workspace_id, engagement, body.model_dump())
    step4 = await engagement_svc.get_step(session, engagement.id, "plan")
    await engagement_svc.mark_step(session, step4, "done")
    agent = await workspace_svc.get_workspace_agent(session, ctx.workspace_id)
    return await _plan_out(session, plan, agent_name=agent.name if agent else None)


@router.put("/plans/{plan_id}", response_model=PlanOut)
async def revise_plan(
    plan_id: uuid.UUID,
    body: SavePlanIn,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PlanOut:
    """Save a re-drafted plan over an existing one (Task 5.11)."""
    _require_enabled()
    plan = await plan_svc.revise_plan(session, ctx.user, ctx.workspace_id, plan_id, body.model_dump())
    agent = await workspace_svc.get_workspace_agent(session, ctx.workspace_id)
    return await _plan_out(session, plan, agent_name=agent.name if agent else None)


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[PlanOut]:
    _require_enabled()
    plans = await plan_svc.list_plans(session, ctx.user, ctx.workspace_id)
    agent = await workspace_svc.get_workspace_agent(session, ctx.workspace_id)
    agent_name = agent.name if agent else None
    return [await _plan_out(session, p, agent_name=agent_name) for p in plans]


@router.get("/plans/{plan_id}", response_model=PlanOut)
async def get_plan(
    plan_id: uuid.UUID,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PlanOut:
    _require_enabled()
    plan = await plan_svc.get_plan(session, ctx.user, ctx.workspace_id, plan_id)
    rating = await plan_rating_svc.get_rating(session, ctx.user, ctx.workspace_id, plan_id)
    agent = await workspace_svc.get_workspace_agent(session, ctx.workspace_id)
    return await _plan_out(session, plan, agent_name=agent.name if agent else None, with_versions=True, rating=rating)


@router.get("/plans/{plan_id}/versions/{version}", response_model=PlanVersionBodyOut)
async def get_plan_version(
    plan_id: uuid.UUID,
    version: int,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PlanVersionBodyOut:
    """Task 5.12 — the version rail's "read an old version" affordance.
    Read-only: no audit action, no rate limit."""
    _require_enabled()
    v = await plan_svc.get_version(session, ctx.user, ctx.workspace_id, plan_id, version)
    body = plan_svc.decrypt_version_body(v)
    return PlanVersionBodyOut(
        version=v.version_no,
        created_at=v.created_at,
        title=v.title,
        core_idea=body.get("core_idea", ""),
        analogous_case=body.get("analogous_case", ""),
        adapted_plan=body.get("adapted_plan", []),
        budget=await plan_svc.budget_out(session, v),
        provenance=await plan_svc.provenance_out(session, v),
    )


@router.post("/plans/{plan_id}/rating", response_model=PlanRatingOut)
async def rate_plan(
    plan_id: uuid.UUID,
    body: PlanRatingIn,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PlanRatingOut:
    _require_enabled()
    if ctx.is_preview:
        raise HTTPException(
            status_code=400,
            detail="You're previewing the demo workspace — ratings are disabled here so a "
            "walkthrough never shows up as real client feedback. This works normally for a "
            "real attendee who arrived via an invite link.",
        )
    rating = await plan_rating_svc.upsert_rating(
        session, ctx.user, ctx.workspace_id, plan_id, score=body.score, comment=body.comment
    )
    return PlanRatingOut(score=rating.score, comment=rating.comment, created_at=rating.created_at)


@router.post("/plans/{plan_id}/activate")
async def activate_plan(
    plan_id: uuid.UUID,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """The plan switcher's "make this the active one" action — server-side
    replacement for the old `bb:activePlan:*` localStorage key (Task 5.12).
    plan_svc.get_plan is the ownership check (404s on a plan this seat
    doesn't own) before engagements.active_plan_id is touched."""
    _require_enabled()
    plan = await plan_svc.get_plan(session, ctx.user, ctx.workspace_id, plan_id)
    engagement = await engagement_svc.get_or_create_active(session, ctx.user, ctx.workspace_id)
    await engagement_svc.set_active_plan(session, engagement, plan.id)
    return {"active_plan_id": str(plan.id)}


@router.post("/plans/{plan_id}/share")
async def share_plan(
    plan_id: uuid.UUID,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Mint (or re-mint) a share token for a plan — GET /public/plans/{token}
    is the read-only page that resolves it."""
    _require_enabled()
    raw = await plan_svc.create_share_token(session, ctx.user, ctx.workspace_id, plan_id)
    return {"token": raw, "share_path": f"/p/{raw}"}


# ---------------------------------------------------------------------------
# Lead capture (Phase 5) — "Talk to an expert"
# ---------------------------------------------------------------------------

class LeadIn(BaseModel):
    plan_id: uuid.UUID | None = None
    contact_name: str | None = None
    contact_phone_or_line: str | None = None
    best_time: str | None = None


@router.post("/leads", status_code=201)
async def submit_lead(
    body: LeadIn,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    _require_enabled()
    if ctx.is_preview:
        raise HTTPException(
            status_code=400,
            detail="You're previewing the demo workspace — lead capture is disabled here so a "
            "walkthrough never creates a real lead. This works normally for a real attendee "
            "who arrived via an invite link.",
        )
    lead = await lead_svc.submit(
        session,
        ctx.user,
        plan_id=body.plan_id,
        contact_name=body.contact_name,
        contact_phone_or_line=body.contact_phone_or_line,
        best_time=body.best_time,
    )
    return {"id": str(lead.id), "status": lead.status, "delivered": lead.n8n_error is None}
