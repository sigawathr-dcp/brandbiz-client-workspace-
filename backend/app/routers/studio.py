"""
app/routers/studio.py

True Studio endpoints.

POST /studio/generate         — generate an asset (image: sync; video: async background; music: mock)
GET  /studio/generations      — list user's generations
GET  /studio/generations/{id} — get a single generation (for polling processing status)
GET  /studio/templates        — return seeded template gallery
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app import crypto
from app.db import get_db
from app.deps import require_consent
from app.llm.base import LLMProviderError
from app.models.user import User
from app.services import studio as studio_svc

router = APIRouter(prefix="/studio", tags=["studio"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    type: str          # "image" | "video" | "music"
    model_label: str
    prompt: str
    settings: dict[str, Any] = {}
    references: list[str] = []  # base64 data URLs; image mode only, not persisted
    parent_id: uuid.UUID | None = None  # source generation, when this is an edit/regenerate


class GenerationResponse(BaseModel):
    id: uuid.UUID
    type: str
    model_label: str
    status: str
    output_ref: str | None
    token_cost: int | None
    created_at: datetime
    parent_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class GenerationDetailResponse(GenerationResponse):
    """Adds the decrypted prompt + settings — only returned for the single-record
    detail endpoint (never the list endpoint), scoped to the owning user."""
    prompt: str
    settings: dict[str, Any] | None


class TemplateResponse(BaseModel):
    id: str
    type: str
    title: str
    preview_image: str | None = None
    description: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/generate", response_model=GenerationResponse)
async def generate(
    body: GenerateRequest,
    background: BackgroundTasks,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> GenerationResponse:
    try:
        gen = await studio_svc.generate(
            session=session,
            user=user,
            type_=body.type,
            model_label=body.model_label,
            prompt=body.prompt,
            settings=body.settings,
            references=body.references,
            background=background,
            parent_id=body.parent_id,
        )
    except LLMProviderError as exc:
        provider_code = exc.provider_code
        if provider_code == 429:
            raise HTTPException(status_code=429, detail=str(exc))
        raise HTTPException(status_code=502, detail=str(exc))
    return GenerationResponse.model_validate(gen)


@router.get("/generations", response_model=list[GenerationResponse])
async def list_generations(
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
    date_from: Annotated[datetime | None, Query(description="ISO 8601 lower bound")] = None,
    date_to: Annotated[datetime | None, Query(description="ISO 8601 upper bound")] = None,
    sort: Annotated[str, Query()] = "recent",
    context: Annotated[str | None, Query(description="'generate' or 'upload'")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[GenerationResponse]:
    # Studio media is always context=generate; upload context yields empty
    if context and context.lower() == "upload":
        return []
    gens = await studio_svc.list_generations(
        session, user.id,
        date_from=date_from, date_to=date_to,
        sort=sort, limit=limit, offset=offset,
    )
    return [GenerationResponse.model_validate(g) for g in gens]


@router.get("/generations/{gen_id}", response_model=GenerationDetailResponse)
async def get_generation(
    gen_id: uuid.UUID,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> GenerationDetailResponse:
    """Fetch a single generation by id, including its decrypted prompt + settings.

    Used both to poll processing status and to power the studio detail/edit view.
    Scoped to the owning user (§7.1 — decrypt-on-read for the owner only, same
    pattern as conversations.py).
    """
    gen = await studio_svc.get_generation(session, user.id, gen_id)
    if gen is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    prompt = crypto.decrypt(gen.prompt_ciphertext, gen.prompt_nonce, gen.prompt_tag, gen.key_version)
    return GenerationDetailResponse(
        id=gen.id,
        type=gen.type,
        model_label=gen.model_label,
        status=gen.status,
        output_ref=gen.output_ref,
        token_cost=gen.token_cost,
        created_at=gen.created_at,
        parent_id=gen.parent_id,
        prompt=prompt,
        settings=gen.settings,
    )


@router.get("/templates", response_model=list[TemplateResponse])
async def list_templates(
    user: Annotated[User, Depends(require_consent)],
    type: Annotated[str | None, Query()] = None,
) -> list[TemplateResponse]:
    templates = studio_svc.list_templates(type)
    return [TemplateResponse(**t) for t in templates]
