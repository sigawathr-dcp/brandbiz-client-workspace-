"""
app/services/rate_limit.py

Minimal in-process rate limiter (Phase 5 §7 hardening, D21/D22).

No Redis, no new dependency: this stack has neither Redis nor slowapi
installed today (PLAN.md's own Gotcha notes "No Celery/Redis in demo
mode"), and a single-instance event deployment doesn't need distributed
rate-limit state. A fixed-window counter keyed by client IP, held in
process memory. Two known, accepted limits for this scope:
  - resets on restart — fine for an event kill switch, not a permanent
    security boundary (see PLAN.md Phase 4's still-open "Rate limiting"
    item for the general, cross-cutting version of this).
  - unbounded dict growth over a long-running process — acceptable for a
    multi-hour event; a real production deployment should move this to
    Redis (or add TTL eviction) rather than run this forever.

Applied to the two genuinely guessable-token surfaces this repo now has
(POST /public/redeem, GET /public/plans/{token}) and, more loosely, across
/client/* as defense in depth against one attendee's device hammering the
booth's shared NAT IP.
"""
from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request

_WINDOWS: dict[str, list[float]] = defaultdict(list)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(key_prefix: str, *, limit: int, window_seconds: float):
    """FastAPI dependency factory: `limit` requests per `window_seconds`,
    per client IP, namespaced by `key_prefix` so different endpoints don't
    share a bucket."""

    async def _dep(request: Request) -> None:
        ip = _client_ip(request)
        key = f"{key_prefix}:{ip}"
        now = time.monotonic()
        bucket = _WINDOWS[key]
        cutoff = now - window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.pop(0)
        if len(bucket) >= limit:
            raise HTTPException(status_code=429, detail="Too many requests — please slow down.")
        bucket.append(now)

    return _dep
