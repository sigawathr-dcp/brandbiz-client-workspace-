"""
app/services/retention.py

D14 (PLAN.md Decisions Log) — messages.content_* is retained for 30 days;
metadata (role, model_used, tokens, cost, timestamps) is kept indefinitely.
Invoked by backend/scripts/purge_expired_messages.py, meant to run once a
day via an external scheduler (cron / Windows Task Scheduler) — this repo
has no running Celery worker despite PLAN.md's aspirational tree (see
backend/scripts/eval_case_match_run.py for the same script-not-worker
pattern), so a standalone script is the honest fit rather than an
in-process asyncio loop that would double-run under multiple app workers.

This purges content only, never rows: a Plan or a lead references its
originating conversation_id, and other parts of the app (chat history
replay, the 4-eyes reveal audit trail) still need the Message row to exist.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.services import audit as audit_svc

_logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 30


async def purge_expired_messages(
    session: AsyncSession, *, retention_days: int = DEFAULT_RETENTION_DAYS
) -> int:
    """Null out content_ciphertext/content_nonce/content_tag for every
    message older than `retention_days` that hasn't been purged yet.
    Returns the number of rows purged. One audit_log row is written for the
    whole run (not per message) — the count is what a reviewer needs, not
    a per-message trail that would itself contain nothing sensitive but
    would dwarf the rest of the audit log."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    now = datetime.now(timezone.utc)

    result = await session.execute(
        update(Message)
        .where(
            and_(
                Message.created_at < cutoff,
                Message.content_ciphertext.is_not(None),
            )
        )
        .values(
            content_ciphertext=None,
            content_nonce=None,
            content_tag=None,
            content_purged_at=now,
        )
    )
    await session.commit()
    purged_count = result.rowcount or 0

    if purged_count > 0:
        await audit_svc.log(
            action="messages_purged",
            user_id=None,
            resource_type="message",
            resource_id=None,
            details={"count": purged_count, "retention_days": retention_days, "cutoff": cutoff.isoformat()},
        )
        _logger.info("retention: purged content for %d message(s) older than %s", purged_count, cutoff.isoformat())
    else:
        _logger.info("retention: nothing to purge (cutoff %s)", cutoff.isoformat())

    return purged_count


async def count_pending_purge(session: AsyncSession, *, retention_days: int = DEFAULT_RETENTION_DAYS) -> int:
    """How many messages are currently past the cutoff and still hold
    content — used by the script's dry-run mode."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    result = await session.execute(
        select(func.count())
        .select_from(Message)
        .where(and_(Message.created_at < cutoff, Message.content_ciphertext.is_not(None)))
    )
    return result.scalar_one()
