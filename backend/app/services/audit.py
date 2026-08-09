"""
app/services/audit.py

Synchronous (inline) audit logger — inserts directly into audit_log.

§7.3 contract:
- audit_log is append-only; no UPDATE or DELETE ever touches it
- writes are synchronous but wrapped in try/except so they never fail
  a user request — the session_factory creates its own connection
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from app.context import request_ip, request_ua
from app.db import session_factory
from app.models.audit import AuditLog

logger = logging.getLogger(__name__)


async def log(
    *,
    action: str,
    user_id: uuid.UUID | None,
    details: dict[str, Any] | None = None,
    actor_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Insert one audit row. Never raises — DB failures are logged and swallowed."""
    try:
        async with session_factory() as session:
            row = AuditLog(
                action=action,
                user_id=user_id,
                actor_id=actor_id,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
                ip_address=ip_address if ip_address is not None else request_ip.get(),
                user_agent=user_agent if user_agent is not None else request_ua.get(),
            )
            session.add(row)
            await session.commit()
    except Exception:
        logger.warning(
            "audit insert failed action=%s user_id=%s", action, user_id, exc_info=True
        )
