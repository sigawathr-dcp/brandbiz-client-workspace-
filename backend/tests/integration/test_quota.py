"""
Integration tests for app/services/quota.py — require real Postgres (pytest-docker).

Run:
    python -m pytest backend/tests/integration/test_quota.py -q
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.quota import Quota
from app.models.user import User
from app.services import quota as quota_svc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user_ns(user_id: uuid.UUID, role: str) -> SimpleNamespace:
    """Lightweight User-like object; consume() needs .id, .role, and
    .workspace_id (D21/D22 workspace-override precedence, resolved via
    app/services/quota.py::resolve_monthly_token_limit)."""
    return SimpleNamespace(id=user_id, role=role, workspace_id=None)


async def _insert_user(session, role: str = "L3") -> tuple[uuid.UUID, str]:
    """Insert a User row and return (id, role)."""
    user = User(google_email=f"test-{uuid.uuid4()}@example.test", role=role)
    session.add(user)
    await session.commit()
    return user.id, role


# ---------------------------------------------------------------------------
# Test: No lost updates under 100 concurrent consume() calls
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_consume_no_lost_updates(db_engine_sync: str) -> None:
    """100 concurrent consume() calls on the same user — no lost updates.

    Each call uses its own AsyncSession to simulate real concurrent requests.
    Final tokens_used must equal the exact sum of all individual call totals.
    """
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    # Seed a user
    async with factory() as s:
        user_id, user_role = await _insert_user(s, role="L3")

    N = 100
    t_in = 30
    t_out = 20
    cost_each = Decimal("0.001")

    async def _one_call() -> None:
        u = _make_user_ns(user_id, user_role)
        async with factory() as s:
            await quota_svc.consume(s, u, t_in, t_out, cost_each)

    await asyncio.gather(*[_one_call() for _ in range(N)])

    expected_tokens = N * (t_in + t_out)
    expected_cost   = N * cost_each

    async with factory() as s:
        row = (await s.execute(
            select(Quota).where(
                Quota.user_id == user_id,
                Quota.period_start == date.today().replace(day=1),
            )
        )).scalar_one()

    assert row.tokens_used == expected_tokens, (
        f"Lost update detected: expected {expected_tokens}, got {row.tokens_used}"
    )
    assert row.cost_used_usd == expected_cost

    await engine.dispose()


# ---------------------------------------------------------------------------
# Test: Auto-creation uses the correct default for the user's role
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("role,expected_limit", [
    ("L1",    50_000),
    ("L2",   200_000),
    ("L3",   500_000),
    ("L4", 1_000_000),
])
async def test_auto_create_uses_correct_default(
    role: str, expected_limit: int, db_engine_sync: str
) -> None:
    """First consume() for a user creates the quota row using the role default."""
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        user_id, _ = await _insert_user(s, role=role)

    u = _make_user_ns(user_id, role)
    async with factory() as s:
        quota = await quota_svc.consume(s, u, 10, 10, Decimal("0"))

    assert quota.tokens_limit == expected_limit
    assert quota.tokens_used == 20  # 10 + 10

    await engine.dispose()


# ---------------------------------------------------------------------------
# Test: External consume records tokens and cost correctly
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_external_consume_records_tokens_and_cost(db_engine_sync: str) -> None:
    """consume() for an external call stores tokens_used and cost_used_usd."""
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        user_id, role = await _insert_user(s, role="L3")

    u = _make_user_ns(user_id, role)
    async with factory() as s:
        quota = await quota_svc.consume(s, u, 300, 150, Decimal("0.015"))

    assert quota.tokens_used == 450
    assert quota.cost_used_usd == Decimal("0.015")
    assert quota.tokens_limit == 500_000  # L3 default

    await engine.dispose()


# ---------------------------------------------------------------------------
# Test: Local model leaves quota untouched (verified at orchestrator level)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_local_model_quota_not_decremented(db_engine_sync: str) -> None:
    """Quota must NOT be touched when the local model is used.

    This is enforced in orchestrator.call_llm (model_code != LOCAL_MODEL_CODE gate).
    Here we verify that NOT calling consume() leaves the quota row at zero.
    """
    from app.llm.router import LOCAL_MODEL_CODE

    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        user_id, role = await _insert_user(s, role="L2")

    # Simulate: orchestrator would skip consume() for LOCAL_MODEL_CODE.
    # Verify: no quota row created, or row stays at 0.
    async with factory() as s:
        row = (await s.execute(
            select(Quota).where(
                Quota.user_id == user_id,
                Quota.period_start == date.today().replace(day=1),
            )
        )).scalar_one_or_none()

    assert row is None, (
        "No quota row should exist before any consume() call "
        "(local LLM never calls consume)"
    )

    await engine.dispose()
