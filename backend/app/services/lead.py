"""
app/services/lead.py

Expert-handoff leads (Phase 5 §5, D21/D22) — "Talk to an expert", the
commercial point of the whole client-workspace funnel. submit() always
persists the Lead row first, then best-effort POSTs to the existing n8n
webhook (app/services/n8n_client.py) with a distinct "action" field so n8n
can branch, same convention as the admin server-down alert. A failed
webhook keeps the lead (with n8n_error recorded) rather than losing it —
the row survives for a human to retry or action manually.
"""
from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.models.plan import Plan
from app.models.user import User
from app.models.workspace import Workspace
from app.services import audit as audit_svc
from app.services import n8n_client


async def submit(
    session: AsyncSession,
    user: User,
    *,
    plan_id: uuid.UUID | None,
    contact_name: str | None,
    contact_phone_or_line: str | None,
    best_time: str | None,
) -> Lead:
    workspace = (await session.execute(
        select(Workspace).where(Workspace.id == user.workspace_id)
    )).scalar_one_or_none()
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    plan_title = None
    if plan_id is not None:
        plan = (await session.execute(
            select(Plan).where(
                Plan.id == plan_id, Plan.workspace_id == user.workspace_id, Plan.user_id == user.id
            )
        )).scalar_one_or_none()
        if plan is None:
            raise HTTPException(status_code=404, detail="Plan not found")
        plan_title = plan.title

    lead = Lead(
        workspace_id=user.workspace_id,
        user_id=user.id,
        plan_id=plan_id,
        contact_name=contact_name,
        contact_phone_or_line=contact_phone_or_line,
        best_time=best_time,
        status="new",
    )
    session.add(lead)
    await session.commit()
    await session.refresh(lead)

    try:
        response = await n8n_client.trigger({
            "action": "brandbiz_lead",
            "workspace": {"id": str(workspace.id), "name": workspace.name},
            "contact_name": contact_name,
            "contact_phone_or_line": contact_phone_or_line,
            "best_time": best_time,
            "plan_title": plan_title,
            "lead_id": str(lead.id),
        })
        lead.n8n_response = response
    except RuntimeError as exc:
        lead.n8n_error = str(exc)[:500]
    await session.commit()
    await session.refresh(lead)

    await audit_svc.log(
        action="lead_submitted",
        user_id=user.id,
        resource_type="lead",
        resource_id=lead.id,
        details={"workspace_id": str(workspace.id), "plan_id": str(plan_id) if plan_id else None},
    )
    return lead


async def list_leads(session: AsyncSession, status: str | None = None) -> list[Lead]:
    stmt = select(Lead).order_by(Lead.created_at.desc())
    if status:
        stmt = stmt.where(Lead.status == status)
    return list((await session.execute(stmt)).scalars().all())


async def assign_lead(session: AsyncSession, lead_id: uuid.UUID, assignee_id: uuid.UUID) -> Lead:
    lead = (await session.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead.assigned_to = assignee_id
    lead.status = "assigned"
    await session.commit()
    await session.refresh(lead)
    return lead


async def mark_done(session: AsyncSession, lead_id: uuid.UUID) -> Lead:
    lead = (await session.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead.status = "done"
    await session.commit()
    await session.refresh(lead)
    return lead
