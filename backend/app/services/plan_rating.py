"""
app/services/plan_rating.py

A client's NPS-style rating of a saved plan (PLAN.md Task 5.10) — collected
on the plan document so the expert on the handoff sees the client's
reaction before they call (surfaced via app/routers/admin_leads.py).

One row per (plan_id, user_id): upsert_rating() replaces rather than
appends, because the only real consumer (the leads inbox) wants a single
current value, not a history to reconcile against. The append-only
audit_log still gets a plan_rated row with the score on every submit
(§7.3), so the change trail exists without a second table.
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import PlanRating
from app.models.user import User
from app.services import audit as audit_svc
from app.services import plan as plan_svc


async def upsert_rating(
    session: AsyncSession,
    user: User,
    workspace_id: uuid.UUID,
    plan_id: uuid.UUID,
    *,
    score: int,
    comment: str | None,
) -> PlanRating:
    """Ownership + workspace scoping is delegated to plan_svc.get_plan() —
    a plan the caller doesn't own 404s exactly like GET /client/plans/{id}
    does, so a client can never see or affect another seat's rating."""
    await plan_svc.get_plan(session, user, workspace_id, plan_id)

    existing = (await session.execute(
        select(PlanRating).where(
            PlanRating.plan_id == plan_id, PlanRating.user_id == user.id
        )
    )).scalar_one_or_none()

    if existing is not None:
        existing.score = score
        existing.comment = comment
        rating = existing
    else:
        rating = PlanRating(
            plan_id=plan_id,
            workspace_id=workspace_id,
            user_id=user.id,
            score=score,
            comment=comment,
        )
        session.add(rating)

    await session.commit()
    await session.refresh(rating)

    await audit_svc.log(
        action="plan_rated",
        user_id=user.id,
        resource_type="plan",
        resource_id=plan_id,
        details={"score": score},
    )
    return rating


async def get_rating(
    session: AsyncSession, user: User, workspace_id: uuid.UUID, plan_id: uuid.UUID
) -> PlanRating | None:
    return (await session.execute(
        select(PlanRating).where(
            PlanRating.plan_id == plan_id,
            PlanRating.workspace_id == workspace_id,
            PlanRating.user_id == user.id,
        )
    )).scalar_one_or_none()


async def ratings_for_plan_ids(
    session: AsyncSession, plan_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, PlanRating]:
    """Batched lookup for the leads inbox (app/routers/admin_leads.py) — one
    query for every lead's plan rather than one per row."""
    if not plan_ids:
        return {}
    rows = (await session.execute(
        select(PlanRating).where(PlanRating.plan_id.in_(plan_ids))
    )).scalars().all()
    return {r.plan_id: r for r in rows}
