import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import run_chat_stream
from app.db import get_db
from app.deps import require_consent
from app.models.user import User
from app.services.chat_policy import prepare_chat

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    content: str
    model: str = "auto"
    agent_id: uuid.UUID | None = None


@router.post("")
async def chat(
    body: ChatRequest,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    # Classify + policy decision happens here so a deny can return HTTP 403.
    # Once StreamingResponse starts, status is committed to 200.
    prepared = await prepare_chat(
        session=session,
        user=user,
        conversation_id=body.conversation_id,
        user_content=body.content,
        requested_model=body.model,
        agent_id=body.agent_id,
    )
    return StreamingResponse(
        run_chat_stream(
            session=session,
            user_id=user.id,
            user=user,
            resolved_conversation_id=prepared.resolved_conversation_id,
            user_content=body.content,
            model_code=prepared.model_code,
            history=prepared.history,
            downgrade_to_local=prepared.downgrade_to_local,
            reasons=prepared.reasons,
            image_model_code=prepared.image_model_code,
            n8n_route=prepared.n8n_route,
            rag_context=prepared.rag_context,
            citations=prepared.citations,
            system_prompt=prepared.system_prompt,
            temperature=prepared.temperature,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
