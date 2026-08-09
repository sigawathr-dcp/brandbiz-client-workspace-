"""
tests/unit/test_alert.py

Unit tests for app.services.alert — keyword detection and webhook firing.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.alert import matches_alert, maybe_alert, _last_alert


# ---------------------------------------------------------------------------
# matches_alert — pure function, no I/O
# ---------------------------------------------------------------------------

MATCH_CASES = [
    # English positives
    "the server is down",
    "server is down",
    "server down",
    "server error occurred",
    "error in the server",
    "error in server",
    "server not available",
    "server not responding",
    "please contact admin",
    "contact admin asap",
    "notify admin immediately",
    "system is down",
    "service is unavailable",
    # Thai positives
    "เซิร์ฟเวอร์ล่ม",
    "เซิร์ฟเวอร์ มีปัญหา",
    "ระบบล่ม",
    "ระบบขัดข้อง",
    "แจ้งแอดมิน",
    "ติดต่อแอดมิน",
    # Mixed / sentence
    "Hi, the server is down can you help?",
    "ช่วยด้วย เซิร์ฟเวอร์ล่ม",
    # Case variations
    "Server Is Down",
    "SERVER ERROR",
    "Contact Admin",
]

NON_MATCH_CASES = [
    "hello world",
    "how are you",
    "what is the weather today",
    "I need help with my document",
    "สวัสดี",
    "ขอบคุณมาก",
    "can you summarise this email",
    "",
    "   ",
    "download",   # should not match "down" in the middle of a word...
    # NOTE: "download" technically won't match because pattern is r"server\s+(is\s+)?down"
    # but let's be explicit about the cases we do NOT want to alert on.
]


@pytest.mark.parametrize("text", MATCH_CASES)
def test_matches_alert_positives(text: str) -> None:
    assert matches_alert(text), f"Expected match for: {repr(text)}"


@pytest.mark.parametrize("text", NON_MATCH_CASES)
def test_matches_alert_negatives(text: str) -> None:
    assert not matches_alert(text), f"Expected no match for: {repr(text)}"


# ---------------------------------------------------------------------------
# maybe_alert — async, uses n8n_client.trigger
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_throttle():
    """Clear the per-user throttle dict before each test."""
    _last_alert.clear()
    yield
    _last_alert.clear()


@pytest.fixture
def mock_trigger():
    with patch(
        "app.services.alert.n8n_client.trigger",
        new_callable=AsyncMock,
        return_value={"ok": True},
    ) as m:
        yield m


@pytest.fixture
def alert_url(monkeypatch):
    """Enable the alert feature by setting a URL in settings."""
    monkeypatch.setattr(
        "app.services.alert.settings",
        type("S", (), {
            "n8n_webhook_url": "https://n8n.test/webhook/alert",
        })(),
    )


@pytest.mark.asyncio
async def test_maybe_alert_fires_on_match(mock_trigger, alert_url) -> None:
    """maybe_alert should call n8n_client.trigger when a keyword is found."""
    cid = uuid.uuid4()
    await maybe_alert(
        "the server is down",
        source="chat",
        user_email="user@example.com",
        conversation_id=cid,
    )
    mock_trigger.assert_awaited_once()
    call_kwargs = mock_trigger.call_args
    payload = call_kwargs.args[0]
    assert payload["action"] == "server_alert"
    assert payload["triggered_by"] == "user@example.com"
    assert payload["source"] == "chat"
    assert payload["conversation_id"] == str(cid)
    assert "server is down" in payload["message"]


@pytest.mark.asyncio
async def test_maybe_alert_no_fire_on_no_match(mock_trigger, alert_url) -> None:
    """maybe_alert should not call trigger when no keyword matches."""
    await maybe_alert(
        "hello, how are you today?",
        source="chat",
        user_email="user@example.com",
        conversation_id=None,
    )
    mock_trigger.assert_not_awaited()


@pytest.mark.asyncio
async def test_maybe_alert_no_fire_when_url_blank(mock_trigger) -> None:
    """maybe_alert should silently return when N8N_WEBHOOK_URL is blank."""
    # No alert_url fixture — settings.n8n_webhook_url defaults to ""
    await maybe_alert(
        "the server is down",
        source="chat",
        user_email="user@example.com",
        conversation_id=None,
    )
    mock_trigger.assert_not_awaited()


@pytest.mark.asyncio
async def test_maybe_alert_throttle(mock_trigger, alert_url) -> None:
    """Rapid repeated alerts from the same user are throttled to one call."""
    await maybe_alert(
        "server is down",
        source="chat",
        user_email="user@example.com",
        conversation_id=None,
    )
    await maybe_alert(
        "server is down again",
        source="chat",
        user_email="user@example.com",
        conversation_id=None,
    )
    # Only the first call should have fired; the second is throttled.
    mock_trigger.assert_awaited_once()


@pytest.mark.asyncio
async def test_maybe_alert_different_users_not_throttled(mock_trigger, alert_url) -> None:
    """Throttle is per-user — different emails each get their own call."""
    await maybe_alert(
        "server is down",
        source="chat",
        user_email="alice@example.com",
        conversation_id=None,
    )
    await maybe_alert(
        "server is down",
        source="chat",
        user_email="bob@example.com",
        conversation_id=None,
    )
    assert mock_trigger.await_count == 2


@pytest.mark.asyncio
async def test_maybe_alert_swallows_trigger_error(mock_trigger, alert_url) -> None:
    """A webhook failure must not propagate — maybe_alert never raises."""
    mock_trigger.side_effect = RuntimeError("n8n unreachable")
    # Should complete without raising.
    await maybe_alert(
        "the server is down",
        source="chat",
        user_email="user@example.com",
        conversation_id=None,
    )
