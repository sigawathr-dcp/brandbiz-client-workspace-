"""Unit tests for the OpenAI-compat passthrough endpoint (Task 2.10, Part A).

Tests cover:
  - Governance: policy deny → 403 in OpenAI error format
  - Governance: tier downgrade → local model used, audit logged
  - Tool-calling passthrough: tools array forwarded intact (not stripped)
  - Non-streaming path returns JSON directly
  - Provider without raw_chat raises 400 (Anthropic/Gemini v1 guard)
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(*, role="L4", consent=True):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    user.google_email = "bot@service.local"
    user.consent_acknowledged_at = datetime.now(timezone.utc) if consent else None
    return user


def _make_decision(*, allowed=True, model_code="gpt-4o", downgrade=False, reasons=None):
    decision = MagicMock()
    decision.allowed = allowed
    decision.model_code = model_code
    decision.downgrade_to_local = downgrade
    decision.reasons = reasons or []
    return decision


# ---------------------------------------------------------------------------
# _text_from_messages
# ---------------------------------------------------------------------------

class TestTextFromMessages:
    def test_plain_string_content(self):
        from app.routers.openai_compat import CompatMessage, _text_from_messages

        msgs = [
            CompatMessage(role="user", content="Hello world"),
            CompatMessage(role="assistant", content="Hi there"),
        ]
        assert _text_from_messages(msgs) == "Hello world\nHi there"

    def test_list_content_extracts_text_parts(self):
        from app.routers.openai_compat import CompatMessage, _text_from_messages

        msgs = [
            CompatMessage(role="user", content=[
                {"type": "text", "text": "Describe this"},
                {"type": "image_url", "image_url": {"url": "http://example.com/img.png"}},
            ])
        ]
        assert _text_from_messages(msgs) == "Describe this"

    def test_tool_call_messages_skipped_gracefully(self):
        """Messages without string content (e.g. tool result) don't crash."""
        from app.routers.openai_compat import CompatMessage, _text_from_messages

        msgs = [
            CompatMessage(role="tool", content=None, tool_call_id="call_abc"),
        ]
        result = _text_from_messages(msgs)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _openai_error
# ---------------------------------------------------------------------------

class TestOpenAIError:
    def test_shape(self):
        from app.routers.openai_compat import _openai_error
        from fastapi import HTTPException

        exc = _openai_error("Some policy error", error_type="policy_denied", status=403)
        assert isinstance(exc, HTTPException)
        assert exc.status_code == 403
        assert exc.detail["error"]["type"] == "policy_denied"
        assert "policy" in exc.detail["error"]["message"].lower()


# ---------------------------------------------------------------------------
# POST /v1/chat/completions — non-streaming governance scenarios
# ---------------------------------------------------------------------------

@pytest.fixture()
def _mock_deps():
    """Shared mocks for the compat router governance path."""
    user = _make_user()
    session = AsyncMock()

    mock_result = MagicMock()
    mock_result.one_or_none.return_value = None  # no cost row → zero cost
    session.execute = AsyncMock(return_value=mock_result)
    session.commit = AsyncMock()

    return user, session


@pytest.mark.asyncio
async def test_policy_deny_returns_openai_error_shape(_mock_deps):
    """A policy deny must return an HTTP 403 with OpenAI-shaped error body."""
    from fastapi import HTTPException

    from app.routers.openai_compat import create_chat_completion, CompatRequest

    user, session = _mock_deps
    decision = _make_decision(allowed=False, reasons=["role_not_allowed"])

    body = CompatRequest(
        model="gpt-4o",
        messages=[{"role": "user", "content": "hello"}],
    )

    with (
        patch("app.routers.openai_compat.detect_tier") as mock_tier,
        patch("app.routers.openai_compat.PolicyEngine") as MockPE,
        patch("app.routers.openai_compat.audit_svc.log", new_callable=AsyncMock),
        patch("app.routers.openai_compat.classify_intent", new_callable=AsyncMock, return_value="gpt-4o"),
    ):
        mock_tier.return_value = MagicMock(
            value="TIER_1_PUBLIC",
            rank=1,
            __class__=MagicMock(TIER_3_CONFIDENTIAL=MagicMock(rank=3)),
        )
        instance = AsyncMock()
        instance.decide = AsyncMock(return_value=decision)
        MockPE.return_value = instance

        with pytest.raises(HTTPException) as exc_info:
            await create_chat_completion(
                request=MagicMock(), body=body, user=user, session=session
            )

    assert exc_info.value.status_code == 403
    assert "error" in exc_info.value.detail
    assert exc_info.value.detail["error"]["type"] == "policy_denied"


