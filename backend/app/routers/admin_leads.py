"""
app/routers/admin_leads.py

Expert handoff inbox (Phase 5 §5, D21/D22) — require_admin-gated, like every
other /admin/* router (D20).
  GET   /admin/leads              — list, optionally filtered by status
  PATCH /admin/leads/{id}/assign  — assign to the calling admin
  PATCH /admin/leads/{id}/done    — mark handled
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import require_admin
from app.models.user import User
from app.services import lead as lead_svc
from app.services import plan_rating as plan_rating_svc

router = APIRouter(prefix="/admin/leads", tags=["client-workspaces"])


class LeadOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    plan_id: uuid.UUID | None
    contact_name: str | None
    contact_phone_or_line: str | None
    best_time: str | None
    status: str
    assigned_to: uuid.UUID | None
    n8n_error: str | None
    created_at: datetime
    # Only populated by GET "" (list_leads) — assign_lead/mark_done return a
    # single row straight from lead_svc without the rating join, so these
    # stay at their default None on those responses. That's not "rating
    # cleared" — it's simply not fetched for that call.
    nps_score: int | None = None
    nps_comment: str | None = None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[LeadOut])
async def list_leads(
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    status: str | None = None,
) -> list[LeadOut]:
    rows = await lead_svc.list_leads(session, status)
    plan_ids = [r.plan_id for r in rows if r.plan_id is not None]
    ratings = await plan_rating_svc.ratings_for_plan_ids(session, plan_ids)

    out: list[LeadOut] = []
    for r in rows:
        lead_out = LeadOut.model_validate(r)
        rating = ratings.get(r.plan_id) if r.plan_id is not None else None
        if rating is not None:
            lead_out.nps_score = rating.score
            lead_out.nps_comment = rating.comment
        out.append(lead_out)
    return out


@router.patch("/{lead_id}/assign", response_model=LeadOut)
async def assign_lead(
    lead_id: uuid.UUID,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> LeadOut:
    lead = await lead_svc.assign_lead(session, lead_id, admin.id)
    return LeadOut.model_validate(lead)


@router.patch("/{lead_id}/done", response_model=LeadOut)
async def mark_lead_done(
    lead_id: uuid.UUID,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> LeadOut:
    lead = await lead_svc.mark_done(session, lead_id)
    return LeadOut.model_validate(lead)
