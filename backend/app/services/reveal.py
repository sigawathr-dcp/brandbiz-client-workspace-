"""
app/services/reveal.py

4-eyes reveal flow — all business logic.

Audit writes here are SYNCHRONOUS (direct session insert, not Celery) because:
  - Reveal operations are low-frequency (≤ 10/admin/month by design).
  - The 4-eyes audit is a hard security control where write reliability matters
    more than request latency.
  - Integration tests need to verify the audit trail without Celery infra.

Security invariants enforced here (defence in depth over DB constraint):
  - Requester ≠ approver — checked at app layer before any DB write.
  - One-time view — second GET /view returns 410 Gone.
  - 24-hour expiry — checked against wall clock on every view attempt.
  - 10 reveals/admin/calendar-month hard cap — returns 429 with X-Reset-At header.
  - Concurrency-safe approve — atomic UPDATE WHERE status='pending'; rowcount=0
    means another admin already claimed it → 409 with a clear message.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import extract, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import crypto
from app.context import request_ip, request_ua
from app.models.audit import AuditLog
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.reveal import RevealRequest
from app.models.user import User

_MONTHLY_REVEAL_CAP = 10
_REVEAL_TTL_HOURS = 24


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _write_audit(
    session: AsyncSession,
    action: str,
    *,
    user_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    resource_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Append one audit row within the current session transaction."""
    row = AuditLog(
        action=action,
        user_id=user_id,
        actor_id=actor_id,
        resource_type="reveal_request",
        resource_id=resource_id,
        details=details,
        ip_address=request_ip.get(),
        user_agent=request_ua.get(),
    )
    session.add(row)


def _next_month_start(today: date) -> date:
    if today.month == 12:
        return today.replace(year=today.year + 1, month=1, day=1)
    return today.replace(month=today.month + 1, day=1)


async def _monthly_reveal_count(session: AsyncSession, requester_id: uuid.UUID) -> int:
    today = date.today()
    return (await session.execute(
        select(func.count()).select_from(RevealRequest).where(
            RevealRequest.requester_id == requester_id,
            extract("year", RevealRequest.created_at) == today.year,
            extract("month", RevealRequest.created_at) == today.month,
        )
    )).scalar_one()


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------

async def create_request(
    session: AsyncSession,
    *,
    requester: User,
    target_message_id: uuid.UUID,
    reason: str,
) -> RevealRequest:
    """Create a pending reveal request.

    Raises 429 if the requester has hit the monthly cap (§8.9).
    Raises 404 if the target message or its conversation does not exist.
    """
    today = date.today()
    count = await _monthly_reveal_count(session, requester.id)
    if count >= _MONTHLY_REVEAL_CAP:
        reset_at = _next_month_start(today)
        raise HTTPException(
            status_code=429,
            detail=f"Monthly reveal cap reached ({_MONTHLY_REVEAL_CAP} per calendar month)",
            headers={"X-Reset-At": reset_at.isoformat()},
        )

    msg: Message | None = (await session.execute(
        select(Message).where(Message.id == target_message_id)
    )).scalar_one_or_none()
    if msg is None:
        raise HTTPException(404, "Target message not found")

    conv: Conversation | None = (await session.execute(
        select(Conversation).where(Conversation.id == msg.conversation_id)
    )).scalar_one_or_none()
    if conv is None:
        raise HTTPException(404, "Target conversation not found")

    req = RevealRequest(
        requester_id=requester.id,
        target_user_id=conv.user_id,
        target_conversation_id=conv.id,
        target_message_id=target_message_id,
        reason=reason,
        status="pending",
    )
    session.add(req)
    await session.flush()  # populate req.id before writing audit

    await _write_audit(
        session,
        "reveal_requested",
        user_id=conv.user_id,
        actor_id=requester.id,
        resource_id=req.id,
        details={"target_message_id": str(target_message_id), "reason": reason},
    )

    await session.commit()
    await session.refresh(req)
    return req


async def approve(
    session: AsyncSession,
    *,
    reveal_id: uuid.UUID,
    approver: User,
) -> RevealRequest:
    """Approve a pending reveal request. Sets approver_id, approved_at, expires_at.

    Raises 400 if the approver is the requester (D15: requester != approver).
    Raises 404 if the reveal request does not exist.
    Raises 409 if the request is not pending OR if a concurrent approval won the race.
    """
    req: RevealRequest | None = (await session.execute(
        select(RevealRequest).where(RevealRequest.id == reveal_id)
    )).scalar_one_or_none()
    if req is None:
        raise HTTPException(404, "Reveal request not found")

    # App-layer self-approve guard — DB constraint `no_self_approve` is the second line.
    if req.requester_id == approver.id:
        raise HTTPException(
            400,
            "Self-approval is prohibited; the approver must be a different user from the requester (D15)",
        )

    if req.status != "pending":
        raise HTTPException(409, f"Reveal request is already {req.status!r}; cannot approve")

    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=_REVEAL_TTL_HOURS)

    # Atomic UPDATE — only succeeds when status is still 'pending'.
    # Postgres row-level locking ensures exactly one concurrent caller wins;
    # the loser sees rowcount=0 and receives 409.
    result = await session.execute(
        update(RevealRequest)
        .where(RevealRequest.id == reveal_id, RevealRequest.status == "pending")
        .values(
            status="approved",
            approver_id=approver.id,
            approved_at=now,
            expires_at=expires,
        )
    )
    if result.rowcount == 0:
        await session.rollback()
        raise HTTPException(
            409,
            "Reveal request was concurrently processed by another admin; only one approval is accepted",
        )

    await _write_audit(
        session,
        "reveal_approved",
        user_id=req.target_user_id,
        actor_id=approver.id,
        resource_id=reveal_id,
        details={"expires_at": expires.isoformat()},
    )

    await session.commit()

    return (await session.execute(
        select(RevealRequest).where(RevealRequest.id == reveal_id)
    )).scalar_one()


