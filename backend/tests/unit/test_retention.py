"""Unit tests for D14 message-content retention (PLAN.md Decisions Log).

Same mocking style as test_client_bootstrap_replay.py — session.execute is
a stand-in returning a canned result, no real DB.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import retention


@pytest.mark.asyncio
async def test_purge_expired_messages_logs_audit_with_count(_silence_audit_celery):
    session = AsyncMock()
    exec_result = MagicMock()
    exec_result.rowcount = 3
    session.execute = AsyncMock(return_value=exec_result)

    purged = await retention.purge_expired_messages(session, retention_days=30)

    assert purged == 3
    session.commit.assert_awaited_once()
    _silence_audit_celery.assert_awaited_once()
    kwargs = _silence_audit_celery.call_args.kwargs
    assert kwargs["action"] == "messages_purged"
    assert kwargs["details"]["count"] == 3
    assert kwargs["details"]["retention_days"] == 30


@pytest.mark.asyncio
async def test_purge_expired_messages_skips_audit_when_nothing_purged(_silence_audit_celery):
    session = AsyncMock()
    exec_result = MagicMock()
    exec_result.rowcount = 0
    session.execute = AsyncMock(return_value=exec_result)

    purged = await retention.purge_expired_messages(session, retention_days=30)

    assert purged == 0
    _silence_audit_celery.assert_not_awaited()


@pytest.mark.asyncio
async def test_count_pending_purge_returns_scalar():
    session = AsyncMock()
    exec_result = MagicMock()
    exec_result.scalar_one.return_value = 5
    session.execute = AsyncMock(return_value=exec_result)

    count = await retention.count_pending_purge(session, retention_days=30)

    assert count == 5
