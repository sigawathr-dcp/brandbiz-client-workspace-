"""
app/routers/client_admin.py

Admin provisioning for Client Workspaces (Phase 5 §2/§6, D21/D22):
  POST   /admin/clients                        — create a workspace
  GET    /admin/clients                        — list workspaces
  POST   /admin/clients/{workspace_id}/invites  — mint an invite link
  GET    /admin/clients/{workspace_id}/invites  — list invites for a workspace
  PUT    /admin/clients/{workspace_id}/agent    — assign an agent to a workspace
  GET    /admin/clients/{workspace_id}/agent    — read-only agent config view

require_admin-gated, like every other /admin/* router (D20) — not gated by
require_internal, since /admin/* already has its own, stricter check and no
client seat can ever hold role=ADMIN.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import require_admin
from app.models.file import File
from app.models.user import User
from app.services import agent as agent_svc
from app.services import skill as skill_svc
from app.services import workspace as workspace_svc

router = APIRouter(prefix="/admin/clients", tags=["client-workspaces"])


# The CLIENT_SURFACE_ENABLED kill switch is enforced by
# Depends(require_client_surface) at include_router() level in main.py, not
# per handler — see app/deps.py::require_client_surface for why.


class WorkspaceCreate(BaseModel):
    name: str
    slug: str
    kind: str = "demo"
    monthly_token_limit: int | None = None
    token_budget_limit: int | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    kind: str
    monthly_token_limit: int | None
    token_budget_limit: int | None
    token_budget_used: int
    contact_name: str | None
    contact_email: str | None
    contact_phone: str | None
    created_at: datetime
    archived_at: datetime | None

    model_config = {"from_attributes": True}


class InviteCreate(BaseModel):
    expires_in_hours: int = 72
    line_user_id: str | None = None
    contact_name: str | None = None


class InviteOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    expires_at: datetime
    redeemed_at: datetime | None
    line_user_id: str | None
    contact_name: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class InviteCreated(BaseModel):
    invite: InviteOut
    invite_url_path: str  # frontend joins this with its own origin
    raw_token: str  # shown exactly once — never retrievable again


@router.post("", status_code=201, response_model=WorkspaceOut)
async def create_workspace(
    body: WorkspaceCreate,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceOut:
    ws = await workspace_svc.create_workspace(
        session,
        name=body.name,
        slug=body.slug,
        kind=body.kind,
        monthly_token_limit=body.monthly_token_limit,
        token_budget_limit=body.token_budget_limit,
        contact_name=body.contact_name,
        contact_email=body.contact_email,
        contact_phone=body.contact_phone,
    )
    return WorkspaceOut.model_validate(ws)


@router.get("", response_model=list[WorkspaceOut])
async def list_workspaces(
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[WorkspaceOut]:
    rows = await workspace_svc.list_workspaces(session)
    return [WorkspaceOut.model_validate(r) for r in rows]


@router.post("/{workspace_id}/invites", status_code=201, response_model=InviteCreated)
async def create_invite(
    workspace_id: uuid.UUID,
    body: InviteCreate,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InviteCreated:
    invite, raw = await workspace_svc.create_invite(
        session,
        workspace_id=workspace_id,
        created_by=admin.id,
        expires_in_hours=body.expires_in_hours,
        line_user_id=body.line_user_id,
        contact_name=body.contact_name,
    )
    return InviteCreated(
        invite=InviteOut.model_validate(invite),
        invite_url_path=f"/try/{raw}",
        raw_token=raw,
    )


@router.get("/{workspace_id}/invites", response_model=list[InviteOut])
async def list_invites(
    workspace_id: uuid.UUID,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[InviteOut]:
    rows = await workspace_svc.list_invites(session, workspace_id)
    return [InviteOut.model_validate(r) for r in rows]


class AgentAssign(BaseModel):
    agent_id: uuid.UUID


@router.put("/{workspace_id}/agent", status_code=204, response_model=None)
async def assign_agent(
    workspace_id: uuid.UUID,
    body: AgentAssign,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Scope an existing internally-authored Agent (built via the normal
    /agent/create UI) to this client workspace — it becomes the workspace's
    น้อง brandbiz persona, reachable via GET /client/bootstrap. No separate
    "client agent" authoring flow exists."""
    await workspace_svc.assign_agent(
        session, workspace_id=workspace_id, agent_id=body.agent_id, admin_id=admin.id
    )


@router.get("/{workspace_id}/agent")
async def get_workspace_agent_config(
    workspace_id: uuid.UUID,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Read-only view backing the design's "Internal mode -> น้อง brandbiz agent"
    screen — everything here is authored in the existing internal UI
    (agent form, skills, knowledge attachment); no new authoring surface.
    Returns null fields when no agent is assigned yet."""
    agent = await workspace_svc.get_workspace_agent(session, workspace_id)
    if agent is None:
        return {"agent": None, "pinned_skills": [], "knowledge_files": []}

    skill_ids = await skill_svc.get_agent_skill_ids(session, agent.id)
    skills = []
    for skill_id in skill_ids:
        skill = await skill_svc.get_skill(session, skill_id, admin.id)
        if skill is not None:
            skills.append({"id": str(skill.id), "name": skill.name, "description": skill.description})

    file_ids = await agent_svc.get_agent_file_ids(session, agent.id)
    files = []
    if file_ids:
        rows = (await session.execute(select(File).where(File.id.in_(file_ids)))).scalars().all()
        files = [
            {
                "id": str(f.id),
                "filename": f.filename,
                "scope": f.scope,
                "workspace_id": str(f.workspace_id) if f.workspace_id else None,
            }
            for f in rows
        ]

    return {
        "agent": {
            "id": str(agent.id),
            "name": agent.name,
            "description": agent.description,
            "instructions": agent.instructions,
            "model": agent.model,
            "capabilities": agent.capabilities,
            "creativity_level": agent.creativity_level,
            "status": agent.status,
        },
        "pinned_skills": skills,
        "knowledge_files": files,
    }
