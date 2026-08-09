"""
D23 — app/services/quota.py::resolve_monthly_token_limit.

The single source of truth for a user's monthly token ceiling, replacing
three previously-divergent copies of the same precedence logic (quota.py's
own consume(), PolicyEngine._get_or_create_current_quota, and
GET /quota/me — the last of which used to ignore the workspace override
entirely). Precedence: workspaces.monthly_token_limit (client seats, when
set) -> quota_defaults[role].
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.quota import resolve_monthly_token_limit


def _scalar_one_or_none_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _scalar_one_result(value):
    r = MagicMock()
    r.scalar_one.return_value = value
    return r


def _make_user(*, workspace_id: uuid.UUID | None, role: str = "L1") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    user.workspace_id = workspace_id
    return user


class TestResolveMonthlyTokenLimit:
    @pytest.mark.asyncio
    async def test_staff_always_uses_role_default(self):
        user = _make_user(workspace_id=None, role="L3")
        session = AsyncMock()
        # Staff never queries Workspace — only the role-default lookup runs.
        session.execute = AsyncMock(return_value=_scalar_one_result(75_000))

        result = await resolve_monthly_token_limit(session, user)

        assert result == 75_000
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_client_seat_workspace_override_wins(self):
        user = _make_user(workspace_id=uuid.uuid4())
        session = AsyncMock()
        # First call: Workspace.monthly_token_limit lookup, set -> short-circuits.
        session.execute = AsyncMock(return_value=_scalar_one_or_none_result(500_000))

        result = await resolve_monthly_token_limit(session, user)

        assert result == 500_000
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_client_seat_falls_back_to_role_default_when_workspace_limit_is_null(self):
        user = _make_user(workspace_id=uuid.uuid4(), role="L1")
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                _scalar_one_or_none_result(None),  # workspace limit unset
                _scalar_one_result(50_000),         # role default
            ]
        )

        result = await resolve_monthly_token_limit(session, user)

        assert result == 50_000
        assert session.execute.await_count == 2
