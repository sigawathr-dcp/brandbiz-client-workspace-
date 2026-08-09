"""D21/D22 — pooled workspace token budget (PolicyEngine Rule 5).

Client seats share a per-workspace pooled cap (workspaces.token_budget_limit
/ token_budget_used) on top of their individual monthly quota — the backstop
against N event attendees adding up to an unbounded bill even though each
individual seat's quota looks reasonable. Internal users (workspace_id IS
NULL) never touch this path — see the internal-unaffected assertion below,
which also doubles as the regression guard for the trap noted in
PROGRESS.md: an unconditional new session.execute() call breaking every
test built on a fixed execute() sequence.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from app.models.classification import DataTier
from app.models.user import User
from app.services.policy_engine import DenyReason, PolicyEngine


def _mock_client_user(workspace_id: uuid.UUID, role: str = "L1") -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.role = role
    user.workspace_id = workspace_id
    return user


def _mock_internal_user(role: str = "L3") -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.role = role
    user.workspace_id = None
    return user


def _active_model(code: str = "claude-sonnet-4") -> MagicMock:
    m = MagicMock()
    m.is_active = True
    m.code = code
    return m


def _scalar_or_none(value: object) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _scalar_one(value: object) -> MagicMock:
    r = MagicMock()
    r.scalar_one.return_value = value
    return r


def _scalars(values: list) -> MagicMock:
    r = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = values
    r.scalars.return_value = scalars
    return r


def _make_session(*execute_return_values) -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=list(execute_return_values))
    return session


def _mock_workspace(*, monthly_token_limit=None, budget_limit=None, budget_used=0) -> MagicMock:
    ws = MagicMock()
    ws.monthly_token_limit = monthly_token_limit
    ws.token_budget_limit = budget_limit
    ws.token_budget_used = budget_used
    return ws


def _mock_quota(limit: int, used: int) -> MagicMock:
    q = MagicMock()
    q.tokens_limit = limit
    q.tokens_used = used
    return q


class TestWorkspaceBudgetExceeded:
    async def test_pooled_budget_spent_denies_even_with_quota_headroom(self):
        ws_id = uuid.uuid4()
        # execute() call order for a client seat, external model, role-granted:
        #   1. _get_model                         -> active model
        #   2. role_stmt (_allowed_external_models) -> [model code]
        #   3. _department_ids                    -> []  (no dept_stmt)
        #   4. workspace.monthly_token_limit lookup -> generous per-seat limit
        #   5. quota upsert (ON CONFLICT DO NOTHING) -> unused
        #   6. quota row select                   -> plenty of per-seat headroom
        #   7. workspace budget row select         -> pool exhausted
        session = _make_session(
            _scalar_or_none(_active_model("claude-sonnet-4")),
            _scalars(["claude-sonnet-4"]),
            _scalars([]),
            _scalar_or_none(1_000_000),                                   # per-seat override
            MagicMock(),                                                   # upsert
            _scalar_one(_mock_quota(limit=1_000_000, used=0)),            # plenty of seat quota
            _scalar_or_none(_mock_workspace(budget_limit=1_000, budget_used=1_000)),  # pool spent
        )
        decision = await PolicyEngine(session).decide(
            _mock_client_user(ws_id), "claude-sonnet-4", DataTier.TIER_1_PUBLIC, 100
        )
        assert decision.allowed is False
        assert DenyReason.WORKSPACE_BUDGET_EXCEEDED in decision.reasons

    async def test_pooled_budget_with_headroom_allows(self):
        ws_id = uuid.uuid4()
        session = _make_session(
            _scalar_or_none(_active_model("claude-sonnet-4")),
            _scalars(["claude-sonnet-4"]),
            _scalars([]),
            _scalar_or_none(1_000_000),
            MagicMock(),
            _scalar_one(_mock_quota(limit=1_000_000, used=0)),
            _scalar_or_none(_mock_workspace(budget_limit=1_000_000, budget_used=0)),
        )
        decision = await PolicyEngine(session).decide(
            _mock_client_user(ws_id), "claude-sonnet-4", DataTier.TIER_1_PUBLIC, 100
        )
        assert decision.allowed is True
        assert decision.model_code == "claude-sonnet-4"

    async def test_no_pooled_cap_configured_never_denies(self):
        """token_budget_limit IS NULL — no pooled cap configured for this
        workspace; only the per-seat quota applies (unchanged Rule 4)."""
        ws_id = uuid.uuid4()
        session = _make_session(
            _scalar_or_none(_active_model("claude-sonnet-4")),
            _scalars(["claude-sonnet-4"]),
            _scalars([]),
            _scalar_or_none(1_000_000),
            MagicMock(),
            _scalar_one(_mock_quota(limit=1_000_000, used=0)),
            _scalar_or_none(_mock_workspace(budget_limit=None, budget_used=999_999)),
        )
        decision = await PolicyEngine(session).decide(
            _mock_client_user(ws_id), "claude-sonnet-4", DataTier.TIER_1_PUBLIC, 100
        )
        assert decision.allowed is True


class TestInternalUsersUnaffected:
    async def test_internal_user_never_queries_workspace_budget(self):
        """Internal users must take the exact same execute() call sequence
        as before D21/D22 — no extra query, no behavior change. This is the
        regression guard for the class of bug PROGRESS.md records: an
        unconditional new session.execute() breaking every hand-built
        session mock built on a fixed call sequence."""
        session = _make_session(
            _scalar_or_none(_active_model("claude-sonnet-4")),
            _scalars(["claude-sonnet-4"]),
            _scalars([]),
            _scalar_one(1_000_000),   # QuotaDefault.monthly_token_limit (role path)
            MagicMock(),
            _scalar_one(_mock_quota(limit=1_000_000, used=0)),
        )
        decision = await PolicyEngine(session).decide(
            _mock_internal_user("L3"), "claude-sonnet-4", DataTier.TIER_1_PUBLIC, 100
        )
        assert decision.allowed is True
        assert session.execute.call_count == 6  # no 7th (workspace-budget) call
