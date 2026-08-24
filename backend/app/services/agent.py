"""
app/services/agent.py

CRUD + access helpers for AI Agents.
All write operations require ownership. Read operations grant access to own
agents plus any with visibility="public" and status="published".
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import VALID_STATUSES, VALID_VISIBILITIES, Agent, AgentFile
from app.models.file import LIBRARY_SCOPE, File
from app.models.user import User
from app.services import audit as audit_svc
from app.services.workspace import (
    is_client_seat,
    workspace_visibility_filter,
    workspace_visibility_filter_by_user_id,
)


def creativity_to_temperature(level: int) -> float:
    """Map a 0–100 creativity slider value to a 0.0–1.0 temperature."""
    return round(max(0, min(100, level)) / 100.0, 2)


def _accessible_filter(user_id: uuid.UUID):
    """SQLAlchemy WHERE clause: own agents OR public+published agents in the
    same tenant (D21/D22 — a client seat never sees an internal-shared
    public agent, or another workspace's; internal users are unaffected)."""
    return or_(
        Agent.user_id == user_id,
        and_(
            Agent.visibility == "public",
            Agent.status == "published",
            workspace_visibility_filter_by_user_id(user_id, Agent),
        ),
    )


async def get_agent(
    session: AsyncSession,
    agent_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Agent | None:
    """Return an agent the user is allowed to see, or None."""
    result = await session.execute(
        select(Agent).where(
            Agent.id == agent_id,
            _accessible_filter(user_id),
        )
    )
    return result.scalar_one_or_none()


async def get_agent_for_workspace(
    session: AsyncSession,
    agent_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> Agent | None:
    """Preview-mode variant of get_agent(): the caller (app/routers/client.py)
    has already resolved+authorized this agent against an explicit
    ClientContext.workspace_id via workspace_svc.get_workspace_agent() — which
    can differ from the requesting user's own user.workspace_id when a staff
    member is previewing a demo workspace (their own row stays
    workspace_id=None; see app/deps.py::ClientContext). _accessible_filter()'s
    per-user tenant subquery would otherwise 404 a real workspace-scoped
    agent for such a user, so this looks the agent up by the explicit
    workspace_id instead."""
    result = await session.execute(
        select(Agent).where(Agent.id == agent_id, Agent.workspace_id == workspace_id)
    )
    return result.scalar_one_or_none()


async def list_agents(
    session: AsyncSession,
    user_id: uuid.UUID,
    scope: str = "all",
    q: str | None = None,
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Agent], int]:
    """List agents with optional filtering.

    scope="all"  → public+published agents + own agents (any status)
    scope="mine" → only own agents (any status)
    """
    if scope == "mine":
        base = Agent.user_id == user_id
    else:
        base = _accessible_filter(user_id)

    filters: list[Any] = [base]
    if q:
        filters.append(Agent.name.ilike(f"%{q}%"))
    if category:
        filters.append(Agent.category == category)

    stmt = select(Agent).where(*filters).order_by(Agent.created_at.desc())
    total_result = await session.execute(select(Agent).where(*filters))
    total = len(total_result.scalars().all())

    paged = await session.execute(stmt.limit(limit).offset(offset))
    return paged.scalars().all(), total  # type: ignore[return-value]


async def create_agent(
    session: AsyncSession,
    user: User,
    name: str,
    provider: str,
    model: str,
    description: str | None = None,
    instructions: str | None = None,
    capabilities: dict | None = None,
    creativity_level: int = 0,
    visibility: str = "public",
    status: str = "published",
    avatar_color: str | None = None,
    category: str | None = None,
) -> Agent:
    if visibility not in VALID_VISIBILITIES:
        raise HTTPException(400, f"visibility must be one of {VALID_VISIBILITIES}")
    if status not in VALID_STATUSES:
        raise HTTPException(400, f"status must be one of {VALID_STATUSES}")
    # D23: every booth attendee shares one workspace, so a client seat's
    # "public" agent would be visible to every other attendee, not just to
    # Brandbiz staff. Coerce rather than 422 — routers/agents.py defaults
    # visibility to "public", so a 422 would break agent creation outright
    # for every client seat.
    if is_client_seat(user):
        visibility = "personal"

    agent = Agent(
        user_id=user.id,
        name=name,
        provider=provider,
        model=model,
        description=description,
        instructions=instructions,
        capabilities=capabilities or {},
        creativity_level=max(0, min(100, creativity_level)),
        visibility=visibility,
        status=status,
        avatar_color=avatar_color,
        category=category,
        # NULL for internal staff, unchanged from pre-D23 behavior.
        workspace_id=user.workspace_id,
    )
    session.add(agent)
    await session.commit()
    await session.refresh(agent)

    await audit_svc.log(
        action="agent_created",
        user_id=user.id,
        details={"agent_id": str(agent.id), "name": name, "model": model},
    )
    return agent


async def update_agent(
    session: AsyncSession,
    user: User,
    agent_id: uuid.UUID,
    **kwargs: Any,
) -> Agent:
    result = await session.execute(
        select(Agent).where(Agent.id == agent_id, Agent.user_id == user.id)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(404, "Agent not found")

    allowed = {
        "name", "description", "instructions", "provider", "model",
        "capabilities", "creativity_level", "visibility", "status",
        "avatar_color", "category",
    }
    for key, value in kwargs.items():
        if key not in allowed:
            continue
        if key == "visibility" and value not in VALID_VISIBILITIES:
            raise HTTPException(400, f"visibility must be one of {VALID_VISIBILITIES}")
        if key == "status" and value not in VALID_STATUSES:
            raise HTTPException(400, f"status must be one of {VALID_STATUSES}")
        if key == "creativity_level":
            value = max(0, min(100, value))
        setattr(agent, key, value)

    await session.commit()
    await session.refresh(agent)

    await audit_svc.log(
        action="agent_updated",
        user_id=user.id,
        details={"agent_id": str(agent_id), "fields": list(kwargs.keys())},
    )
    return agent


async def delete_agent(
    session: AsyncSession,
    user: User,
    agent_id: uuid.UUID,
) -> None:
    result = await session.execute(
        select(Agent).where(Agent.id == agent_id, Agent.user_id == user.id)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(404, "Agent not found")

    await session.execute(delete(Agent).where(Agent.id == agent_id))
    await session.commit()

    await audit_svc.log(
        action="agent_deleted",
        user_id=user.id,
        details={"agent_id": str(agent_id)},
    )


async def attach_knowledge_file(
    session: AsyncSession,
    user: User,
    agent_id: uuid.UUID,
    file_id: uuid.UUID,
) -> None:
    """Associate an already-uploaded file with an agent."""
    agent = await session.execute(
        select(Agent).where(Agent.id == agent_id, Agent.user_id == user.id)
    )
    if agent.scalar_one_or_none() is None:
        raise HTTPException(404, "Agent not found")

    # The file must be accessible (own personal, org-scoped within the same
    # tenant — D21/D22 — or the shared case library, ADR 0002; mirrors
    # app/tools/rag_search.py::_scope_filter)
    file_result = await session.execute(
        select(File).where(
            File.id == file_id,
            or_(
                and_(File.scope == "personal", File.user_id == user.id),
                and_(File.scope == "org", workspace_visibility_filter(user, File)),
                File.scope == LIBRARY_SCOPE,
            ),
        )
    )
    if file_result.scalar_one_or_none() is None:
        raise HTTPException(404, "File not found or not accessible")

    # Idempotent insert
    existing = await session.execute(
        select(AgentFile).where(
            AgentFile.agent_id == agent_id,
            AgentFile.file_id == file_id,
        )
    )
    if existing.scalar_one_or_none() is None:
        session.add(AgentFile(agent_id=agent_id, file_id=file_id))
        await session.commit()


async def detach_knowledge_file(
    session: AsyncSession,
    user: User,
    agent_id: uuid.UUID,
    file_id: uuid.UUID,
) -> None:
    agent = await session.execute(
        select(Agent).where(Agent.id == agent_id, Agent.user_id == user.id)
    )
    if agent.scalar_one_or_none() is None:
        raise HTTPException(404, "Agent not found")

    await session.execute(
        delete(AgentFile).where(
            AgentFile.agent_id == agent_id,
            AgentFile.file_id == file_id,
        )
    )
    await session.commit()


async def get_agent_file_ids(
    session: AsyncSession,
    agent_id: uuid.UUID,
) -> list[uuid.UUID]:
    """Return file IDs associated with this agent (for RAG scoping)."""
    result = await session.execute(
        select(AgentFile.file_id).where(AgentFile.agent_id == agent_id)
    )
    return [row[0] for row in result.all()]
