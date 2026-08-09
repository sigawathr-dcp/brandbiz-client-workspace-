"""
app/routers/agents.py

AI Agent CRUD and knowledge-file association endpoints.
prefix=/agents  tags=["agents"]

Visibility rules:
  - GET (list / detail): own agents + public+published agents
  - POST/PUT/DELETE: owner only
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import require_consent
from app.models.agent import VALID_STATUSES, VALID_VISIBILITIES
from app.models.user import User
from app.services import agent as agent_svc

router = APIRouter(prefix="/agents", tags=["agents"])


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------

class AgentCapabilities(BaseModel):
    web_search: bool = False
    think_longer: bool = False
    image_gen: bool = False
    video_gen: bool = False


class AgentCreateRequest(BaseModel):
    name: str
    provider: str
    model: str
    description: str | None = None
    instructions: str | None = None
    capabilities: AgentCapabilities = AgentCapabilities()
    creativity_level: int = 0
    visibility: str = "public"
    status: str = "published"
    avatar_color: str | None = None
    category: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty")
        return v[:100]

    @field_validator("creativity_level")
    @classmethod
    def clamp_creativity(cls, v: int) -> int:
        return max(0, min(100, v))


class AgentUpdateRequest(BaseModel):
    name: str | None = None
    provider: str | None = None
    model: str | None = None
    description: str | None = None
    instructions: str | None = None
    capabilities: AgentCapabilities | None = None
    creativity_level: int | None = None
    visibility: str | None = None
    status: str | None = None
    avatar_color: str | None = None
    category: str | None = None


class AgentResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    provider: str
    model: str
    description: str | None
    instructions: str | None
    capabilities: dict | None
    creativity_level: int
    visibility: str
    status: str
    avatar_color: str | None
    category: str | None
    created_at: datetime
    updated_at: datetime
    # Populated manually from joined User row
    creator_name: str | None = None


class AgentListResponse(BaseModel):
    items: list[AgentResponse]
    total: int


class KnowledgeAttachRequest(BaseModel):
    file_id: uuid.UUID


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _enrich_with_creator(
    session, agents
) -> list[AgentResponse]:
    """Join creator display_name for each agent."""
    if not agents:
        return []
    user_ids = list({a.user_id for a in agents})
    rows = await session.execute(
        select(User.id, User.display_name, User.google_email).where(
            User.id.in_(user_ids)
        )
    )
    name_map: dict[uuid.UUID, str] = {}
    for uid, display_name, email in rows.all():
        name_map[uid] = display_name or email

    result = []
    for agent in agents:
        data = AgentResponse.model_validate(agent)
        data.creator_name = name_map.get(agent.user_id)
        result.append(data)
    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=AgentListResponse)
async def list_agents(
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: str = Query(default="all", pattern="^(all|mine)$"),
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AgentListResponse:
    agents, total = await agent_svc.list_agents(
        session, user.id, scope=scope, q=q, category=category,
        limit=limit, offset=offset,
    )
    items = await _enrich_with_creator(session, agents)
    return AgentListResponse(items=items, total=total)


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(
    body: AgentCreateRequest,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AgentResponse:
    if body.visibility not in VALID_VISIBILITIES:
        raise HTTPException(400, f"visibility must be one of {VALID_VISIBILITIES}")
    if body.status not in VALID_STATUSES:
        raise HTTPException(400, f"status must be one of {VALID_STATUSES}")

    agent = await agent_svc.create_agent(
        session=session,
        user=user,
        name=body.name,
        provider=body.provider,
        model=body.model,
        description=body.description,
        instructions=body.instructions,
        capabilities=body.capabilities.model_dump(),
        creativity_level=body.creativity_level,
        visibility=body.visibility,
        status=body.status,
        avatar_color=body.avatar_color,
        category=body.category,
    )
    items = await _enrich_with_creator(session, [agent])
    return items[0]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: uuid.UUID,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AgentResponse:
    agent = await agent_svc.get_agent(session, agent_id, user.id)
    if agent is None:
        raise HTTPException(404, "Agent not found")
    items = await _enrich_with_creator(session, [agent])
    return items[0]


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID,
    body: AgentUpdateRequest,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AgentResponse:
    update_data = body.model_dump(exclude_none=True)
    # Flatten capabilities dict
    if "capabilities" in update_data:
        update_data["capabilities"] = update_data["capabilities"]
    agent = await agent_svc.update_agent(session, user, agent_id, **update_data)
    items = await _enrich_with_creator(session, [agent])
    return items[0]


@router.delete("/{agent_id}", status_code=204, response_model=None)
async def delete_agent(
    agent_id: uuid.UUID,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await agent_svc.delete_agent(session, user, agent_id)


@router.post("/{agent_id}/knowledge", status_code=204, response_model=None)
async def attach_knowledge(
    agent_id: uuid.UUID,
    body: KnowledgeAttachRequest,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await agent_svc.attach_knowledge_file(session, user, agent_id, body.file_id)


@router.delete("/{agent_id}/knowledge/{file_id}", status_code=204, response_model=None)
async def detach_knowledge(
    agent_id: uuid.UUID,
    file_id: uuid.UUID,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await agent_svc.detach_knowledge_file(session, user, agent_id, file_id)
