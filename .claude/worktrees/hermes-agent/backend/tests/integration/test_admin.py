"""
Integration tests for Task 2.7: admin user + permission management.

Key acceptance scenario:
  Create an L4 user with Claude access.
  Demote to L1 via the PATCH /admin/users/{id} endpoint.
  Immediately call PolicyEngine.decide — must return downgrade_to_local
  with reason ROLE_NOT_ALLOWED.  No sleep: the DB write is visible to the
  next session instantly (< 30 s staleness gate satisfied).

Run:
    python -m pytest backend/tests/integration/test_admin.py -v
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.llm.router import LOCAL_MODEL_CODE
from app.models.audit import AuditLog
from app.models.classification import DataTier
from app.models.model_catalog import ModelCatalog
from app.models.permission import RoleModelPermission
from app.models.quota import Quota, QuotaDefault
from app.models.user import User
from app.services.policy_engine import DenyReason, PolicyEngine


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

async def _make_admin(session: AsyncSession) -> User:
    user = User(
        google_email=f"admin-{uuid.uuid4()}@test.local",
        role="ADMIN",
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _make_user(session: AsyncSession, role: str = "L1") -> User:
    user = User(
        google_email=f"user-{uuid.uuid4()}@test.local",
        role=role,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _ensure_model(session: AsyncSession, code: str = "claude-sonnet-4") -> ModelCatalog:
    existing = (await session.execute(
        select(ModelCatalog).where(ModelCatalog.code == code)
    )).scalar_one_or_none()
    if existing:
        return existing
    m = ModelCatalog(
        code=code,
        display_name="Claude Sonnet 4 (test)",
        provider="anthropic",
        is_local=False,
        is_active=True,
    )
    session.add(m)
    await session.commit()
    await session.refresh(m)
    return m


async def _grant_role_permission(
    session: AsyncSession, role: str, model_id: int
) -> None:
    exists = (await session.execute(
        select(RoleModelPermission).where(
            RoleModelPermission.role == role,
            RoleModelPermission.model_id == model_id,
        )
    )).scalar_one_or_none()
    if not exists:
        session.add(RoleModelPermission(role=role, model_id=model_id))
        await session.commit()


async def _ensure_quota_default(session: AsyncSession, role: str) -> None:
    exists = (await session.execute(
        select(QuotaDefault).where(QuotaDefault.role == role)
    )).scalar_one_or_none()
    if not exists:
        session.add(QuotaDefault(role=role, monthly_token_limit=1_000_000))
        await session.commit()


def _make_jwt(user_id: uuid.UUID) -> str:
    secret = os.environ.get("JWT_SECRET", "test-jwt-secret")
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    return jwt.encode({"sub": str(user_id), "exp": exp}, secret, algorithm="HS256")


# ---------------------------------------------------------------------------
# 1. list_users returns the created user
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_users_returns_created_user(db_engine_sync: str) -> None:
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        admin = await _make_admin(s)
        target = await _make_user(s, role="L3")

    from app.main import app
    from app.db import get_db

    async def override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        token = _make_jwt(admin.id)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/admin/users",
                params={"role": "L3"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total"] >= 1
        emails = [u["google_email"] for u in data["items"]]
        assert target.google_email in emails
    finally:
        app.dependency_overrides.clear()

    await engine.dispose()


# ---------------------------------------------------------------------------
# 2. PATCH /admin/users/{id} — role change persists to DB
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_user_role_persists(db_engine_sync: str) -> None:
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        admin = await _make_admin(s)
        target = await _make_user(s, role="L2")

    from app.main import app
    from app.db import get_db

    async def override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        token = _make_jwt(admin.id)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.patch(
                f"/admin/users/{target.id}",
                json={"role": "L3"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["role"] == "L3"
    finally:
        app.dependency_overrides.clear()

    # Verify the DB row was actually changed
    async with factory() as s:
        refreshed = (await s.execute(
            select(User).where(User.id == target.id)
        )).scalar_one()
    assert refreshed.role == "L3"

    await engine.dispose()


# ---------------------------------------------------------------------------
# 3. KEY ACCEPTANCE TEST: demote L4→L1, claude blocked immediately
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_demote_l4_to_l1_blocks_claude_immediately(db_engine_sync: str) -> None:
    """
    Acceptance criterion: demoting a user from L4 to L1 via the admin endpoint
    must cause PolicyEngine.decide() to deny Claude access on the NEXT call —
    no staleness window, because get_current_user reads from DB on every request.
    """
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    # --- Setup ---
    async with factory() as s:
        admin = await _make_admin(s)
        l4_user = await _make_user(s, role="L4")
        claude = await _ensure_model(s, "claude-sonnet-4")
        await _grant_role_permission(s, "L4", claude.id)
        await _ensure_quota_default(s, "L4")
        await _ensure_quota_default(s, "L1")

    # --- Step 1: L4 user can use claude ---
    async with factory() as s:
        fresh = (await s.execute(select(User).where(User.id == l4_user.id))).scalar_one()
        decision_before = await PolicyEngine(s).decide(
            fresh, "claude-sonnet-4", DataTier.TIER_1_PUBLIC, 100
        )
    assert decision_before.allowed is True
    assert decision_before.downgrade_to_local is False
    assert decision_before.model_code == "claude-sonnet-4"

    # --- Step 2: demote via admin HTTP endpoint ---
    from app.main import app
    from app.db import get_db

    async def override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        token = _make_jwt(admin.id)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.patch(
                f"/admin/users/{l4_user.id}",
                json={"role": "L1"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["role"] == "L1"
    finally:
        app.dependency_overrides.clear()

    # --- Step 3: immediately check — no sleep, DB is authoritative ---
    async with factory() as s:
        fresh = (await s.execute(select(User).where(User.id == l4_user.id))).scalar_one()
        assert fresh.role == "L1", "Role must be committed to DB"
        decision_after = await PolicyEngine(s).decide(
            fresh, "claude-sonnet-4", DataTier.TIER_1_PUBLIC, 100
        )

    assert decision_after.downgrade_to_local is True, (
        "L1 user must be downgraded away from Claude"
    )
    assert DenyReason.ROLE_NOT_ALLOWED in decision_after.reasons, (
        f"Expected ROLE_NOT_ALLOWED in {decision_after.reasons}"
    )
    assert decision_after.model_code == LOCAL_MODEL_CODE, (
        "Downgrade must route to local model"
    )

    await engine.dispose()


# ---------------------------------------------------------------------------
# 4. Role permission matrix: PUT replaces atomically
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_put_role_permissions_replaces_atomically(db_engine_sync: str) -> None:
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        admin = await _make_admin(s)
        m1 = await _ensure_model(s, "claude-sonnet-4")
        m2 = await _ensure_model(s, "gpt-4o-mini-test")

    from app.main import app
    from app.db import get_db

    async def override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        token = _make_jwt(admin.id)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Set L5 → [claude-sonnet-4]
            r1 = await client.put(
                "/admin/permissions/role",
                json={"role": "L5", "model_codes": ["claude-sonnet-4"]},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r1.status_code == 200, r1.text
            assert r1.json()["model_codes"] == ["claude-sonnet-4"]

            # Replace L5 → [gpt-4o-mini-test]
            r2 = await client.put(
                "/admin/permissions/role",
                json={"role": "L5", "model_codes": ["gpt-4o-mini-test"]},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r2.status_code == 200, r2.text

            # GET must reflect the replacement
            r3 = await client.get(
                "/admin/permissions/role",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r3.status_code == 200
            matrix = {row["role"]: row["model_codes"] for row in r3.json()}
            assert "claude-sonnet-4" not in matrix.get("L5", [])
            assert "gpt-4o-mini-test" in matrix.get("L5", [])
    finally:
        app.dependency_overrides.clear()

    await engine.dispose()


# ---------------------------------------------------------------------------
# 5. Unknown model code returns 422
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_put_role_permissions_unknown_model_returns_422(
    db_engine_sync: str,
) -> None:
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        admin = await _make_admin(s)

    from app.main import app
    from app.db import get_db

    async def override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        token = _make_jwt(admin.id)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.put(
                "/admin/permissions/role",
                json={"role": "L3", "model_codes": ["does-not-exist"]},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()

    await engine.dispose()


# ---------------------------------------------------------------------------
# 6. Task 2.8 — PII block counter increments on dashboard within cache window
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pii_block_counter_increments(db_engine_sync: str) -> None:
    """
    Acceptance criterion (Task 2.8): inserting 5 audit_log rows with
    action='pii_detected' this month causes GET /admin/metrics?refresh=true
    to return pii_blocks_month >= 5.

    refresh=true bypasses the Redis cache (which may not be available in CI)
    so the fresh SQL is exercised directly.
    """
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        admin = await _make_admin(s)
        for _ in range(5):
            s.add(AuditLog(
                user_id=admin.id,
                action="pii_detected",
                resource_type="message",
            ))
        await s.commit()

    from app.main import app
    from app.db import get_db

    async def override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        token = _make_jwt(admin.id)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/admin/metrics",
                params={"refresh": "true"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["pii_blocks_month"] >= 5, (
            f"Expected >= 5 PII blocks, got {data['pii_blocks_month']}"
        )
        assert "period_start" in data
        assert "active_users" in data
    finally:
        app.dependency_overrides.clear()

    await engine.dispose()


# ---------------------------------------------------------------------------
# 7. Task 2.8 — Audit log endpoint returns entries with filters
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_log_endpoint_filters(db_engine_sync: str) -> None:
    """GET /admin/audit with action filter returns only matching rows."""
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        admin = await _make_admin(s)
        for _ in range(3):
            s.add(AuditLog(user_id=admin.id, action="login"))
        for _ in range(2):
            s.add(AuditLog(user_id=admin.id, action="pii_detected", resource_type="message"))
        await s.commit()

    from app.main import app
    from app.db import get_db

    async def override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        token = _make_jwt(admin.id)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/admin/audit",
                params={"action": "pii_detected", "limit": "50"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] >= 2
        actions = {item["action"] for item in body["items"]}
        assert actions == {"pii_detected"}
    finally:
        app.dependency_overrides.clear()

    await engine.dispose()


# ---------------------------------------------------------------------------
# 8. Task 2.8 — Dashboard metrics endpoint shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dashboard_metrics_shape(db_engine_sync: str) -> None:
    """GET /admin/metrics returns all required fields with correct types."""
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        admin = await _make_admin(s)

    from app.main import app
    from app.db import get_db

    async def override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        token = _make_jwt(admin.id)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/admin/metrics",
                params={"refresh": "true"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        required_fields = {
            "active_users", "total_messages_month", "external_cost_month_usd",
            "pii_blocks_month", "pending_reveals", "period_start",
        }
        assert required_fields <= data.keys()
        assert isinstance(data["active_users"], int)
        assert isinstance(data["external_cost_month_usd"], float)
        assert data["period_start"].endswith("-01")
    finally:
        app.dependency_overrides.clear()

    await engine.dispose()


# ---------------------------------------------------------------------------
# 9. GET /admin/quota-defaults — shape and coverage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quota_defaults_get_shape(db_engine_sync: str) -> None:
    """GET /admin/quota-defaults returns all 7 roles with correct field types."""
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        admin = await _make_admin(s)
        # Seed defaults for all roles so the endpoint has real rows
        for role, limit in [
            ("L1", 50_000), ("L2", 200_000), ("L3", 500_000),
            ("L4", 1_000_000), ("L5", 2_000_000),
            ("L6", 9_223_372_036_854_775_807), ("ADMIN", 9_223_372_036_854_775_807),
        ]:
            existing = (await s.execute(
                select(QuotaDefault).where(QuotaDefault.role == role)
            )).scalar_one_or_none()
            if not existing:
                s.add(QuotaDefault(role=role, monthly_token_limit=limit))
        await s.commit()

    from app.main import app
    from app.db import get_db

    async def override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        token = _make_jwt(admin.id)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/admin/quota-defaults",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200, resp.text
        items = resp.json()
        roles_returned = [i["role"] for i in items]
        assert set(roles_returned) == {"L1", "L2", "L3", "L4", "L5", "L6", "ADMIN"}
        # Verify order: L1 first, ADMIN last
        assert roles_returned[0] == "L1"
        assert roles_returned[-1] == "ADMIN"
        # Check field types on a sample row
        l1 = next(i for i in items if i["role"] == "L1")
        assert isinstance(l1["monthly_token_limit"], int)
        assert isinstance(l1["is_unlimited"], bool)
        assert isinstance(l1["tokens_used_month"], int)
        assert isinstance(l1["user_count"], int)
        assert l1["is_unlimited"] is False
        # L6 and ADMIN should be unlimited
        l6 = next(i for i in items if i["role"] == "L6")
        assert l6["is_unlimited"] is True
    finally:
        app.dependency_overrides.clear()

    await engine.dispose()


# ---------------------------------------------------------------------------
# 10. PUT /admin/quota-defaults — updates DB and emits audit log
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_put_quota_default_updates_and_audits(db_engine_sync: str) -> None:
    """PUT /admin/quota-defaults updates quota_defaults and emits admin_quota_changed."""
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        admin = await _make_admin(s)
        await _ensure_quota_default(s, "L2")

    from app.main import app
    from app.db import get_db

    async def override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        token = _make_jwt(admin.id)
        new_limit = 333_000
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.put(
                "/admin/quota-defaults",
                json={"role": "L2", "monthly_token_limit": new_limit, "is_unlimited": False},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["role"] == "L2"
        assert body["monthly_token_limit"] == new_limit
        assert body["is_unlimited"] is False
    finally:
        app.dependency_overrides.clear()

    # Verify DB row was persisted
    async with factory() as s:
        row = (await s.execute(
            select(QuotaDefault).where(QuotaDefault.role == "L2")
        )).scalar_one()
        assert row.monthly_token_limit == new_limit

        # Verify audit log emitted admin_quota_changed
        audit_row = (await s.execute(
            select(AuditLog)
            .where(
                AuditLog.action == "admin_quota_changed",
                AuditLog.actor_id == admin.id,
            )
            .order_by(AuditLog.id.desc())
            .limit(1)
        )).scalar_one_or_none()
        assert audit_row is not None, "Expected admin_quota_changed audit row"
        assert audit_row.details is not None
        assert audit_row.details["role"] == "L2"
        assert audit_row.details["monthly_token_limit"] == new_limit

    await engine.dispose()


# ---------------------------------------------------------------------------
# 11. PUT /admin/quota-defaults — cascades to current-month quota rows
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_put_quota_default_cascades_current_month(db_engine_sync: str) -> None:
    """PUT cascades the new limit to existing current-month Quota rows."""
    from datetime import date

    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    period = date.today().replace(day=1)

    async with factory() as s:
        admin = await _make_admin(s)
        user = await _make_user(s, role="L3")
        await _ensure_quota_default(s, "L3")
        # Seed a current-month quota row for this user
        s.add(Quota(
            user_id=user.id,
            period_start=period,
            tokens_limit=500_000,
            tokens_used=10_000,
        ))
        await s.commit()

    from app.main import app
    from app.db import get_db

    async def override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        token = _make_jwt(admin.id)
        new_limit = 750_000
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.put(
                "/admin/quota-defaults",
                json={"role": "L3", "monthly_token_limit": new_limit, "is_unlimited": False},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.clear()

    # Verify the existing quota row was updated
    async with factory() as s:
        quota_row = (await s.execute(
            select(Quota).where(Quota.user_id == user.id, Quota.period_start == period)
        )).scalar_one()
        assert quota_row.tokens_limit == new_limit, (
            f"Expected tokens_limit={new_limit}, got {quota_row.tokens_limit}"
        )
        # tokens_used must not be touched
        assert quota_row.tokens_used == 10_000

    await engine.dispose()


# ---------------------------------------------------------------------------
# 12. GET /admin/quota-defaults — tokens_used_month sums per role
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quota_defaults_used_tokens_aggregated(db_engine_sync: str) -> None:
    """tokens_used_month aggregates all quota rows for the role in the current month."""
    from datetime import date

    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    period = date.today().replace(day=1)

    async with factory() as s:
        admin = await _make_admin(s)
        u1 = await _make_user(s, role="L4")
        u2 = await _make_user(s, role="L4")
        await _ensure_quota_default(s, "L4")
        s.add(Quota(user_id=u1.id, period_start=period, tokens_limit=1_000_000, tokens_used=12_000))
        s.add(Quota(user_id=u2.id, period_start=period, tokens_limit=1_000_000, tokens_used=8_000))
        await s.commit()

    from app.main import app
    from app.db import get_db

    async def override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        token = _make_jwt(admin.id)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/admin/quota-defaults",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200, resp.text
        items = resp.json()
        l4 = next(i for i in items if i["role"] == "L4")
        assert l4["tokens_used_month"] >= 20_000, (
            f"Expected >= 20000, got {l4['tokens_used_month']}"
        )
    finally:
        app.dependency_overrides.clear()

    await engine.dispose()


# ---------------------------------------------------------------------------
# 13. PUT /admin/quota-defaults — rejects invalid role and negative limit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_put_quota_default_rejects_bad_input(db_engine_sync: str) -> None:
    """PUT /admin/quota-defaults returns 422 for unknown role or negative limit."""
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        admin = await _make_admin(s)

    from app.main import app
    from app.db import get_db

    async def override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        token = _make_jwt(admin.id)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            bad_role = await client.put(
                "/admin/quota-defaults",
                json={"role": "L99", "monthly_token_limit": 100_000, "is_unlimited": False},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert bad_role.status_code == 422, bad_role.text

            neg_limit = await client.put(
                "/admin/quota-defaults",
                json={"role": "L1", "monthly_token_limit": -1, "is_unlimited": False},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert neg_limit.status_code == 422, neg_limit.text
    finally:
        app.dependency_overrides.clear()

    await engine.dispose()
