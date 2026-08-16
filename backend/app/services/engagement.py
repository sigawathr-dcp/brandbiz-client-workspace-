"""
app/services/engagement.py

The single owner of a client seat's journey state through the 4-step
funnel (Interview -> Market scan -> Case match -> Plan & budget) — see
app/models/engagement.py for the full rationale. Every step transition
goes through mark_step(); nothing else in the codebase writes
engagement_steps.status.

Before this module existed, "which step is this client on" had no
server-side representation at all — it was reconstructed from scratch in
the browser on every load (frontend-chat/components/client/journey.ts).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.engagement import STEP_KEYS, Engagement, EngagementStep
from app.models.intake import IntakeScript
from app.models.user import User
from app.services import audit as audit_svc
from app.services import workspace as workspace_svc


async def get_active_script_id(session: AsyncSession) -> uuid.UUID | None:
    """The currently-published intake script — pinned onto a new
    Engagement so a future republish never reinterprets its stored
    answers (see app/models/intake.py::IntakeScript)."""
    result = await session.execute(
        select(IntakeScript.id).where(IntakeScript.active.is_(True)).order_by(IntakeScript.version.desc())
    )
    return result.scalars().first()


async def _create_engagement(
    session: AsyncSession, user: User, workspace_id: uuid.UUID, *, seq: int
) -> Engagement:
    workspace_agent = await workspace_svc.get_workspace_agent(session, workspace_id)
    conv = Conversation(
        user_id=user.id,
        agent_id=workspace_agent.id if workspace_agent else None,
        workspace_id=workspace_id,
        kind="client_workspace",
    )
    session.add(conv)
    await session.flush()

    script_id = await get_active_script_id(session)
    engagement = Engagement(
        workspace_id=workspace_id,
        user_id=user.id,
        seq=seq,
        conversation_id=conv.id,
        intake_script_id=script_id,
        status="active",
    )
    session.add(engagement)
    await session.flush()

    for step_no, step_key in enumerate(STEP_KEYS, start=1):
        session.add(EngagementStep(engagement_id=engagement.id, step_no=step_no, step_key=step_key))

    await session.commit()
    await session.refresh(engagement)
    return engagement


async def get_or_create_active(session: AsyncSession, user: User, workspace_id: uuid.UUID) -> Engagement:
    """The seat's current engagement — creates the first one (seq=1) on
    first bootstrap, exactly like the old _get_or_create_profile did for
    ClientProfile."""
    result = await session.execute(
        select(Engagement).where(
            Engagement.workspace_id == workspace_id,
            Engagement.user_id == user.id,
            Engagement.status == "active",
        )
    )
    engagement = result.scalars().first()
    if engagement is not None:
        return engagement
    return await _create_engagement(session, user, workspace_id, seq=1)


async def start_new(session: AsyncSession, user: User, workspace_id: uuid.UUID) -> Engagement:
    """A returning client starting a fresh brief (POST /client/engagements).
    The old schema's uq_client_profiles_workspace_user made this
    impossible — a seat got exactly one intake forever."""
    current = await session.execute(
        select(Engagement).where(
            Engagement.workspace_id == workspace_id,
            Engagement.user_id == user.id,
            Engagement.status == "active",
        )
    )
    prior = current.scalars().first()
    if prior is not None:
        prior.status = "completed"
        prior.completed_at = datetime.now(timezone.utc)

    max_seq = (
        await session.execute(
            select(Engagement.seq)
            .where(Engagement.workspace_id == workspace_id, Engagement.user_id == user.id)
            .order_by(Engagement.seq.desc())
            .limit(1)
        )
    ).scalar_one_or_none() or 0

    engagement = await _create_engagement(session, user, workspace_id, seq=max_seq + 1)
    await audit_svc.log(
        action="engagement_started",
        user_id=user.id,
        resource_type="workspace",
        resource_id=workspace_id,
        details={"engagement_id": str(engagement.id), "seq": engagement.seq},
    )
    return engagement


async def set_active_plan(session: AsyncSession, engagement: Engagement, plan_id: uuid.UUID) -> Engagement:
    """Server-side replacement for the old `bb:activePlan:*` localStorage
    key — which plan a PUT /client/plans/{id} revision targets, and which
    the switcher checkmarks, is now engagement state rather than a
    per-device browser preference (see app/models/engagement.py's
    Engagement.active_plan_id docstring). Ownership of `plan_id` is the
    caller's responsibility (the router resolves it via plan_svc.get_plan
    first, which 404s on a plan the seat doesn't own)."""
    engagement.active_plan_id = plan_id
    session.add(engagement)
    await session.commit()
    await session.refresh(engagement)
    return engagement


async def get_steps(session: AsyncSession, engagement_id: uuid.UUID) -> dict[str, EngagementStep]:
    """All 4 steps for an engagement, keyed by step_key — the shape every
    router handler and bootstrap needs."""
    result = await session.execute(
        select(EngagementStep).where(EngagementStep.engagement_id == engagement_id)
    )
    return {row.step_key: row for row in result.scalars().all()}


async def get_step(session: AsyncSession, engagement_id: uuid.UUID, step_key: str) -> EngagementStep:
    result = await session.execute(
        select(EngagementStep).where(
            EngagementStep.engagement_id == engagement_id, EngagementStep.step_key == step_key
        )
    )
    step = result.scalars().first()
    if step is None:
        raise HTTPException(status_code=500, detail=f"Engagement step '{step_key}' is missing")
    return step


async def mark_step(
    session: AsyncSession,
    step: EngagementStep,
    status: str,
    *,
    progress_current: int | None = None,
    progress_total: int | None = None,
    error_code: str | None = None,
    error_detail: str | None = None,
    commit: bool = True,
) -> EngagementStep:
    """The only function allowed to write engagement_steps.status. Every
    endpoint that runs a step (research/cases/plan draft) calls this
    before starting ('running') and after finishing ('done'/'failed')."""
    now = datetime.now(timezone.utc)
    if status == "running":
        step.attempt_count += 1
        if step.started_at is None:
            step.started_at = now
        step.error_code = None
        step.error_detail = None
    elif status in ("done", "failed"):
        step.completed_at = now
        if status == "failed":
            step.error_code = error_code
            step.error_detail = error_detail

    step.status = status
    if progress_current is not None:
        step.progress_current = progress_current
    if progress_total is not None:
        step.progress_total = progress_total

    session.add(step)
    if commit:
        await session.commit()
        await session.refresh(step)
    return step
