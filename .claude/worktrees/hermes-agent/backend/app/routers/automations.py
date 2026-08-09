"""
app/routers/automations.py

Gateway → n8n direction: allows the gateway to trigger n8n automations
on demand instead of waiting for the 5-minute poll schedule.

Endpoints
---------
POST /automations/n8n/label-inbox
    Fire the Gmail-labelling workflow immediately.  Authenticated users and
    service accounts can call this.  An admin can trigger it for any user;
    a regular user triggers it for themselves.

    The endpoint calls n8n_client.trigger() which POSTs to the n8n webhook
    URL configured in N8N_WEBHOOK_URL.  The webhook fires the same labelling
    agent that runs on the Gmail poll.

    On success: 200 with n8n's response body.
    On n8n unreachable (N8N_WEBHOOK_URL not configured): 503.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_principal
from app.models.user import User
from app.services import audit as audit_svc
from app.services import n8n_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/automations", tags=["automations"])


class AgentRequest(BaseModel):
    """Request body for the non-streaming agent endpoint used by n8n (and any other
    external caller that cannot consume SSE)."""
    content: str
    conversation_id: uuid.UUID | None = None
    model: str = "auto"


class AgentResponse(BaseModel):
    output: str
    conversation_id: str
    model_used: str
    tokens_input: int | None = None
    tokens_output: int | None = None


@router.post("/agent", response_model=AgentResponse)
async def agent(
    body: AgentRequest,
    user: Annotated[User, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AgentResponse:
    """Non-streaming chat endpoint for external callers (e.g. n8n LINE chatbot).

    Identical governance to POST /chat — prepare_chat() runs PolicyEngine.decide(),
    checks quota, detects PII tier, and either raises 403 or returns a PreparedChat.
    run_chat_collect() drives the same LangGraph, calls the same External APIs, and
    writes the same audit rows as the streaming chat page.

    Response field ``output`` is intentionally named to match n8n's AI Agent node
    convention (``{{ $json.output }}``) so the LINE reply node needs no change.
    """
    # Lazy imports: orchestrator pulls in LLM clients (openai, google-genai) that
    # are only available in the [external] extras. Importing here avoids the chain
    # being triggered at module-load time (which would break unit-test collection).
    from app.agents.orchestrator import run_chat_collect  # noqa: PLC0415
    from app.services.chat_policy import prepare_chat     # noqa: PLC0415

    if user.consent_acknowledged_at is None:
        raise HTTPException(status_code=403, detail="REQUIRES_CONSENT")

    # prepare_chat raises HTTPException(403) on policy deny — same gate as /chat
    prepared = await prepare_chat(
        session=session,
        user=user,
        conversation_id=body.conversation_id,
        user_content=body.content,
        requested_model=body.model,
    )

    try:
        result = await run_chat_collect(
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
        )
    except RuntimeError as exc:
        # A graph node failed (e.g. image generation with no OPENAI_API_KEY).
        # Surface it as 502 so the caller (n8n) sees a real failure rather than
        # a 200 with an empty output field.
        logger.warning("agent run failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))

    return AgentResponse(
        output=result["output"],
        conversation_id=str(prepared.resolved_conversation_id),
        model_used=result["model_used"],
        tokens_input=result["tokens_input"],
        tokens_output=result["tokens_output"],
    )


class LabelInboxRequest(BaseModel):
    """Optional hints forwarded to the n8n webhook payload."""
    scan_label: str | None = None   # if set, scan only this Gmail label
    note: str | None = None         # free-text annotation logged in audit


class LabelInboxResponse(BaseModel):
    triggered: bool
    n8n_response: Any = None


@router.post("/n8n/label-inbox", response_model=LabelInboxResponse)
async def trigger_label_inbox(
    body: LabelInboxRequest = LabelInboxRequest(),
    user: Annotated[User, Depends(get_principal)] = None,
    session: Annotated[AsyncSession, Depends(get_db)] = None,
) -> LabelInboxResponse:
    """Trigger the Gmail-labelling n8n workflow immediately.

    Fires an HTTP POST to the n8n webhook configured in N8N_WEBHOOK_URL.
    Returns n8n's response body on success.
    """
    if user.consent_acknowledged_at is None:
        raise HTTPException(status_code=403, detail="REQUIRES_CONSENT")

    webhook_payload: dict = {
        "action": "label_inbox",
        "triggered_by": user.google_email,
    }
    if body.scan_label:
        webhook_payload["scan_label"] = body.scan_label
    if body.note:
        webhook_payload["note"] = body.note

    try:
        n8n_response = await n8n_client.trigger(webhook_payload)
    except RuntimeError as exc:
        logger.warning("n8n trigger failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"n8n automation could not be triggered: {exc}",
        )

    await audit_svc.log(
        action="n8n_triggered",
        user_id=user.id,
        details={
            "automation": "label_inbox",
            "payload": webhook_payload,
            "n8n_status": "ok",
        },
    )
    await session.commit()

    return LabelInboxResponse(triggered=True, n8n_response=n8n_response)
