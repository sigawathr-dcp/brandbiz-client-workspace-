"""
app/routers/skills.py

Skill CRUD + upload endpoints.
prefix=/skills  tags=["skills"]

Visibility rules:
  - GET (list / detail): own skills + public skills
  - POST/PUT/DELETE: owner only

Agent-pin endpoints (attach/detach a skill to an agent, always-on injection)
live on the agents router — see routers/agents.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import require_consent
from app.models.skill import VALID_SKILL_VISIBILITIES
from app.models.user import User
from app.services import skill as skill_svc

router = APIRouter(prefix="/skills", tags=["skills"])


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------

class SkillCreateRequest(BaseModel):
    name: str
    description: str | None = None
    instructions: str | None = None
    visibility: str = "personal"
    category: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty")
        return v.strip()


class SkillUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    instructions: str | None = None
    enabled: bool | None = None
    visibility: str | None = None
    category: str | None = None


class SkillUploadRequest(BaseModel):
    markdown: str
    visibility: str = "personal"
    category: str | None = None


class SkillToggleRequest(BaseModel):
    enabled: bool


class SkillDraftMessage(BaseModel):
    role: str
    content: str


class SkillDraftRequest(BaseModel):
    messages: list[SkillDraftMessage]


class SkillDraft(BaseModel):
    name: str
    description: str
    instructions: str


class SkillDraftResponse(BaseModel):
    done: bool
    message: str | None = None
    draft: SkillDraft | None = None


class SkillResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: str | None
    instructions: str | None
    source_markdown: str | None
    enabled: bool
    visibility: str
    category: str | None
    created_at: datetime
    updated_at: datetime


class SkillListResponse(BaseModel):
    items: list[SkillResponse]
    total: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=SkillListResponse)
async def list_skills(
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: str = Query(default="all", pattern="^(all|mine)$"),
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SkillListResponse:
    skills, total = await skill_svc.list_skills(
        session, user.id, scope=scope, q=q, category=category,
        limit=limit, offset=offset,
    )
    return SkillListResponse(
        items=[SkillResponse.model_validate(s) for s in skills], total=total
    )


@router.post("", response_model=SkillResponse, status_code=201)
async def create_skill(
    body: SkillCreateRequest,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SkillResponse:
    if body.visibility not in VALID_SKILL_VISIBILITIES:
        raise HTTPException(400, f"visibility must be one of {VALID_SKILL_VISIBILITIES}")

    skill = await skill_svc.create_skill(
        session=session,
        user=user,
        name=body.name,
        description=body.description,
        instructions=body.instructions,
        visibility=body.visibility,
        category=body.category,
    )
    return SkillResponse.model_validate(skill)


@router.post("/upload", response_model=SkillResponse, status_code=201)
async def upload_skill(
    body: SkillUploadRequest,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SkillResponse:
    if body.visibility not in VALID_SKILL_VISIBILITIES:
        raise HTTPException(400, f"visibility must be one of {VALID_SKILL_VISIBILITIES}")

    skill = await skill_svc.create_skill_from_markdown(
        session=session,
        user=user,
        raw_markdown=body.markdown,
        visibility=body.visibility,
        category=body.category,
    )
    return SkillResponse.model_validate(skill)


@router.post("/draft", response_model=SkillDraftResponse)
async def draft_skill(
    body: SkillDraftRequest,
    user: Annotated[User, Depends(require_consent)],
) -> SkillDraftResponse:
    """"Create with AI": local-model-only conversational skill authoring.

    No DB session — nothing is persisted until the user reviews the draft and
    calls POST /skills. Must be declared before GET/PUT/DELETE /{skill_id} so
    "draft" isn't matched as a skill_id path param.
    """
    result = await skill_svc.draft_skill([m.model_dump() for m in body.messages])
    return SkillDraftResponse(**result)


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: uuid.UUID,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SkillResponse:
    skill = await skill_svc.get_skill(session, skill_id, user.id)
    if skill is None:
        raise HTTPException(404, "Skill not found")
    return SkillResponse.model_validate(skill)


@router.put("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: uuid.UUID,
    body: SkillUpdateRequest,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SkillResponse:
    update_data = body.model_dump(exclude_none=True)
    skill = await skill_svc.update_skill(session, user, skill_id, **update_data)
    return SkillResponse.model_validate(skill)


@router.post("/{skill_id}/toggle", response_model=SkillResponse)
async def toggle_skill(
    skill_id: uuid.UUID,
    body: SkillToggleRequest,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SkillResponse:
    skill = await skill_svc.update_skill(session, user, skill_id, enabled=body.enabled)
    return SkillResponse.model_validate(skill)


@router.delete("/{skill_id}", status_code=204, response_model=None)
async def delete_skill(
    skill_id: uuid.UUID,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await skill_svc.delete_skill(session, user, skill_id)
