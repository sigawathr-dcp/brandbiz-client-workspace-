"""
Integration tests for the 4-eyes reveal flow (Task 2.6).

Requires real Postgres (pytest-docker). Run with:
    python -m pytest backend/tests/integration/test_reveal.py -v

All tests use unique UUIDs so they don't interfere with each other even
though the service commits (the db_session rollback-after-test only catches
uncommitted work).

Scenarios covered:
  1. Happy path: A requests, B approves, A views → plaintext returned, 4 audit rows
  2. Self-approve: A requests, A tries to approve → 400
  3. Expired: approve, set expires_at to past, try to view → 410
  4. Already viewed: view twice → second returns 410
  5. Rate limit: 11th reveal request from same admin in month → 429
  6. Concurrency: two admins approve simultaneously → only one wins (409)
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app import crypto
from app.models.audit import AuditLog
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.reveal import RevealRequest
from app.models.user import User
from app.services import reveal as reveal_svc


# ---------------------------------------------------------------------------
# Test data factories
# ---------------------------------------------------------------------------

async def _make_admin(session: AsyncSession, email: str | None = None) -> User:
    user = User(
        google_email=email or f"admin-{uuid.uuid4()}@test.local",
        role="ADMIN",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _make_user(session: AsyncSession) -> User:
    user = User(
        google_email=f"user-{uuid.uuid4()}@test.local",
        role="L1",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _make_message(session: AsyncSession, owner: User, content: str = "secret payload") -> Message:
    """Create a conversation + encrypted message owned by `owner`."""
    conv = Conversation(user_id=owner.id, title="Test conversation")
    session.add(conv)
    await session.flush()

    ct, nonce, tag, kv = crypto.encrypt(content)
    msg = Message(
        conversation_id=conv.id,
        role="user",
        content_ciphertext=ct,
        content_nonce=nonce,
        content_tag=tag,
        key_version=kv,
    )
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    return msg


async def _audit_count(session: AsyncSession, reveal_id: uuid.UUID) -> int:
    """Count audit rows linked to a specific reveal_request id."""
    return (await session.execute(
        select(AuditLog).where(AuditLog.resource_id == reveal_id)
    )).scalars().all().__len__()


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_happy_path_audit_trail(db_engine_sync: str) -> None:
    """A requests, B approves, A views → plaintext correct, 4 audit rows."""
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        admin_a = await _make_admin(s)
        admin_b = await _make_admin(s)
        target = await _make_user(s)
        msg = await _make_message(s, target, content="top-secret information")

    # Step 1: A requests
    async with factory() as s:
        req = await reveal_svc.create_request(
            s,
            requester=admin_a,
            target_message_id=msg.id,
            reason="Compliance audit Q2",
        )
    reveal_id = req.id
    assert req.status == "pending"

    # Step 2: B approves
    async with factory() as s:
        req = await reveal_svc.approve(s, reveal_id=reveal_id, approver=admin_b)
    assert req.status == "approved"
    assert req.approver_id == admin_b.id
    assert req.expires_at is not None

    # Step 3: A views
    async with factory() as s:
        plaintext = await reveal_svc.view(s, reveal_id=reveal_id, requester=admin_a)
    assert plaintext == "top-secret information"

    # Verify reveal is marked as viewed
    async with factory() as s:
        refreshed = (await s.execute(
            select(RevealRequest).where(RevealRequest.id == reveal_id)
        )).scalar_one()
    assert refreshed.viewed_at is not None
    assert refreshed.notified_target_at is not None

    # Verify 4 audit rows: reveal_requested, reveal_approved, reveal_viewed (x2)
    async with factory() as s:
        count = await _audit_count(s, reveal_id)
    assert count == 4, f"Expected 4 audit rows, got {count}"

    # Verify the action types
    async with factory() as s:
        rows = (await s.execute(
            select(AuditLog).where(AuditLog.resource_id == reveal_id)
            .order_by(AuditLog.id.asc())
        )).scalars().all()
    actions = [r.action for r in rows]
    assert "reveal_requested" in actions
    assert "reveal_approved" in actions
    assert actions.count("reveal_viewed") == 2

    await engine.dispose()


# ---------------------------------------------------------------------------
# 2. Self-approve returns 400
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_self_approve_rejected(db_engine_sync: str) -> None:
    """App layer must reject self-approval with HTTP 400 before touching the DB."""
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        admin_a = await _make_admin(s)
        target = await _make_user(s)
        msg = await _make_message(s, target)

    async with factory() as s:
        req = await reveal_svc.create_request(
            s, requester=admin_a, target_message_id=msg.id, reason="audit"
        )
    reveal_id = req.id

    # Admin A tries to approve their own request
    with pytest.raises(HTTPException) as exc_info:
        async with factory() as s:
            await reveal_svc.approve(s, reveal_id=reveal_id, approver=admin_a)

    assert exc_info.value.status_code == 400
    assert "self-approval" in exc_info.value.detail.lower()

    # Status must still be pending
    async with factory() as s:
        refreshed = (await s.execute(
            select(RevealRequest).where(RevealRequest.id == reveal_id)
        )).scalar_one()
    assert refreshed.status == "pending"

    await engine.dispose()


# ---------------------------------------------------------------------------
# 3. Expired reveal returns 410
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_expired_reveal_returns_410(db_engine_sync: str) -> None:
    """After the 24-hour window elapses, GET /view must return 410 Gone."""
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        admin_a = await _make_admin(s)
        admin_b = await _make_admin(s)
        target = await _make_user(s)
        msg = await _make_message(s, target)

    async with factory() as s:
        req = await reveal_svc.create_request(
            s, requester=admin_a, target_message_id=msg.id, reason="audit"
        )
    async with factory() as s:
        req = await reveal_svc.approve(s, reveal_id=req.id, approver=admin_b)

    # Fast-forward: directly set expires_at to the past
    async with factory() as s:
        await s.execute(
            update(RevealRequest)
            .where(RevealRequest.id == req.id)
            .values(expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
        )
        await s.commit()

    with pytest.raises(HTTPException) as exc_info:
        async with factory() as s:
            await reveal_svc.view(s, reveal_id=req.id, requester=admin_a)

    assert exc_info.value.status_code == 410
    assert "expired" in exc_info.value.detail.lower()

    await engine.dispose()


# ---------------------------------------------------------------------------
# 4. Already-viewed returns 410 on second attempt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_second_view_returns_410(db_engine_sync: str) -> None:
    """Second GET /view on an already-viewed reveal returns 410 Gone."""
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        admin_a = await _make_admin(s)
        admin_b = await _make_admin(s)
        target = await _make_user(s)
        msg = await _make_message(s, target, content="once only")

    async with factory() as s:
        req = await reveal_svc.create_request(
            s, requester=admin_a, target_message_id=msg.id, reason="audit"
        )
    async with factory() as s:
        req = await reveal_svc.approve(s, reveal_id=req.id, approver=admin_b)

    # First view — must succeed
    async with factory() as s:
        plaintext = await reveal_svc.view(s, reveal_id=req.id, requester=admin_a)
    assert plaintext == "once only"

    # Second view — must return 410
    with pytest.raises(HTTPException) as exc_info:
        async with factory() as s:
            await reveal_svc.view(s, reveal_id=req.id, requester=admin_a)

    assert exc_info.value.status_code == 410
    assert "already been viewed" in exc_info.value.detail.lower()

    await engine.dispose()


# ---------------------------------------------------------------------------
# 5. Rate limit: 11th reveal request returns 429
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rate_limit_429_on_11th_request(db_engine_sync: str) -> None:
    """11th reveal request from the same admin in the same calendar month → 429."""
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        admin_a = await _make_admin(s)
        target = await _make_user(s)

    # Create 10 distinct messages so we have distinct targets for each request
    message_ids: list[uuid.UUID] = []
    for _ in range(11):
        async with factory() as s:
            m = await _make_message(s, target, content="filler")
            message_ids.append(m.id)

    # Create 10 reveal requests (all should succeed)
    for mid in message_ids[:10]:
        async with factory() as s:
            await reveal_svc.create_request(
                s, requester=admin_a, target_message_id=mid, reason="bulk audit"
            )

    # 11th must fail with 429
    with pytest.raises(HTTPException) as exc_info:
        async with factory() as s:
            await reveal_svc.create_request(
                s, requester=admin_a, target_message_id=message_ids[10], reason="one too many"
            )

    err = exc_info.value
    assert err.status_code == 429
    assert "X-Reset-At" in err.headers
    # Reset-at is the first of next month — must be parseable as a date
    reset_date = err.headers["X-Reset-At"]
    assert reset_date.endswith("-01"), f"Expected first-of-month, got {reset_date!r}"

    await engine.dispose()


# ---------------------------------------------------------------------------
# 5b. Concurrency: two simultaneous views — exactly one decrypts, other gets 410
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_view_only_one_succeeds(db_engine_sync: str) -> None:
    """Two concurrent GET /view on an approved reveal: one returns plaintext, one 410."""
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        admin_a = await _make_admin(s)
        admin_b = await _make_admin(s)
        target = await _make_user(s)
        msg = await _make_message(s, target, content="strictly once")

    async with factory() as s:
        req = await reveal_svc.create_request(
            s, requester=admin_a, target_message_id=msg.id, reason="race test"
        )
    async with factory() as s:
        req = await reveal_svc.approve(s, reveal_id=req.id, approver=admin_b)
    reveal_id = req.id

    results: list[str | HTTPException] = []

    async def _try_view() -> None:
        async with factory() as s:
            try:
                results.append(await reveal_svc.view(s, reveal_id=reveal_id, requester=admin_a))
            except HTTPException as exc:
                results.append(exc)

    await asyncio.gather(_try_view(), _try_view())

    successes = [r for r in results if isinstance(r, str)]
    failures = [r for r in results if isinstance(r, HTTPException)]

    assert len(successes) == 1, f"Expected exactly 1 decrypt, got {len(successes)}"
    assert successes[0] == "strictly once"
    assert len(failures) == 1, f"Expected exactly 1 failure, got {len(failures)}"
    assert failures[0].status_code == 410

    # Exactly one view audit pair was written (view + notify), never two pairs.
    async with factory() as s:
        rows = (await s.execute(
            select(AuditLog).where(AuditLog.resource_id == reveal_id)
        )).scalars().all()
    assert [r.action for r in rows].count("reveal_viewed") == 2

    await engine.dispose()


# ---------------------------------------------------------------------------
# 6. Concurrency: two admins approve simultaneously — only one wins
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_approve_only_one_wins(db_engine_sync: str) -> None:
    """Two admins race to approve the same request; exactly one wins and the other gets 409."""
    engine = create_async_engine(db_engine_sync, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as s:
        admin_a = await _make_admin(s)
        admin_b = await _make_admin(s)
        admin_c = await _make_admin(s)
        target = await _make_user(s)
        msg = await _make_message(s, target)

    async with factory() as s:
        req = await reveal_svc.create_request(
            s, requester=admin_a, target_message_id=msg.id, reason="concurrent test"
        )
    reveal_id = req.id

    results: list[RevealRequest | HTTPException] = []

    async def _try_approve(approver: User) -> None:
        async with factory() as s:
            try:
                r = await reveal_svc.approve(s, reveal_id=reveal_id, approver=approver)
                results.append(r)
            except HTTPException as exc:
                results.append(exc)

    # Fire both approvals concurrently
    await asyncio.gather(_try_approve(admin_b), _try_approve(admin_c))

    successes = [r for r in results if isinstance(r, RevealRequest)]
    failures = [r for r in results if isinstance(r, HTTPException)]

    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
    assert len(failures) == 1, f"Expected exactly 1 failure, got {len(failures)}"
    assert failures[0].status_code == 409, (
        f"Expected 409 for the losing racer, got {failures[0].status_code}"
    )

    # DB must reflect exactly one approval
    async with factory() as s:
        final = (await s.execute(
            select(RevealRequest).where(RevealRequest.id == reveal_id)
        )).scalar_one()
    assert final.status == "approved"
    assert final.approver_id in {admin_b.id, admin_c.id}

    await engine.dispose()
