import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import require_admin
from app.models.user import User
from app.services import reveal as reveal_svc

router = APIRouter(prefix="/reveal", tags=["reveal"])


class CreateRevealBody(BaseModel):
    target_message_id: uuid.UUID
    reason: str


class RevealRequestOut(BaseModel):
    id: uuid.UUID
    requester_id: uuid.UUID
    target_user_id: uuid.UUID | None
    target_message_id: uuid.UUID
    reason: str
    status: str
    approver_id: uuid.UUID | None
    approved_at: datetime | None
    expires_at: datetime | None
    viewed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ViewRevealOut(BaseModel):
    reveal_id: uuid.UUID
    plaintext: str
    viewed_at: str


@router.post("", response_model=RevealRequestOut, status_code=201)
async def create_reveal(
    body: CreateRevealBody,
    user: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RevealRequestOut:
    req = await reveal_svc.create_request(
        session,
        requester=user,
        target_message_id=body.target_message_id,
        reason=body.reason,
    )
    return RevealRequestOut.model_validate(req)


@router.post("/{reveal_id}/approve", response_model=RevealRequestOut)
async def approve_reveal(
    reveal_id: uuid.UUID,
    user: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RevealRequestOut:
    req = await reveal_svc.approve(session, reveal_id=reveal_id, approver=user)
    return RevealRequestOut.model_validate(req)


@router.post("/{reveal_id}/deny", response_model=RevealRequestOut)
async def deny_reveal(
    reveal_id: uuid.UUID,
    user: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RevealRequestOut:
    req = await reveal_svc.deny(session, reveal_id=reveal_id, approver=user)
    return RevealRequestOut.model_validate(req)


@router.get("/{reveal_id}/view", response_model=ViewRevealOut)
async def view_reveal(
    reveal_id: uuid.UUID,
    user: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ViewRevealOut:
    plaintext = await reveal_svc.view(session, reveal_id=reveal_id, requester=user)
    return ViewRevealOut(
        reveal_id=reveal_id,
        plaintext=plaintext,
        viewed_at=datetime.now(timezone.utc).isoformat(),
    )
