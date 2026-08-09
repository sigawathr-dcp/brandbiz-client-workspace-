"""Unit tests for PolicyEngine.decide() — all branches, DB-free.

Strategy: PolicyEngine receives an AsyncMock session. Each helper query
(_get_model, _allowed_external_models, _department_ids) is driven by
session.execute returning sequenced MagicMock results.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.router import LOCAL_MODEL_CODE
from app.models.classification import DataTier
from app.models.user import User
from app.services.policy_engine import DenyReason, PolicyDecision, PolicyEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_user(role: str = "L3") -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.role = role
    return user


def _active_model(code: str = "claude-sonnet-4") -> MagicMock:
    m = MagicMock()
    m.is_active = True
    m.code = code
    return m


def _inactive_model(code: str = "claude-sonnet-4") -> MagicMock:
    m = MagicMock()
    m.is_active = False
    m.code = code
    return m


def _scalar_result(value: object) -> MagicMock:
    """Mimic session.execute(...).scalar_one_or_none() returning value."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _scalar_one_result(value: object) -> MagicMock:
    """Mimic session.execute(...).scalar_one() returning value."""
    r = MagicMock()
    r.scalar_one.return_value = value
    return r


def _scalars_result(values: list) -> MagicMock:
    """Mimic session.execute(...).scalars().all() returning values."""
    r = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = values
    r.scalars.return_value = scalars
    return r


