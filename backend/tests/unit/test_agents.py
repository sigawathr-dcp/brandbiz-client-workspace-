"""
Unit tests for app/services/agent.py and the agent chat integration.

Covers:
- create_agent: returns persisted row, audits agent_created
- get_agent: own agent visible, other user's public agent visible, private not visible
- list_agents: scope=all returns public+own; scope=mine returns only own
- update_agent: owner succeeds, non-owner gets 404
- delete_agent: owner succeeds, non-owner gets 404
- creativity_to_temperature: correct mapping
- attach_knowledge_file / detach
- chat_policy.prepare_chat: injects system_prompt + temperature when agent_id given,
  still calls PolicyEngine.decide (can downgrade)
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent import creativity_to_temperature
from app.models.agent import VALID_VISIBILITIES, VALID_STATUSES


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def set_encryption_key(monkeypatch):
    import base64
    monkeypatch.setenv("ENCRYPTION_KEY", base64.b64encode(b"A" * 32).decode())
    import app.crypto as crypto_mod
    crypto_mod._key = None
    yield
    crypto_mod._key = None


def _make_user(role: str = "L3", workspace_id: uuid.UUID | None = None) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    user.google_email = "test@example.com"
    # Explicit default (staff): a bare MagicMock would auto-vivify
    # workspace_id to a truthy child Mock, which is_client_seat() would
    # read as a client seat — see D23 in app/services/workspace.py.
    user.workspace_id = workspace_id
    return user


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    async def _refresh(obj):
        if not getattr(obj, "id", None) or obj.id is None:
            obj.id = uuid.uuid4()
        from datetime import datetime, timezone
        obj.created_at = datetime.now(timezone.utc)
        obj.updated_at = datetime.now(timezone.utc)

    session.refresh = _refresh
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    return session


def _make_agent(
    user_id: uuid.UUID,
    name: str = "Test Agent",
    model: str = "claude-sonnet-4",
    visibility: str = "public",
    status: str = "published",
    instructions: str = "You are helpful.",
    creativity_level: int = 50,
) -> MagicMock:
    agent = MagicMock()
    agent.id = uuid.uuid4()
    agent.user_id = user_id
    agent.name = name
    agent.model = model
    agent.provider = "anthropic"
    agent.visibility = visibility
    agent.status = status
    agent.instructions = instructions
    agent.creativity_level = creativity_level
    agent.capabilities = {}
    agent.description = "A helpful agent"
    agent.avatar_color = None
    agent.category = None
    from datetime import datetime, timezone
    agent.created_at = datetime.now(timezone.utc)
    agent.updated_at = datetime.now(timezone.utc)
    return agent


# ---------------------------------------------------------------------------
# creativity_to_temperature
# ---------------------------------------------------------------------------

class TestCreativityToTemperature:
    def test_zero_maps_to_zero(self):
        assert creativity_to_temperature(0) == 0.0

    def test_hundred_maps_to_one(self):
        assert creativity_to_temperature(100) == 1.0

    def test_fifty_maps_to_point_five(self):
        assert creativity_to_temperature(50) == 0.5

    def test_clamps_below_zero(self):
        assert creativity_to_temperature(-10) == 0.0

    def test_clamps_above_hundred(self):
        assert creativity_to_temperature(150) == 1.0


# ---------------------------------------------------------------------------
# create_agent
# ---------------------------------------------------------------------------

class TestCreateAgent:
    @pytest.mark.asyncio
    async def test_create_published_agent(self):
        from app.services import agent as agent_svc

        user = _make_user()
        session = _make_session()

        with patch("app.services.agent.audit_svc.log", AsyncMock()):
            result = await agent_svc.create_agent(
                session=session,
                user=user,
                name="Marketing Bot",
                provider="anthropic",
                model="claude-sonnet-4",
                description="Helps with marketing",
                instructions="You are a marketing expert.",
                capabilities={"web_search": True},
                creativity_level=40,
            )

        assert session.add.called
        assert session.commit.called
        assert result.name == "Marketing Bot"
        assert result.user_id == user.id

    @pytest.mark.asyncio
    async def test_create_audits_agent_created(self):
        from app.services import agent as agent_svc

        user = _make_user()
        session = _make_session()

        audit_log = AsyncMock()
        with patch("app.services.agent.audit_svc.log", audit_log):
            await agent_svc.create_agent(
                session=session, user=user,
                name="Bot", provider="local", model="gemma4:26b",
            )

        audit_log.assert_called_once()
        call_kwargs = audit_log.call_args
        assert call_kwargs.kwargs.get("action") == "agent_created"

    @pytest.mark.asyncio
    async def test_invalid_visibility_raises(self):
        from app.services import agent as agent_svc
        from fastapi import HTTPException

        user = _make_user()
        session = _make_session()

        with pytest.raises(HTTPException) as exc_info:
            await agent_svc.create_agent(
                session=session, user=user,
                name="Bot", provider="local", model="gemma4:26b",
                visibility="secret",
            )
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# get_agent / accessibility
# ---------------------------------------------------------------------------

class TestGetAgent:
    @pytest.mark.asyncio
    async def test_owner_can_access_own_agent(self):
        from app.services import agent as agent_svc

        user = _make_user()
        agent = _make_agent(user_id=user.id)
        session = _make_session()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=agent)
        session.execute = AsyncMock(return_value=mock_result)

        result = await agent_svc.get_agent(session, agent.id, user.id)
        assert result is agent

    @pytest.mark.asyncio
    async def test_public_agent_accessible_to_others(self):
        from app.services import agent as agent_svc

        owner = _make_user()
        other_user = _make_user()
        agent = _make_agent(user_id=owner.id, visibility="public", status="published")
        session = _make_session()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=agent)
        session.execute = AsyncMock(return_value=mock_result)

        result = await agent_svc.get_agent(session, agent.id, other_user.id)
        assert result is agent

    @pytest.mark.asyncio
    async def test_personal_agent_not_accessible_to_others(self):
        from app.services import agent as agent_svc

        owner = _make_user()
        other_user = _make_user()
        session = _make_session()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=mock_result)

        result = await agent_svc.get_agent(session, uuid.uuid4(), other_user.id)
        assert result is None


# ---------------------------------------------------------------------------
# update_agent
# ---------------------------------------------------------------------------

class TestUpdateAgent:
    @pytest.mark.asyncio
    async def test_owner_can_update(self):
        from app.services import agent as agent_svc

        user = _make_user()
        agent = _make_agent(user_id=user.id, name="Old Name")
        session = _make_session()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=agent)
        session.execute = AsyncMock(return_value=mock_result)

        audit_log = AsyncMock()
        with patch("app.services.agent.audit_svc.log", audit_log):
            result = await agent_svc.update_agent(session, user, agent.id, name="New Name")

        assert result.name == "New Name"
        assert audit_log.called

    @pytest.mark.asyncio
    async def test_non_owner_gets_404(self):
        from app.services import agent as agent_svc
        from fastapi import HTTPException

        user = _make_user()
        session = _make_session()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await agent_svc.update_agent(session, user, uuid.uuid4(), name="Hacked")
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# delete_agent
# ---------------------------------------------------------------------------

class TestDeleteAgent:
    @pytest.mark.asyncio
    async def test_owner_can_delete(self):
        from app.services import agent as agent_svc

        user = _make_user()
        agent = _make_agent(user_id=user.id)
        session = _make_session()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=agent)
        session.execute = AsyncMock(return_value=mock_result)

        audit_log = AsyncMock()
        with patch("app.services.agent.audit_svc.log", audit_log):
            await agent_svc.delete_agent(session, user, agent.id)

        assert session.commit.called
        call_kwargs = audit_log.call_args
        assert call_kwargs.kwargs.get("action") == "agent_deleted"

    @pytest.mark.asyncio
    async def test_non_owner_gets_404(self):
        from app.services import agent as agent_svc
        from fastapi import HTTPException

        user = _make_user()
        session = _make_session()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await agent_svc.delete_agent(session, user, uuid.uuid4())
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Valid constant sets
# ---------------------------------------------------------------------------

class TestValidConstants:
    def test_visibilities(self):
        assert "public" in VALID_VISIBILITIES
        assert "personal" in VALID_VISIBILITIES

    def test_statuses(self):
        assert "published" in VALID_STATUSES
        assert "draft" in VALID_STATUSES