@pytest.mark.asyncio
async def test_downgrade_uses_local_model(_mock_deps):
    """A tier downgrade routes to the local model and audits tier_blocked."""
    from app.routers.openai_compat import create_chat_completion, CompatRequest
    from app.llm.router import DEFAULT_MODEL_CODE

    user, session = _mock_deps
    decision = _make_decision(
        allowed=True,
        model_code=DEFAULT_MODEL_CODE,
        downgrade=True,
        reasons=["tier_blocks_external"],
    )

    body = CompatRequest(
        model="gpt-4o",
        messages=[{"role": "user", "content": "hello"}],
        stream=False,
    )

    mock_client = MagicMock()
    mock_client.raw_chat = AsyncMock(return_value={
        "id": "chatcmpl-123",
        "choices": [{"message": {"role": "assistant", "content": "Hi"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3},
    })

    with (
        patch("app.routers.openai_compat.detect_tier") as mock_tier,
        patch("app.routers.openai_compat.PolicyEngine") as MockPE,
        patch("app.routers.openai_compat.audit_svc.log", new_callable=AsyncMock) as mock_audit,
        patch("app.routers.openai_compat.get_router") as mock_router,
        patch("app.routers.openai_compat.classify_intent", new_callable=AsyncMock, return_value="gpt-4o"),
        patch("app.routers.openai_compat.quota_svc.consume", new_callable=AsyncMock),
    ):
        mock_tier.return_value = MagicMock(
            value="TIER_2_INTERNAL",
            rank=2,
            __class__=MagicMock(TIER_3_CONFIDENTIAL=MagicMock(rank=3)),
        )
        instance = AsyncMock()
        instance.decide = AsyncMock(return_value=decision)
        MockPE.return_value = instance
        mock_router.return_value.get.return_value = mock_client

        await create_chat_completion(
            request=MagicMock(), body=body, user=user, session=session
        )

    # Audit must include a tier_blocked event (log() is called with keyword args)
    audit_actions = [call.kwargs.get("action") or (call.args[0] if call.args else None)
                     for call in mock_audit.call_args_list]
    assert "tier_blocked" in audit_actions, f"Expected tier_blocked audit, got {audit_actions}"

    # Client must be called with the local model (mock_router.get was called with DEFAULT_MODEL_CODE)
    mock_router.return_value.get.assert_called_with(DEFAULT_MODEL_CODE)


@pytest.mark.asyncio
async def test_tools_passed_through_to_provider(_mock_deps):
    """The tools array from the request must reach the provider unchanged."""
    from app.routers.openai_compat import create_chat_completion, CompatRequest

    user, session = _mock_deps
    decision = _make_decision(model_code="gpt-4o")

    tools = [
        {
            "type": "function",
            "function": {
                "name": "read_gmail_labels",
                "description": "Read all Gmail labels",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]

    body = CompatRequest(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Label this email"}],
        tools=tools,
        stream=False,
    )

    mock_client = MagicMock()
    mock_client.raw_chat = AsyncMock(return_value={
        "id": "chatcmpl-abc",
        "choices": [{"message": {"role": "assistant", "tool_calls": [{"id": "call1"}]}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    })

    with (
        patch("app.routers.openai_compat.detect_tier") as mock_tier,
        patch("app.routers.openai_compat.PolicyEngine") as MockPE,
        patch("app.routers.openai_compat.audit_svc.log", new_callable=AsyncMock),
        patch("app.routers.openai_compat.get_router") as mock_router,
        patch("app.routers.openai_compat.classify_intent", new_callable=AsyncMock, return_value="gpt-4o"),
        patch("app.routers.openai_compat.quota_svc.consume", new_callable=AsyncMock),
    ):
        mock_tier.return_value = MagicMock(
            value="TIER_1_PUBLIC",
            rank=1,
            __class__=MagicMock(TIER_3_CONFIDENTIAL=MagicMock(rank=3)),
        )
        instance = AsyncMock()
        instance.decide = AsyncMock(return_value=decision)
        MockPE.return_value = instance
        mock_router.return_value.get.return_value = mock_client

        await create_chat_completion(
            request=MagicMock(), body=body, user=user, session=session
        )

    # raw_chat must have been called with tools=tools
    mock_client.raw_chat.assert_awaited_once()
    call_kwargs = mock_client.raw_chat.call_args.kwargs
    assert call_kwargs.get("tools") == tools, "tools array must pass through unchanged"


@pytest.mark.asyncio
async def test_provider_without_raw_chat_raises_400(_mock_deps):
    """Anthropic/Gemini clients (no raw_chat) must return a 400, not crash."""
    from fastapi import HTTPException
    from app.routers.openai_compat import create_chat_completion, CompatRequest

    user, session = _mock_deps
    decision = _make_decision(model_code="claude-sonnet-4")

    body = CompatRequest(
        model="claude-sonnet-4",
        messages=[{"role": "user", "content": "hello"}],
    )

    # A client without raw_chat / raw_streaming_chat attributes
    mock_client = MagicMock(spec=[])  # empty spec = no attributes

    with (
        patch("app.routers.openai_compat.detect_tier") as mock_tier,
        patch("app.routers.openai_compat.PolicyEngine") as MockPE,
        patch("app.routers.openai_compat.audit_svc.log", new_callable=AsyncMock),
        patch("app.routers.openai_compat.get_router") as mock_router,
        patch("app.routers.openai_compat.classify_intent", new_callable=AsyncMock, return_value="claude-sonnet-4"),
    ):
        mock_tier.return_value = MagicMock(
            value="TIER_1_PUBLIC",
            rank=1,
            __class__=MagicMock(TIER_3_CONFIDENTIAL=MagicMock(rank=3)),
        )
        instance = AsyncMock()
        instance.decide = AsyncMock(return_value=decision)
        MockPE.return_value = instance
        mock_router.return_value.get.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            await create_chat_completion(
                request=MagicMock(), body=body, user=user, session=session
            )

    assert exc_info.value.status_code == 400
    assert "passthrough" in exc_info.value.detail["error"]["message"].lower()


@pytest.mark.asyncio
async def test_consent_not_acknowledged_returns_403():
    from fastapi import HTTPException
    from app.routers.openai_compat import create_chat_completion, CompatRequest

    user = _make_user(consent=False)
    session = AsyncMock()
    body = CompatRequest(model="gpt-4o", messages=[{"role": "user", "content": "hi"}])

    with pytest.raises(HTTPException) as exc_info:
        await create_chat_completion(
            request=MagicMock(), body=body, user=user, session=session
        )

    assert exc_info.value.status_code == 403