def _make_session(*execute_return_values) -> AsyncMock:
    """Return an AsyncMock session whose execute() returns values in order."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=list(execute_return_values))
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLocalModelAlwaysAllowed:
    async def test_local_tier1_any_role(self):
        session = AsyncMock()
        engine = PolicyEngine(session)
        decision = await engine.decide(
            _mock_user("L1"), LOCAL_MODEL_CODE, DataTier.TIER_1_PUBLIC, 100
        )
        assert decision.allowed is True
        assert decision.model_code == LOCAL_MODEL_CODE
        assert decision.downgrade_to_local is False

    async def test_local_tier2_allowed(self):
        session = AsyncMock()
        decision = await PolicyEngine(session).decide(
            _mock_user("L1"), LOCAL_MODEL_CODE, DataTier.TIER_2_INTERNAL, 100
        )
        assert decision.allowed is True

    async def test_local_tier3_allowed(self):
        session = AsyncMock()
        decision = await PolicyEngine(session).decide(
            _mock_user("L3"), LOCAL_MODEL_CODE, DataTier.TIER_3_CONFIDENTIAL, 100
        )
        assert decision.allowed is True


class TestTier4RequiresL5:
    async def test_local_tier4_low_role_denied(self):
        session = AsyncMock()
        decision = await PolicyEngine(session).decide(
            _mock_user("L3"), LOCAL_MODEL_CODE, DataTier.TIER_4_RESTRICTED, 100
        )
        assert decision.allowed is False
        assert DenyReason.TIER_4_REQUIRES_L5 in decision.reasons

    async def test_local_tier4_l5_allowed(self):
        session = AsyncMock()
        decision = await PolicyEngine(session).decide(
            _mock_user("L5"), LOCAL_MODEL_CODE, DataTier.TIER_4_RESTRICTED, 100
        )
        assert decision.allowed is True

    async def test_local_tier4_admin_allowed(self):
        session = AsyncMock()
        decision = await PolicyEngine(session).decide(
            _mock_user("ADMIN"), LOCAL_MODEL_CODE, DataTier.TIER_4_RESTRICTED, 100
        )
        assert decision.allowed is True

    async def test_external_tier4_low_role_denied(self):
        # _get_model returns an active model, but tier4 + low role → deny
        session = _make_session(_scalar_result(_active_model()))
        decision = await PolicyEngine(session).decide(
            _mock_user("L3"), "claude-sonnet-4", DataTier.TIER_4_RESTRICTED, 100
        )
        assert decision.allowed is False
        assert DenyReason.TIER_4_REQUIRES_L5 in decision.reasons


class TestUnknownModel:
    async def test_unknown_model_denied(self):
        session = _make_session(_scalar_result(None))  # _get_model → None
        decision = await PolicyEngine(session).decide(
            _mock_user(), "nonexistent-model", DataTier.TIER_1_PUBLIC, 100
        )
        assert decision.allowed is False
        assert DenyReason.UNKNOWN_MODEL in decision.reasons


class TestModelInactive:
    async def test_inactive_model_denied(self):
        session = _make_session(_scalar_result(_inactive_model()))
        decision = await PolicyEngine(session).decide(
            _mock_user(), "claude-sonnet-4", DataTier.TIER_1_PUBLIC, 100
        )
        assert decision.allowed is False
        assert DenyReason.MODEL_INACTIVE in decision.reasons


class TestTierBlocksExternal:
    async def test_tier3_external_downgrades_to_local(self):
        # _get_model returns active model, then tier3 triggers downgrade before perm check
        session = _make_session(_scalar_result(_active_model()))
        decision = await PolicyEngine(session).decide(
            _mock_user("L3"), "claude-sonnet-4", DataTier.TIER_3_CONFIDENTIAL, 100
        )
        assert decision.allowed is True
        assert decision.model_code == LOCAL_MODEL_CODE
        assert decision.downgrade_to_local is True
        assert DenyReason.TIER_BLOCKS_EXTERNAL in decision.reasons

    async def test_tier4_l5_external_downgrades_to_local(self):
        session = _make_session(_scalar_result(_active_model()))
        decision = await PolicyEngine(session).decide(
            _mock_user("L5"), "claude-sonnet-4", DataTier.TIER_4_RESTRICTED, 100
        )
        assert decision.allowed is True
        assert decision.model_code == LOCAL_MODEL_CODE
        assert decision.downgrade_to_local is True


class TestRoleNotAllowed:
    async def test_external_model_not_in_allowed_set_downgrades(self):
        # execute calls: _get_model, role_stmt, _department_ids
        session = _make_session(
            _scalar_result(_active_model()),              # _get_model
            _scalars_result([]),                          # role perms → empty
            _scalars_result([]),                          # dept_ids → empty
        )
        decision = await PolicyEngine(session).decide(
            _mock_user("L1"), "claude-sonnet-4", DataTier.TIER_1_PUBLIC, 100
        )
        assert decision.allowed is True
        assert decision.model_code == LOCAL_MODEL_CODE
        assert decision.downgrade_to_local is True
        assert DenyReason.ROLE_NOT_ALLOWED in decision.reasons


def _quota_sequence(limit: int = 500_000, used: int = 0) -> tuple:
    """Three execute() return values consumed by _get_or_create_current_quota:
      1. SELECT QuotaDefault → scalar_one() == limit
      2. INSERT ... ON CONFLICT DO NOTHING → result ignored
      3. SELECT Quota → scalar_one() == Quota(tokens_limit, tokens_used)
    """
    q = MagicMock()
    q.tokens_limit = limit
    q.tokens_used = used
    return (
        _scalar_one_result(limit),  # QuotaDefault.monthly_token_limit
        MagicMock(),                # upsert — return value unused
        _scalar_one_result(q),      # Quota row
    )


class TestHappyPath:
    async def test_allowed_external_model_returns_requested(self):
        # execute calls: _get_model, role_stmt, dept_ids, then 3 for quota
        session = _make_session(
            _scalar_result(_active_model("claude-sonnet-4")),  # _get_model
            _scalars_result(["claude-sonnet-4"]),               # role perms
            _scalars_result([]),                                # dept_ids
            *_quota_sequence(),                                 # quota (under limit)
        )
        decision = await PolicyEngine(session).decide(
            _mock_user("L3"), "claude-sonnet-4", DataTier.TIER_1_PUBLIC, 100
        )
        assert decision.allowed is True
        assert decision.model_code == "claude-sonnet-4"
        assert decision.downgrade_to_local is False


class TestDepartmentAddOn:
    async def test_dept_permitted_model_included_in_allowed_set(self):
        dept_id = 42
        # execute calls: _get_model, role_stmt (empty), _department_ids, dept_stmt, then 3 for quota
        session = _make_session(
            _scalar_result(_active_model("gemini-2.5-flash-image")),  # _get_model
            _scalars_result([]),                                        # role perms → none
            _scalars_result([dept_id]),                                 # dept_ids
            _scalars_result(["gemini-2.5-flash-image"]),               # dept perms
            *_quota_sequence(),                                         # quota (under limit)
        )
        decision = await PolicyEngine(session).decide(
            _mock_user("L2"), "gemini-2.5-flash-image", DataTier.TIER_1_PUBLIC, 100
        )
        assert decision.allowed is True
        assert decision.model_code == "gemini-2.5-flash-image"
        assert decision.downgrade_to_local is False


class TestQuotaExceeded:
    """Rule 4: monthly quota gate (live since Task 2.3)."""

    async def test_quota_exceeded_denies(self):
        # Execute sequence for external model that passes Rules 1-3 then hits Rule 4:
        # _get_model, role_stmt, dept_ids (empty → no dept_stmt), then 3 for quota
        session = _make_session(
            _scalar_result(_active_model("claude-sonnet-4")),  # _get_model
            _scalars_result(["claude-sonnet-4"]),               # role perms
            _scalars_result([]),                                # dept_ids → empty
            *_quota_sequence(limit=1_000, used=1_000),         # remaining==0 < 100
        )
        decision = await PolicyEngine(session).decide(
            _mock_user("L3"), "claude-sonnet-4", DataTier.TIER_1_PUBLIC, 100
        )
        assert decision.allowed is False
        assert DenyReason.QUOTA_EXCEEDED in decision.reasons

    async def test_quota_within_limit_allowed(self):
        session = _make_session(
            _scalar_result(_active_model("claude-sonnet-4")),
            _scalars_result(["claude-sonnet-4"]),
            _scalars_result([]),
            *_quota_sequence(limit=200_000, used=0),
        )
        decision = await PolicyEngine(session).decide(
            _mock_user("L3"), "claude-sonnet-4", DataTier.TIER_1_PUBLIC, 100
        )
        assert decision.allowed is True
        assert decision.model_code == "claude-sonnet-4"
        assert decision.quota_remaining == 200_000
