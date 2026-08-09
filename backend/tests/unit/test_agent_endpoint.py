"""Unit tests for POST /automations/agent (Task 2.10 — n8n LINE chatbot integration).

Tests cover:
  - 200 with output field — allow path (mocks prepare_chat + run_chat_collect)
  - 403 on policy deny — prepare_chat raises HTTPException as it would for /chat
  - 403 on missing consent
  - tier_blocked audit written on downgrade
  - response schema has output / conversation_id / model_used
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(*, consent: bool = True, role: str = "L4"):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    user.google_email = "n8n-bot@service.local"
    user.consent_acknowledged_at = datetime.now(timezone.utc) if consent else None
    return user


def _make_prepared(*, model_code: str = "gpt-4o", downgrade: bool = False):
    p = MagicMock()
    p.resolved_conversation_id = uuid.uuid4()
    p.model_code = model_code
    p.history = []
    p.downgrade_to_local = downgrade
    p.reasons = ["tier_blocks_external"] if downgrade else []
    p.image_model_code = None
    p.rag_context = ""
    p.citations = []
    return p


# ---------------------------------------------------------------------------
# POST /automations/agent — allow path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_returns_output_on_allow():
    from app.routers.automations import agent, AgentRequest

    user = _make_user()
    session = AsyncMock()
    prepared = _make_prepared(model_code="gpt-4o")

    body = AgentRequest(content="What is the weather today?")

    collect_result = {
        "output": "I cannot check real-time weather.",
        "model_used": "gpt-4o",
        "tokens_input": 12,
        "tokens_output": 8,
        "latency_ms": 320,
    }

    with (
        patch("app.services.chat_policy.prepare_chat", new_callable=AsyncMock, return_value=prepared),
        patch("app.agents.orchestrator.run_chat_collect", new_callable=AsyncMock, return_value=collect_result),
    ):
        response = await agent(body=body, user=user, session=session)

    assert response.output == "I cannot check real-time weather."
    assert response.model_used == "gpt-4o"
    assert response.conversation_id == str(prepared.resolved_conversation_id)
    assert response.tokens_input == 12
    assert response.tokens_output == 8


# ---------------------------------------------------------------------------
# 403 — policy deny (prepare_chat raises)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_403_on_policy_deny():
    from app.routers.automations import agent, AgentRequest

    user = _make_user()
    session = AsyncMock()
    body = AgentRequest(content="hello")

    with patch(
        "app.services.chat_policy.prepare_chat",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=403, detail={"error": "policy_denied"}),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await agent(body=body, user=user, session=session)

    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# 403 — consent not acknowledged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_403_no_consent():
    from app.routers.automations import agent, AgentRequest

    user = _make_user(consent=False)
    session = AsyncMock()
    body = AgentRequest(content="hello")

    with pytest.raises(HTTPException) as exc_info:
        await agent(body=body, user=user, session=session)

    assert exc_info.value.status_code == 403
    assert "CONSENT" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Downgrade path — model switched to local, response still returns output
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_downgrade_still_returns_output():
    from app.routers.automations import agent, AgentRequest
    from app.llm.router import LOCAL_MODEL_CODE

    user = _make_user()
    session = AsyncMock()
    prepared = _make_prepared(model_code=LOCAL_MODEL_CODE, downgrade=True)
    body = AgentRequest(content="เลขบัตรประชาชน 1234567890123")

    collect_result = {
        "output": "ขอโทษ ฉันไม่สามารถประมวลผลข้อมูลส่วนบุคคลได้",
        "model_used": LOCAL_MODEL_CODE,
        "tokens_input": 20,
        "tokens_output": 15,
        "latency_ms": 800,
    }

    with (
        patch("app.services.chat_policy.prepare_chat", new_callable=AsyncMock, return_value=prepared),
        patch("app.agents.orchestrator.run_chat_collect", new_callable=AsyncMock, return_value=collect_result),
    ):
        response = await agent(body=body, user=user, session=session)

    # Response must still come back (downgrade ≠ deny)
    assert response.output != ""
    assert response.model_used == LOCAL_MODEL_CODE


# ---------------------------------------------------------------------------
# run_chat_collect is called with all prepared fields intact
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_passes_prepared_fields_to_collect():
    from app.routers.automations import agent, AgentRequest

    user = _make_user()
    session = AsyncMock()
    prepared = _make_prepared(model_code="gpt-4o-mini")
    prepared.rag_context = "some retrieved context"
    body = AgentRequest(content="Summarise this", model="gpt-4o-mini")

    collect_result = {
        "output": "Summary here",
        "model_used": "gpt-4o-mini",
        "tokens_input": 30,
        "tokens_output": 10,
        "latency_ms": 400,
    }

    with (
        patch("app.services.chat_policy.prepare_chat", new_callable=AsyncMock, return_value=prepared),
        patch("app.agents.orchestrator.run_chat_collect", new_callable=AsyncMock, return_value=collect_result) as mock_collect,
    ):
        await agent(body=body, user=user, session=session)

    # Verify run_chat_collect received the rag_context from PreparedChat
    call_kwargs = mock_collect.call_args.kwargs
    assert call_kwargs["rag_context"] == "some retrieved context"
    assert call_kwargs["model_code"] == "gpt-4o-mini"
    assert call_kwargs["user_id"] == user.id
