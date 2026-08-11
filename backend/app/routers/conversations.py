import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import crypto
from app.db import get_db
from app.deps import get_current_user
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User

router = APIRouter(prefix="/conversations", tags=["conversations"])


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    model_used: str | None
    created_at: str


class ConversationDetail(BaseModel):
    id: uuid.UUID
    title: str | None
    agent_id: uuid.UUID | None = None
    messages: list[MessageOut]


def escape_like(term: str) -> str:
    """Escape LIKE wildcards so user input is matched literally."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ConversationOut]:
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    )
    if q and q.strip():
        stmt = stmt.where(
            Conversation.title.ilike(f"%{escape_like(q.strip())}%", escape="\\")
        )
    result = await session.execute(stmt)
    convs = result.scalars().all()
    return [
        ConversationOut(
            id=c.id,
            title=c.title,
            created_at=c.created_at.isoformat(),
            updated_at=c.updated_at.isoformat(),
        )
        for c in convs
    ]


@router.get("/{conv_id}", response_model=ConversationDetail)
async def get_conversation(
    conv_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationDetail:
    result = await session.execute(
        select(Conversation).where(
            Conversation.id == conv_id,
            Conversation.user_id == user.id,
        )
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msg_result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.created_at)
    )
    rows = msg_result.scalars().all()

    messages: list[MessageOut] = []
    for row in rows:
        plaintext = crypto.decrypt_message(
            row.content_ciphertext,
            row.content_nonce,
            row.content_tag,
            row.key_version,
        )
        messages.append(
            MessageOut(
                id=row.id,
                role=row.role,
                content=plaintext,
                model_used=row.model_used,
                created_at=row.created_at.isoformat(),
            )
        )

    return ConversationDetail(id=conv.id, title=conv.title, agent_id=conv.agent_id, messages=messages)
