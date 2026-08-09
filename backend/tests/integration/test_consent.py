"""
Integration tests for Task 2.9 — privacy consent acknowledgement.

Acceptance criteria:
  1. New user (consent_acknowledged_at = NULL) cannot POST /chat — 403 REQUIRES_CONSENT.
  2. POST /auth/acknowledge-consent sets consent_acknowledged_at and writes exactly
     one 'consent_acknowledged' row to audit_log.
  3. Existing user who logged in before this task shipped (NULL consent) is also blocked.
  4. After acknowledgement, GET /auth/me returns requires_consent=False.

Run:
    python -m pytest backend/tests/integration/test_consent.py -v
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

from app.models.audit import AuditLog
from app.models.user import User


def _make_jwt(user_id: uuid.UUID) -> str:
    secret = os.environ.get("JWT_SECRET", "test-jwt-secret")
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    return jwt.encode({"sub": str(user_id), "exp": exp}, secret, algorithm="HS256")


async def _make_user(
    session: AsyncSession,
    *,
    consent_acknowledged_at: datetime | None = None,
) -> User:
    user = User(
        google_email=f"user-{uuid.uuid4()}@test.local",
        role="L1",
        is_active=True,
        consent_acknowledged_at=consent_acknowledged_at,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Test 1: New user (NULL consent) blocked from chat
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_new_user_blocked_from_chat(db_engine_sync: str) -> None:
    """New user with NULL consent_acknowledged_at gets 403 REQUIRES_CONSENT on POST /chat."""
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        user = await _make_user(s, consent_acknowledged_at=None)

    from app.main import app
    from app.db import get_db

    async def override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        token = _make_jwt(user.id)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/chat",
                json={"content": "hello", "conversation_id": None},
                headers={"Cookie": f"access_token={token}"},
            )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "REQUIRES_CONSENT"
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()


# ---------------------------------------------------------------------------
# Test 2: acknowledge-consent writes audit log and clears the flag
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_acknowledge_consent_writes_audit_and_clears_flag(db_engine_sync: str) -> None:
    """POST /auth/acknowledge-consent → requires_consent=False + exactly one audit row."""
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        user = await _make_user(s, consent_acknowledged_at=None)

    from app.main import app
    from app.db import get_db

    async def override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        token = _make_jwt(user.id)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Acknowledge
            ack = await client.post(
                "/auth/acknowledge-consent",
                headers={"Cookie": f"access_token={token}"},
            )
            assert ack.status_code == 200
            assert ack.json()["requires_consent"] is False

            # /auth/me should reflect the change immediately
            me = await client.get("/auth/me", headers={"Cookie": f"access_token={token}"})
            assert me.status_code == 200
            assert me.json()["requires_consent"] is False

        # Check audit_log for exactly one consent_acknowledged row for this user
        async with factory() as s:
            rows = (await s.execute(
                select(AuditLog).where(
                    AuditLog.user_id == user.id,
                    AuditLog.action == "consent_acknowledged",
                )
            )).scalars().all()
        assert len(rows) == 1
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()


# ---------------------------------------------------------------------------
# Test 3: Existing user (logged in before task shipped) also blocked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_existing_user_without_consent_blocked(db_engine_sync: str) -> None:
    """Users who existed before Task 2.9 shipped (NULL consent) are also blocked."""
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    # Simulate a user that was created before consent tracking existed
    async with factory() as s:
        user = await _make_user(s, consent_acknowledged_at=None)

    from app.main import app
    from app.db import get_db

    async def override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        token = _make_jwt(user.id)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/chat",
                json={"content": "hello", "conversation_id": None},
                headers={"Cookie": f"access_token={token}"},
            )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "REQUIRES_CONSENT"
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()
