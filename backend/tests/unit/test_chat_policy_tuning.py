"""Unit tests for G-A1's mode resolution inside chat_policy.prepare_chat.

Covers:
- An agent with capabilities.think_longer=True sets the default mode to
  THINKING when the caller didn't request one explicitly.
- An explicit request mode always wins over the agent default.
- No agent (or think_longer unset/False) defaults to INSTANT.

Harness mirrors test_chat_policy_skills.py's _run_prepare — same mocking
strategy (PolicyEngine/rag_search/classify_intent/settings/alert/audit all
patched at the module level chat_policy imports them from).
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.router import DEFAULT_MODEL_CODE
from app.llm.tuning import ReasoningLevel, ResponseMode
from app.services.chat_policy import prepare_chat


def _make_user(role: str = "L3") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    user.workspace_id = None
    return user


def _make_agent(capabilities: dict | None = None) -> MagicMock:
    agent = MagicMock()
    agent.id = uuid.uuid4()
    agent.instructions = "You are helpful."
    agent.creativity_level = 50
    agent.capabilities = capabilities or {}
    agent.model = "claude-sonnet-4"
    return agent


def _allowed_decision(model_code: str = DEFAULT_MODEL_CODE):
    from app.services.policy_engine import PolicyDecision
    return PolicyDecision(allowed=True, model_code=model_code, downgrade_to_local=False, reasons=[])


def _new_conversation_session() -> AsyncMock:
    # Two empty message windows (chat + unfiltered — see
    # chat_policy.load_history_messages), then the auto-title sa_update.
    msg_result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = []
    msg_result.scalars.return_value = scalars

    update_result = MagicMock()

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[msg_result, msg_result, update_result])
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


async def _run_prepare(
    *,
    agent_id=None,
    agent=None,
    mode=None,
    reasoning_level=None,
):
    user = _make_user()
    session = _new_conversation_session()

    with patch("app.services.chat_policy.PolicyEngine") as mock_pe, \
         patch("app.services.chat_policy.rag_search") as mock_rag, \
         patch("app.services.chat_policy.classify_intent", new_callable=AsyncMock, return_value=DEFAULT_MODEL_CODE), \
         patch("app.services.chat_policy.settings") as mock_settings, \
         patch("app.services.chat_policy.alert") as mock_alert, \
         patch("app.services.chat_policy.agent_svc.get_agent", new_callable=AsyncMock, return_value=agent), \
         patch("app.services.chat_policy.agent_svc.get_agent_file_ids", new_callable=AsyncMock, return_value=[]), \
         patch("app.services.chat_policy.skill_svc.get_agent_skill_ids", new_callable=AsyncMock, return_value=[]), \
         patch("app.services.chat_policy.skill_svc.get_enabled_skills", new_callable=AsyncMock, return_value=[]), \
         patch("app.services.chat_policy.audit_svc.log", new_callable=AsyncMock):
        mock_pe.return_value.decide = AsyncMock(return_value=_allowed_decision())
        mock_rag.retrieve = AsyncMock(return_value=[])
        mock_rag.build_context_block.return_value = ""
        mock_rag.citations.return_value = []
        mock_settings.n8n_webhook_url = ""
        mock_alert.matches_alert.return_value = False

        return await prepare_chat(
            session=session,
            user=user,
            conversation_id=None,
            user_content="hello",
            requested_model="auto",
            agent_id=agent_id,
            mode=mode,
            reasoning_level=reasoning_level,
        )


class TestModeDefaulting:
    async def test_no_agent_defaults_to_instant(self):
        prepared = await _run_prepare()
        assert prepared.tuning.mode is ResponseMode.INSTANT

    async def test_agent_without_think_longer_defaults_to_instant(self):
        agent = _make_agent(capabilities={"think_longer": False})
        prepared = await _run_prepare(agent_id=agent.id, agent=agent)
        assert prepared.tuning.mode is ResponseMode.INSTANT

    async def test_agent_with_think_longer_defaults_to_thinking(self):
        agent = _make_agent(capabilities={"think_longer": True})
        prepared = await _run_prepare(agent_id=agent.id, agent=agent)
        assert prepared.tuning.mode is ResponseMode.THINKING

    async def test_explicit_mode_wins_over_think_longer_agent(self):
        """A user explicitly picking Instant must not be silently upgraded to
        Thinking just because the agent's capabilities blob says so —
        permissions live in PolicyEngine, not this JSONB flag."""
        agent = _make_agent(capabilities={"think_longer": True})
        prepared = await _run_prepare(agent_id=agent.id, agent=agent, mode=ResponseMode.INSTANT)
        assert prepared.tuning.mode is ResponseMode.INSTANT

    async def test_explicit_mode_wins_with_no_agent(self):
        prepared = await _run_prepare(mode=ResponseMode.PRO)
        assert prepared.tuning.mode is ResponseMode.PRO

    async def test_reasoning_level_carried_through_to_tuning(self):
        prepared = await _run_prepare(mode=ResponseMode.THINKING, reasoning_level=ReasoningLevel.HIGH)
        assert prepared.tuning.reasoning_level is ReasoningLevel.HIGH
        assert prepared.tuning.effective_reasoning() is ReasoningLevel.HIGH

    async def test_agent_temperature_still_carried_into_tuning(self):
        """Reviving think_longer must not disturb the existing
        creativity_level -> temperature mapping."""
        agent = _make_agent(capabilities={"think_longer": True})
        agent.creativity_level = 100
        prepared = await _run_prepare(agent_id=agent.id, agent=agent)
        assert prepared.tuning.temperature == 1.0


# ---------------------------------------------------------------------------
# ChatRequest validation — invalid mode/reasoning_level values 422 before
# any LLM call, same as any other Pydantic field.
# ---------------------------------------------------------------------------

class TestChatRequestValidation:
    def test_invalid_mode_raises_validation_error(self):
        from pydantic import ValidationError
        from app.routers.chat import ChatRequest

        with pytest.raises(ValidationError):
            ChatRequest(content="hi", mode="banana")

    def test_invalid_reasoning_level_raises_validation_error(self):
        from pydantic import ValidationError
        from app.routers.chat import ChatRequest

        with pytest.raises(ValidationError):
            ChatRequest(content="hi", reasoning_level="extreme")

    def test_valid_mode_and_reasoning_level_accepted(self):
        from app.routers.chat import ChatRequest

        body = ChatRequest(content="hi", mode="thinking", reasoning_level="high")
        assert body.mode is ResponseMode.THINKING
        assert body.reasoning_level is ReasoningLevel.HIGH

    def test_mode_and_reasoning_level_default_to_none(self):
        from app.routers.chat import ChatRequest

        body = ChatRequest(content="hi")
        assert body.mode is None
        assert body.reasoning_level is None