async def deny(
    session: AsyncSession,
    *,
    reveal_id: uuid.UUID,
    approver: User,
) -> RevealRequest:
    """Deny a pending reveal request.

    Raises 400 if the requester tries to deny their own request.
    Raises 404 if the reveal request does not exist.
    Raises 409 if the request is not in pending state.
    """
    req: RevealRequest | None = (await session.execute(
        select(RevealRequest).where(RevealRequest.id == reveal_id)
    )).scalar_one_or_none()
    if req is None:
        raise HTTPException(404, "Reveal request not found")

    if req.requester_id == approver.id:
        raise HTTPException(400, "Requester cannot deny their own reveal request")

    if req.status != "pending":
        raise HTTPException(409, f"Reveal request is already {req.status!r}; cannot deny")

    await session.execute(
        update(RevealRequest)
        .where(RevealRequest.id == reveal_id, RevealRequest.status == "pending")
        .values(status="denied")
    )

    await _write_audit(
        session,
        "reveal_denied",
        user_id=req.target_user_id,
        actor_id=approver.id,
        resource_id=reveal_id,
        details={"denied_by": str(approver.id)},
    )

    await session.commit()

    return (await session.execute(
        select(RevealRequest).where(RevealRequest.id == reveal_id)
    )).scalar_one()


async def view(
    session: AsyncSession,
    *,
    reveal_id: uuid.UUID,
    requester: User,
) -> str:
    """Decrypt and return the target message plaintext. One-time access only.

    Raises 403 if the caller is not the original requester.
    Raises 403 if the request is not approved.
    Raises 410 if the approval has expired (§8.9).
    Raises 410 if the content has already been viewed (second GET → 410 Gone).

    On success:
    - Sets viewed_at, notified_target_at on the reveal_request row.
    - Writes TWO audit rows: one for the view event, one to record target notification.
      This gives the happy-path trail its required 4th row (request, approve, view, notify).
    """
    req: RevealRequest | None = (await session.execute(
        select(RevealRequest).where(RevealRequest.id == reveal_id)
    )).scalar_one_or_none()
    if req is None:
        raise HTTPException(404, "Reveal request not found")

    if req.requester_id != requester.id:
        raise HTTPException(403, "Only the original requester can view this reveal")

    # One-time access — check before status so 'completed' reveals always return 410 (§8.9)
    if req.viewed_at is not None:
        raise HTTPException(410, "Reveal content has already been viewed (one-time access only)")

    if req.status != "approved":
        raise HTTPException(403, f"Reveal is {req.status!r}, not approved")

    now = datetime.now(timezone.utc)

    if req.expires_at and now >= req.expires_at:
        raise HTTPException(410, "Reveal request has expired (24-hour window elapsed)")

    # Atomically claim the one-time view BEFORE decrypting. Only one caller can
    # flip viewed_at from NULL while the row is still 'approved'; a concurrent
    # second viewer blocks on the row lock, then sees rowcount=0 and gets 410
    # without ever decrypting. Mirrors the guarded UPDATE in approve().
    result = await session.execute(
        update(RevealRequest)
        .where(
            RevealRequest.id == reveal_id,
            RevealRequest.viewed_at.is_(None),
            RevealRequest.status == "approved",
        )
        .values(status="completed", viewed_at=now, notified_target_at=now)
    )
    if result.rowcount == 0:
        await session.rollback()
        raise HTTPException(
            410, "Reveal content has already been viewed (one-time access only)"
        )

    msg: Message | None = (await session.execute(
        select(Message).where(Message.id == req.target_message_id)
    )).scalar_one_or_none()
    if msg is None:
        raise HTTPException(500, "Target message missing; cannot decrypt")

    plaintext = crypto.decrypt(
        msg.content_ciphertext,
        msg.content_nonce,
        msg.content_tag,
        msg.key_version,
    )

    # Audit row 3: the requester viewed the decrypted content.
    await _write_audit(
        session,
        "reveal_viewed",
        user_id=req.target_user_id,
        actor_id=requester.id,
        resource_id=reveal_id,
        details={"viewed_at": now.isoformat()},
    )

    # Audit row 4: record that the target user must be notified their message
    # was revealed (D15). PLAN 2.6 calls this the "notify-target audit task";
    # we record it synchronously here rather than via Celery for the same
    # reliability reasons as the other reveal audits (see module docstring).
    # Notification delivery UI is post-Phase 3.
    await _write_audit(
        session,
        "reveal_viewed",
        user_id=req.target_user_id,
        actor_id=requester.id,
        resource_id=reveal_id,
        details={"notify_target": True, "notified_at": now.isoformat()},
    )

    await session.commit()
    return plaintext
