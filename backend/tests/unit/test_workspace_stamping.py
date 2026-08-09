"""
D23 — write-path stamping and private-by-default writes for client seats.

Once client seats can reach the internal-app create endpoints
(POST /files, /skills, /agents), everything they create must be stamped
with their own workspace_id AND forced private — every booth attendee
shares one workspace (redeem_invite mints into invite.workspace_id), so
workspace-grained stamping alone would let attendee A read attendee B's
"public"/"org" row within that shared workspace.

Covers:
- create_agent / create_skill stamp workspace_id from the passed user
  (client seat -> set, staff -> None)
- a client seat's create_agent / create_skill is coerced to
  visibility="personal" even when "public" was explicitly requested
- staff behavior is unchanged (visibility passes through as requested)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    async def _refresh(obj):
        if not getattr(obj, "id", None):
            obj.id = uuid.uuid4()
        obj.created_at = datetime.now(timezone.utc)
        obj.updated_at = datetime.now(timezone.utc)

    session.refresh = _refresh
    session.execute = AsyncMock()
    return session


def _make_user(*, workspace_id: uuid.UUID | None, role: str = "L3") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    user.workspace_id = workspace_id
    return user


class TestCreateAgentStamping:
    @pytest.mark.asyncio
    async def test_staff_agent_has_no_workspace_id(self):
        from app.services import agent as agent_svc

        user = _make_user(workspace_id=None)
        session = _make_session()

        with patch("app.services.agent.audit_svc.log", AsyncMock()):
            result = await agent_svc.create_agent(
                session=session, user=user,
                name="Marketing Bot", provider="anthropic", model="claude-sonnet-4",
                visibility="public",
            )

        assert result.workspace_id is None
        assert result.visibility == "public"

    @pytest.mark.asyncio
    async def test_client_seat_agent_is_stamped_and_forced_private(self):
        from app.services import agent as agent_svc

        ws_id = uuid.uuid4()
        user = _make_user(workspace_id=ws_id)
        session = _make_session()

        with patch("app.services.agent.audit_svc.log", AsyncMock()):
            result = await agent_svc.create_agent(
                session=session, user=user,
                name="My Bot", provider="anthropic", model="claude-sonnet-4",
                # explicitly requesting public — must be coerced, not rejected
                visibility="public",
            )

        assert result.workspace_id == ws_id
        assert result.visibility == "personal"


class TestCreateSkillStamping:
    @pytest.mark.asyncio
    async def test_staff_skill_has_no_workspace_id(self):
        from app.services import skill as skill_svc

        user = _make_user(workspace_id=None)
        session = _make_session()
        no_existing = MagicMock()
        no_existing.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=no_existing)

        with patch("app.services.skill.audit_svc.log", AsyncMock()):
            result = await skill_svc.create_skill(
                session=session, user=user,
                name="weekly-report", visibility="public",
            )

        assert result.workspace_id is None
        assert result.visibility == "public"

    @pytest.mark.asyncio
    async def test_client_seat_skill_is_stamped_and_forced_private(self):
        from app.services import skill as skill_svc

        ws_id = uuid.uuid4()
        user = _make_user(workspace_id=ws_id)
        session = _make_session()
        no_existing = MagicMock()
        no_existing.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=no_existing)

        with patch("app.services.skill.audit_svc.log", AsyncMock()):
            result = await skill_svc.create_skill(
                session=session, user=user,
                name="weekly-report",
                # explicitly requesting public — must be coerced, not rejected
                visibility="public",
            )

        assert result.workspace_id == ws_id
        assert result.visibility == "personal"
