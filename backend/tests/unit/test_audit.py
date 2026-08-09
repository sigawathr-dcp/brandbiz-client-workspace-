"""Unit tests for app/services/audit.py (Task 2.4).

All tests mock write_audit_log.apply_async so no Redis or Celery worker is needed.
The autouse _silence_audit_celery fixture from conftest patches apply_async globally;
tests here use their own patches so they can inspect the mock's call_args_list.
"""
from __future__ import annotations

import time
import uuid
from unittest.mock import MagicMock, patch

import pytest

import app.services.audit as audit
from app.context import request_ip, request_ua


@pytest.mark.asyncio
async def test_100_messages_enqueue_200_audit_rows():
    """100 message_sent + 100 message_received calls = exactly 200 apply_async calls."""
    user_id = uuid.uuid4()

    with patch("app.workers.audit_writer.write_audit_log.apply_async") as mock_apply:
        for _ in range(100):
            await audit.log(action="message_sent", user_id=user_id,
                            details={"conversation_id": str(uuid.uuid4())})
            await audit.log(action="message_received", user_id=user_id,
                            details={"conversation_id": str(uuid.uuid4())})

    assert mock_apply.call_count == 200
    payloads = [call.kwargs.get("args", call.args[0] if call.args else [])[0]
                for call in mock_apply.call_args_list]
    actions = [p["action"] for p in payloads]
    assert actions.count("message_sent") == 100
    assert actions.count("message_received") == 100


@pytest.mark.asyncio
async def test_audit_enqueue_overhead_is_minimal():
    """1000 audit.log() calls (mocked broker) complete well under 50ms.

    This is the unit-level proxy for the p50-latency requirement: if the
    enqueue itself is microseconds, it cannot add 5%+ to a ~1s LLM response.
    """
    N = 1000
    with patch("app.workers.audit_writer.write_audit_log.apply_async"):
        t0 = time.perf_counter()
        for _ in range(N):
            await audit.log(action="message_sent", user_id=uuid.uuid4())
        duration = time.perf_counter() - t0

    assert duration < 0.05, f"{N} audit.log() calls took {duration:.3f}s (expected <0.05s)"


@pytest.mark.asyncio
async def test_audit_does_not_raise_when_broker_unreachable():
    """If apply_async raises (broker down), audit.log() swallows the error.

    This is the unit-level proof that chat requests are not blocked by audit
    failures — matching the 'kill worker mid-test → messages still succeed'
    acceptance criterion.
    """
    def _raise(*_, **__):
        raise ConnectionError("broker unavailable")

    with patch("app.workers.audit_writer.write_audit_log.apply_async", side_effect=_raise):
        result = await audit.log(action="message_sent", user_id=uuid.uuid4())

    assert result is None  # must return None, not raise


@pytest.mark.asyncio
async def test_audit_payload_structure():
    """Payload dict has all required fields with correct types."""
    user_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    resource_id = uuid.uuid4()

    with patch("app.workers.audit_writer.write_audit_log.apply_async") as mock_apply:
        await audit.log(
            action="model_blocked",
            user_id=user_id,
            actor_id=actor_id,
            resource_type="message",
            resource_id=resource_id,
            details={"model_requested": "claude-sonnet-4", "reasons": ["no_permission"]},
            ip_address="10.0.0.1",
            user_agent="Mozilla/5.0",
        )

    assert mock_apply.call_count == 1
    payload = mock_apply.call_args.kwargs["args"][0]
    assert payload["action"] == "model_blocked"
    assert payload["user_id"] == str(user_id)
    assert payload["actor_id"] == str(actor_id)
    assert payload["resource_type"] == "message"
    assert payload["resource_id"] == str(resource_id)
    assert payload["details"]["model_requested"] == "claude-sonnet-4"
    assert payload["ip_address"] == "10.0.0.1"
    assert payload["user_agent"] == "Mozilla/5.0"


@pytest.mark.asyncio
async def test_audit_reads_ip_and_ua_from_context_vars():
    """When ip_address/user_agent are not passed explicitly, they come from context vars."""
    token_ip = request_ip.set("192.168.1.42")
    token_ua = request_ua.set("TestBrowser/1.0")
    try:
        with patch("app.workers.audit_writer.write_audit_log.apply_async") as mock_apply:
            await audit.log(action="login", user_id=uuid.uuid4())

        payload = mock_apply.call_args.kwargs["args"][0]
        assert payload["ip_address"] == "192.168.1.42"
        assert payload["user_agent"] == "TestBrowser/1.0"
    finally:
        request_ip.reset(token_ip)
        request_ua.reset(token_ua)


@pytest.mark.asyncio
async def test_audit_explicit_ip_overrides_context_var():
    """Explicit ip_address kwarg wins over the context var."""
    token_ip = request_ip.set("10.0.0.1")
    try:
        with patch("app.workers.audit_writer.write_audit_log.apply_async") as mock_apply:
            await audit.log(action="login", user_id=uuid.uuid4(), ip_address="1.2.3.4")

        payload = mock_apply.call_args.kwargs["args"][0]
        assert payload["ip_address"] == "1.2.3.4"
    finally:
        request_ip.reset(token_ip)


@pytest.mark.asyncio
async def test_audit_none_user_id_serialises_as_none():
    """user_id=None should produce None in the payload, not crash."""
    with patch("app.workers.audit_writer.write_audit_log.apply_async") as mock_apply:
        await audit.log(action="logout", user_id=None)

    payload = mock_apply.call_args.kwargs["args"][0]
    assert payload["user_id"] is None


@pytest.mark.asyncio
async def test_audit_enqueue_uses_audit_queue():
    """apply_async must be called with queue='audit'."""
    with patch("app.workers.audit_writer.write_audit_log.apply_async") as mock_apply:
        await audit.log(action="message_sent", user_id=uuid.uuid4())

    assert mock_apply.call_args.kwargs.get("queue") == "audit"
