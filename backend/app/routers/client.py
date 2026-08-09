"""
app/routers/client.py

Client-workspace endpoints (Phase 5 §3-4, D21/D22) — require_client_context-gated
(a real client seat uses its own workspace; internal staff with no
workspace of their own preview the seeded demo workspace instead — see
app/deps.py::ClientContext):
  GET  /client/bootstrap      — workspace, agent, profile + current step
  POST /client/intake/answer  — record an answer, return the next step
  POST /client/chat            — chat with the workspace's agent (SSE)
  POST /client/research        — run the market scan (Perplexity)
  POST /client/cases           — match against the case library (RAG)
  POST /client/plan/draft      — draft a plan (not saved yet)
  POST /client/plans           — save a drafted plan as an artifact
  GET  /client/plans           — list this seat's saved plans
  GET  /client/plans/{id}      — one plan, decrypted
  POST /client/plans/{id}/rating — rate a plan (upserted; surfaced on the
                                    expert leads inbox, app/routers/admin_leads.py)

Every governance path (PolicyEngine.decide, quota, audit, encryption) is
inherited unchanged from the internal chat path — this router only decides
WHICH agent a client seat's chat is forced through; it never bypasses how
that call is gated. See app/models/client_intake.py for why the intake/
research/cases tables are scoped per (workspace_id, user_id).
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import crypto
from app.agents.orchestrator import _compute_cost, run_chat_stream
from app.config import settings
from app.db import get_db
from app.deps import ClientContext, require_client_context
from app.llm.base import ChatMessage
from app.llm.router import PERPLEXITY_MODEL_CODE, get_router
from app.models.client_intake import CaseMatch, ClientProfile, ResearchRun
from app.models.conversation import Conversation
from app.models.user import User
from app.services import agent as agent_svc
from app.services import audit as audit_svc
from app.services import case_match as case_match_svc
from app.services import client_intake as intake_svc
from app.services import lead as lead_svc
from app.services import plan as plan_svc
from app.services import plan_rating as plan_rating_svc
from app.services import quota as quota_svc
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
# Profile helpers
# ---------------------------------------------------------------------------

async def _get_or_create_profile(session: AsyncSession, user: User, workspace_id: uuid.UUID) -> ClientProfile:
    result = await session.execute(
        select(ClientProfile).where(
            ClientProfile.workspace_id == workspace_id,
            ClientProfile.user_id == user.id,
        )
    )
    profile = result.scalar_one_or_none()
    if profile is not None:
        return profile

    # One conversation for this seat's whole session — intake (recorded as
    # structured fields, not messages), chat, research, and cases all share
    # it, so a later /client/chat turn sees consistent conversation_id-scoped
    # history even though intake itself never writes a Message row.
    workspace_agent = await workspace_svc.get_workspace_agent(session, workspace_id)
    conv = Conversation(
        user_id=user.id,
        agent_id=workspace_agent.id if workspace_agent else None,
    )
    session.add(conv)
    await session.flush()

    ct, nonce, tag, kv = crypto.encrypt(json.dumps({}))
    profile = ClientProfile(
        workspace_id=workspace_id,
        user_id=user.id,
        conversation_id=conv.id,
        step=0,
        fields_ciphertext=ct,
        fields_nonce=nonce,
        fields_tag=tag,
        key_version=kv,
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile


def _decrypt_fields(profile: ClientProfile) -> dict:
    raw = crypto.decrypt(
        profile.fields_ciphertext, profile.fields_nonce, profile.fields_tag, profile.key_version
    )
    return json.loads(raw) if raw else {}


def _encrypt_fields(fields: dict) -> tuple[bytes, bytes, bytes, int]:
    return crypto.encrypt(json.dumps(fields))


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


def _current_step_out(step_index: int) -> CurrentStepOut | None:
    step_def = intake_svc.step_at(step_index)
    if step_def is None:
        return None
    return CurrentStepOut(
        field=step_def["field"],
        question=step_def["question"],
        options=[ChipOut(index=i, label=o["label"]) for i, o in enumerate(step_def["options"])],
    )


class BootstrapOut(BaseModel):
    workspace: dict
    agent: dict | None
    conversation_id: uuid.UUID
    step: int
    total_steps: int
    completed: bool
    fields: dict[str, str]
    current_step: CurrentStepOut | None
    plan_count: int
    # True when an internal staff member (no workspace of their own) is
    # clicking through the demo workspace before it goes live to real
    # attendees — see app/deps.py::require_client_context. The frontend
    # uses this to show a preview banner and disable lead capture.
    is_preview: bool
    # D23 — same flag surfaced on /auth/me (app/routers/auth.py::
    # _user_response). Lets ClientWorkspace.tsx offer a real client seat
    # (not just a previewing staff member) the "open the full AI workspace"
    # link. See app/deps.py::require_internal for the enforcement side.
    internal_app_enabled: bool


class IntakeAnswerIn(BaseModel):
    option_index: int | None = None
    free_text: str | None = None


class IntakeAnswerOut(BaseModel):
    step: int
    total_steps: int
    completed: bool
    completion_message: str | None
    current_step: CurrentStepOut | None
    # What น้องภูมิ concluded from the answer just given — see
    # app/services/client_intake.py's IntakeStep.insight docstring for the
    # off-by-one this must NOT have (it belongs to the step just answered,
    # not the next step returned in current_step).
    insight: str | None = None


class ClientChatIn(BaseModel):
    conversation_id: uuid.UUID | None = None
    content: str


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
    profile = await _get_or_create_profile(session, ctx.user, ctx.workspace_id)
    fields = _decrypt_fields(profile)
    plans = await plan_svc.list_plans(session, ctx.user, ctx.workspace_id)

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
        conversation_id=profile.conversation_id,
        step=profile.step,
        total_steps=intake_svc.total_steps(),
        completed=profile.completed_at is not None,
        fields=fields,
        current_step=_current_step_out(profile.step),
        plan_count=len(plans),
        is_preview=ctx.is_preview,
        internal_app_enabled=settings.client_internal_access_enabled,
    )


@router.post("/intake/answer", response_model=IntakeAnswerOut)
async def answer_intake(
    body: IntakeAnswerIn,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> IntakeAnswerOut:
    _require_enabled()
    profile = await _get_or_create_profile(session, ctx.user, ctx.workspace_id)
    step_def = intake_svc.step_at(profile.step)
    if step_def is None:
        raise HTTPException(status_code=400, detail="Intake is already complete")

    try:
        value = intake_svc.resolve_answer(
            step_def, option_index=body.option_index, free_text=body.free_text
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    fields = _decrypt_fields(profile)
    fields[step_def["field"]] = value
    ct, nonce, tag, kv = _encrypt_fields(fields)
    profile.fields_ciphertext = ct
    profile.fields_nonce = nonce
    profile.fields_tag = tag
    profile.key_version = kv
    profile.step += 1

    completed = profile.step >= intake_svc.total_steps()
    completion_message = None
    if completed:
        profile.completed_at = datetime.now(timezone.utc)
        completion_message = intake_svc.INTAKE_COMPLETE_MESSAGE

    await session.commit()
    await session.refresh(profile)

    await audit_svc.log(
        action="intake_answered",
        user_id=ctx.user.id,
        resource_type="workspace",
        resource_id=ctx.workspace_id,
        details={"field": step_def["field"], "step": profile.step - 1},
    )

    return IntakeAnswerOut(
        step=profile.step,
        total_steps=intake_svc.total_steps(),
        completed=completed,
        completion_message=completion_message,
        current_step=_current_step_out(profile.step),
        insight=step_def.get("insight"),
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

    # Classify + policy decision happens inside prepare_chat, before the
    # stream starts, so a deny still returns a real 403 (StreamingResponse
    # commits to 200 once it starts) — identical contract to POST /chat.
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


@router.post("/research")
async def run_research(
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """The "External market scan · IAG" step. IAG ≈ Perplexity (per
    DSME_ai.md's mapping) — routed through PolicyEngine.decide() at the
    Perplexity model code exactly like an internal user's chat would be, so
    tier/quota/department-permission gating all still apply to a client
    seat's research call.
    """
    _require_enabled()
    user = ctx.user
    profile = await _get_or_create_profile(session, user, ctx.workspace_id)
    if profile.completed_at is None:
        raise HTTPException(status_code=400, detail="Complete the intake before running research")

    fields = _decrypt_fields(profile)
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

    run = ResearchRun(
        workspace_id=ctx.workspace_id,
        user_id=user.id,
        conversation_id=profile.conversation_id,
        query=query,
        status="pending",
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    full_text = ""
    citations_raw: list[str] = []
    tokens_in = tokens_out = 0
    try:
        # get_router().get() raises a bare KeyError when PERPLEXITY_API_KEY
        # isn't configured (app/llm/router.py only registers a client
        # `if cfg.perplexity_api_key:`) — folded into this try/except so
        # that's a clean "temporarily unavailable" + failed run, not an
        # unhandled 500 with the ResearchRun stuck at status="pending".
        client = get_router().get(PERPLEXITY_MODEL_CODE)
        async for chunk in client.stream_chat([ChatMessage(role="user", content=query)]):
            full_text += chunk.content
            if chunk.metadata and chunk.metadata.get("citations"):
                citations_raw = chunk.metadata["citations"]
            if chunk.prompt_tokens:
                tokens_in = chunk.prompt_tokens
            if chunk.completion_tokens:
                tokens_out = chunk.completion_tokens
    except Exception as exc:
        run.status = "failed"
        await session.commit()
        raise HTTPException(
            status_code=502, detail="Market research is temporarily unavailable"
        ) from exc

    findings = [{"text": s.strip()} for s in full_text.split("\n") if s.strip()]
    citations = [{"index": i + 1, "source": url} for i, url in enumerate(citations_raw)]

    run.findings = findings
    run.citations = citations
    run.model_used = PERPLEXITY_MODEL_CODE
    run.status = "done"
    run.completed_at = datetime.now(timezone.utc)
    await session.commit()

    # §7.5-equivalent: usage recorded after the call, same as the main chat
    # path's call_llm — quota is a real cost signal (Perplexity fires a
    # billable external call), not free like the local model.
    cost = await _compute_cost(session, PERPLEXITY_MODEL_CODE, tokens_in, tokens_out)
    await quota_svc.consume(session, user, tokens_in, tokens_out, cost)

    await audit_svc.log(
        action="research_run",
        user_id=user.id,
        resource_type="workspace",
        resource_id=ctx.workspace_id,
        details={"research_run_id": str(run.id), "citation_count": len(citations)},
    )

    return {"id": str(run.id), "findings": findings, "citations": citations}


@router.post("/cases")
async def run_case_match(
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Score the client's profile against the case library attached to the
    workspace's agent — via app/services/case_match.match_cases(), so the
    same personal/org/workspace access rule (R4 + D21/D22) governs which
    case-study files are even eligible to match, and the eval harness
    (backend/scripts/eval_case_match_run.py) exercises this exact pipeline.

    Preview mode (ctx.is_preview) passes ctx.workspace_id through as
    effective_workspace_id, so an internal staff member previewing the demo
    funnel (user.workspace_id IS NULL) still matches against the demo
    workspace's case files instead of the internal org corpus — see
    rag_search.retrieve()'s effective_workspace_id param and
    app/services/workspace.py::workspace_visibility_filter_by_workspace_id.
    """
    _require_enabled()
    user = ctx.user
    profile = await _get_or_create_profile(session, user, ctx.workspace_id)
    if profile.completed_at is None:
        raise HTTPException(status_code=400, detail="Complete the intake before matching cases")

    agent = await workspace_svc.get_workspace_agent(session, ctx.workspace_id)
    agent_file_ids = await agent_svc.get_agent_file_ids(session, agent.id) if agent else None

    fields = _decrypt_fields(profile)
    run = await case_match_svc.match_cases(
        session,
        user,
        fields,
        agent_file_ids=agent_file_ids,
        effective_workspace_id=ctx.workspace_id,
    )

    # Matching is a recomputation, not an append — clear this seat's prior
    # results for this conversation before inserting the new set, otherwise
    # plan.py's `ORDER BY score DESC LIMIT 3` (fed by every CaseMatch row
    # ever written) can pick stale/duplicate cases after a second /cases call.
    await session.execute(
        delete(CaseMatch).where(
            CaseMatch.workspace_id == ctx.workspace_id,
            CaseMatch.user_id == user.id,
            CaseMatch.conversation_id == profile.conversation_id,
        )
    )

    rows: list[CaseMatch] = []
    for r in run.results:
        row = CaseMatch(
            workspace_id=ctx.workspace_id,
            user_id=user.id,
            conversation_id=profile.conversation_id,
            file_id=r.file_id,
            filename=r.filename,
            score=r.score,
            rationale=r.rationale,
        )
        session.add(row)
        rows.append((row, r.card))
    await session.commit()

    await audit_svc.log(
        action="case_matched",
        user_id=user.id,
        resource_type="workspace",
        resource_id=ctx.workspace_id,
        details={"match_count": len(rows)},
    )

    return {
        "matches": [
            {
                "file_id": str(row.file_id),
                "filename": row.filename,
                "score": round(row.score, 2),
                "rationale": row.rationale,
                "title": card.title if card else None,
                "client": card.client if card else None,
                "category": card.category if card else None,
                "source_url": card.source_url if card else None,
                "summary": card.summary if card else None,
                "image_url": card.image_url if card else None,
            }
            for row, card in rows
        ]
    }


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
    # Only populated by GET /plans/{id} — list_plans/save_plan skip the
    # extra query since the plans list/save response never renders them.
    versions: list[PlanVersionOut] = []
    rating: PlanRatingOut | None = None


def _plan_out(plan, *, versions: list = (), rating=None) -> PlanOut:
    body = plan_svc.decrypt_body(plan)
    return PlanOut(
        id=plan.id,
        title=plan.title,
        status=plan.status,
        version=plan.version,
        core_idea=body.get("core_idea", ""),
        analogous_case=body.get("analogous_case", ""),
        adapted_plan=body.get("adapted_plan", []),
        budget=plan.budget,
        provenance=plan.provenance,
        created_at=plan.created_at,
        versions=[PlanVersionOut(version=v.version, created_at=v.created_at) for v in versions],
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
    """Draft the 4-part plan (core idea / analogous case / adapted plan /
    budget) but do not save it — the frontend shows this as a preview with
    a "Save as a plan" action (POST /client/plans) before it becomes a
    durable artifact. Not saving-by-default matters: a drafting call that
    fails partway (bad JSON, model hiccup) must not leave a half-formed
    Plan row behind."""
    _require_enabled()
    profile = await _get_or_create_profile(session, ctx.user, ctx.workspace_id)
    if profile.completed_at is None:
        _logger.warning(
            "plan/draft: workspace %s user %s intake incomplete at step %d",
            ctx.workspace_id,
            ctx.user.id,
            profile.step,
        )
        raise HTTPException(status_code=400, detail="Complete the intake before drafting a plan")

    fields = _decrypt_fields(profile)
    return await plan_svc.draft_plan(session, ctx.user, ctx.workspace_id, profile.conversation_id, fields)


@router.post("/plans", status_code=201, response_model=PlanOut)
async def save_plan(
    body: SavePlanIn,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PlanOut:
    _require_enabled()
    plan = await plan_svc.save_plan(session, ctx.user, ctx.workspace_id, body.conversation_id, body.model_dump())
    return _plan_out(plan)


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[PlanOut]:
    _require_enabled()
    plans = await plan_svc.list_plans(session, ctx.user, ctx.workspace_id)
    return [_plan_out(p) for p in plans]


@router.get("/plans/{plan_id}", response_model=PlanOut)
async def get_plan(
    plan_id: uuid.UUID,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PlanOut:
    _require_enabled()
    plan = await plan_svc.get_plan(session, ctx.user, ctx.workspace_id, plan_id)
    versions = await plan_svc.list_versions(session, plan_id)
    rating = await plan_rating_svc.get_rating(session, ctx.user, ctx.workspace_id, plan_id)
    return _plan_out(plan, versions=versions, rating=rating)


@router.post("/plans/{plan_id}/rating", response_model=PlanRatingOut)
async def rate_plan(
    plan_id: uuid.UUID,
    body: PlanRatingIn,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PlanRatingOut:
    _require_enabled()
    if ctx.is_preview:
        # Same reasoning as POST /client/leads below: a staff walkthrough
        # must not pollute the strategist's pre-call signal with a fake
        # rating — the UI shows "you're previewing" instead of a false
        # "Thanks — logged".
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


@router.post("/plans/{plan_id}/share")
async def share_plan(
    plan_id: uuid.UUID,
    ctx: Annotated[ClientContext, Depends(require_client_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Mint (or re-mint) a share token for a plan — GET /public/plans/{token}
    is the read-only page that resolves it. Re-minting invalidates the
    previous link (create_share_token overwrites share_token_hash)."""
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
        # A staff member clicking through the demo before the event must
        # never fire the real n8n webhook or create a row a strategist
        # sees in the Expert Leads inbox (app/routers/admin_leads.py) — see
        # app/deps.py::require_client_context.
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
