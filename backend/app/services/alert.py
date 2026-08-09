"""
app/services/alert.py

Admin-alert service — fires an n8n webhook when a chat message contains
keywords indicating the server is down or an admin should be contacted.

The webhook call is fire-and-forget:
  * Never raises into the calling request.
  * Per-user throttle (30 s) to avoid spamming admin LINE on rapid retries.
  * Disabled entirely when N8N_WEBHOOK_URL is blank.

n8n side setup (required):
  1. In the Webhook node, set HTTP Method = POST.
  2. In the LINE Messaging node, use {{ $json.body.message }} for the text.
  3. For always-on delivery, activate the workflow and point the env var at
     the Production URL (.../webhook/...) not the test URL.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any

from app.config import settings
from app.services import n8n_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword patterns — extend freely; case-insensitive, partial-word match OK.
# ---------------------------------------------------------------------------
_ALERT_PHRASES: list[str] = [
    # English
    r"server\s+(is\s+)?down",
    r"server\s+error",
    r"error\s+in\s+(the\s+)?server",
    r"server\s+not\s+(available|reachable|responding|working)",
    r"contact\s+admin",
    r"please\s+contact\s+admin",
    r"notify\s+admin",
    r"inform\s+admin",
    r"service\s+(is\s+)?unavailable",
    r"system\s+(is\s+)?(down|outage)",
    # Thai
    r"เซิร์ฟเวอร์\s*ล่ม",
    r"เซิร์ฟเวอร์\s*มีปัญหา",
    r"เซิร์ฟเวอร์\s*ขัดข้อง",
    r"ระบบ\s*ล่ม",
    r"ระบบ\s*ขัดข้อง",
    r"ระบบ\s*มีปัญหา",
    r"แจ้ง\s*แอดมิน",
    r"ติดต่อ\s*แอดมิน",
    r"แจ้ง\s*ผู้ดูแล",
]

_PATTERN = re.compile(
    "|".join(f"(?:{p})" for p in _ALERT_PHRASES),
    re.IGNORECASE,
)

# Throttle: minimum seconds between alerts for the same user.
_THROTTLE_SECONDS: float = 30.0
_last_alert: dict[str, float] = {}  # user_email → monotonic timestamp


def matches_alert(text: str) -> bool:
    """Return True if *text* contains any alert keyword phrase."""
    return bool(_PATTERN.search(text))


async def maybe_alert(
    text: str,
    *,
    source: str,
    user_email: str,
    conversation_id: uuid.UUID | None,
) -> None:
    """Fire the admin-alert n8n webhook if *text* matches a keyword pattern.

    Always returns without raising — a webhook failure is logged as a warning
    but must not break the caller's request.

    Args:
        text:            The raw user message content.
        source:          Which endpoint triggered this (e.g. "chat", "n8n").
        user_email:      Authenticated user's email (used as throttle key).
        conversation_id: Optional conversation UUID for traceability.
    """
    if not settings.n8n_webhook_url:
        return  # feature disabled

    if not matches_alert(text):
        return  # no keyword match — fast path, no overhead

    # Per-user throttle — asyncio is single-threaded so plain dict is safe.
    now = time.monotonic()
    last = _last_alert.get(user_email, 0.0)
    if now - last < _THROTTLE_SECONDS:
        logger.debug(
            "alert throttled for %s (%.0fs since last)",
            user_email,
            now - last,
        )
        return

    _last_alert[user_email] = now

    payload: dict[str, Any] = {
        "action": "server_alert",
        "message": text,
        "line_message": "โปรดอ่านไลน์",
        "source": source,
        "triggered_by": user_email,
        "conversation_id": str(conversation_id) if conversation_id else None,
    }

    try:
        await n8n_client.trigger(payload)
        logger.info(
            "admin alert sent to n8n (user=%s source=%s)", user_email, source
        )
    except Exception as exc:  # noqa: BLE001
        # Never propagate — a webhook failure must not break the user's chat.
        logger.warning(
            "admin alert webhook failed (user=%s): %s", user_email, exc
        )
