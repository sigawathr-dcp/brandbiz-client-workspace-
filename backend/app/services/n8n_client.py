"""
app/services/n8n_client.py

Outbound client for triggering n8n webhooks — Part B of the n8n integration.

The gateway can fire a labelling-run (or any other automation) by POSTing to
an n8n Webhook trigger node.  Configure the n8n side:
  1. Add a "Webhook" node as a parallel trigger (alongside the Gmail Trigger).
  2. Set the HTTP method to POST and note the webhook URL.
  3. Optionally set "Header Auth" to validate X-N8N-Secret.

Gateway config (via .env):
  N8N_WEBHOOK_URL — full webhook URL from n8n (single URL for all triggers)

Returns the n8n webhook response body on success.  Raises RuntimeError if
n8n is unreachable or returns a non-2xx status.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)


async def trigger(
    payload: dict[str, Any] | None = None,
    *,
    webhook_url: str | None = None,
) -> dict[str, Any]:
    """POST a JSON payload to the n8n webhook.

    Args:
        payload: Arbitrary JSON body forwarded to n8n (e.g. {"action": "label_inbox"}).
        webhook_url: Override the configured N8N_WEBHOOK_URL (mainly for tests).

    Returns:
        The parsed JSON response from n8n.

    Raises:
        RuntimeError: N8N_WEBHOOK_URL is not configured, n8n is unreachable,
                      or n8n returns a non-2xx status.
    """
    url = webhook_url or settings.n8n_webhook_url
    if not url:
        raise RuntimeError(
            "N8N_WEBHOOK_URL is not set — configure it in .env to enable Gateway→n8n triggers."
        )

    headers: dict[str, str] = {"Content-Type": "application/json"}

    body = payload or {}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(url, json=body, headers=headers)
    except httpx.ConnectError as exc:
        raise RuntimeError(f"n8n webhook unreachable at {url}: {exc}") from exc
    except httpx.TimeoutException as exc:
        raise RuntimeError(f"n8n webhook timed out at {url}: {exc}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"n8n webhook HTTP error: {exc}") from exc

    if response.status_code >= 300:
        raise RuntimeError(
            f"n8n webhook returned {response.status_code}: {response.text[:200]}"
        )

    try:
        return response.json()
    except Exception:
        return {"raw": response.text}
