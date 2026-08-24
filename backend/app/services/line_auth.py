"""
app/services/line_auth.py

Verification of LINE Login id_tokens — the identity half of the client
entry point (0063). One responsibility: turn an opaque id_token string
into trustworthy claims, or raise. It creates no users, touches no
database, and knows nothing about workspaces; app/services/workspace.py
::provision_line_seat owns that half.

WHY DELEGATE VERIFICATION TO LINE
LINE signs id_tokens with HS256 (channel secret) for some client types and
ES256 (rotating JWKS) for others, and which one you get depends on channel
configuration that can change without a deploy. POSTing to LINE's
/oauth2/v2.1/verify endpoint checks signature, issuer, audience AND expiry
in one call, so none of that lives here. The cost is one outbound HTTPS
round trip per login — a login happens once per client, so this is not a
hot path.

TRUST BOUNDARY
The `sub` returned here is the ONLY field callers may treat as identity.
`name` and `picture` are user-controlled LINE profile strings: they are
display data, they are personal data under PDPA, and they must never be
used to look a seat up. See provision_line_seat, which keys on sub alone.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from fastapi import HTTPException

from app.config import settings

logger = logging.getLogger(__name__)

# A login is interactive — the client is watching a spinner inside the LINE
# app — so fail fast rather than hanging on a slow LINE edge.
_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)

# LINE user ids are "U" + 32 hex chars today. The DB column is VARCHAR(64);
# this bound stops an oversized `sub` from a malformed response reaching an
# INSERT and erroring at the driver instead of here, with a useful message.
_MAX_SUB_LEN = 64


@dataclass(frozen=True)
class LineProfile:
    """Verified claims from a LINE id_token. `sub` is identity; everything
    else is display data the user controls."""

    sub: str
    name: str | None
    picture: str | None


def is_enabled() -> bool:
    """Whether LINE login is configured at all. Checked by the router so an
    unconfigured deploy returns a clean 503 instead of failing inside an
    HTTP call to LINE with an empty client_id."""
    return bool(settings.line_login_channel_id)


async def verify_id_token(id_token: str) -> LineProfile:
    """Verify an id_token against LINE and return its claims.

    Raises 401 for anything that makes the token untrustworthy (bad
    signature, wrong audience, expired) and 502 if LINE itself is
    unreachable — the two are deliberately different: the first is the
    caller's problem, the second is ours, and a client staring at a
    spinner should be told to retry only in the second case.
    """
    if not is_enabled():
        raise HTTPException(503, "LINE login is not configured")
    if not id_token or not id_token.strip():
        raise HTTPException(401, "Missing LINE id_token")

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                settings.line_verify_url,
                data={
                    "id_token": id_token,
                    # LINE checks this against the token's `aud` claim, so a
                    # token minted for someone else's channel is rejected by
                    # LINE rather than trusted by us.
                    "client_id": settings.line_login_channel_id,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except httpx.HTTPError as exc:
        logger.warning("LINE id_token verification unreachable: %s", exc)
        raise HTTPException(502, "Could not reach LINE to verify your login") from exc

    if response.status_code != 200:
        # LINE returns 400 with {error, error_description} for an invalid or
        # expired token. Log the reason, but never echo it to the caller —
        # it distinguishes "expired" from "wrong audience", which is a probe
        # oracle for an unauthenticated endpoint.
        logger.info(
            "LINE id_token rejected (status=%s body=%s)",
            response.status_code,
            response.text[:200],
        )
        raise HTTPException(401, "LINE login could not be verified")

    try:
        claims = response.json()
    except ValueError as exc:
        raise HTTPException(502, "Unexpected response from LINE") from exc

    sub = (claims.get("sub") or "").strip()
    if not sub:
        # A 200 with no sub should be impossible; treat it as a failed
        # verification rather than minting an anonymous seat.
        logger.error("LINE verify returned 200 with no sub: %s", str(claims)[:200])
        raise HTTPException(502, "Unexpected response from LINE")
    if len(sub) > _MAX_SUB_LEN:
        logger.error("LINE verify returned an oversized sub (%d chars)", len(sub))
        raise HTTPException(502, "Unexpected response from LINE")

    name = claims.get("name") or None
    picture = claims.get("picture") or None
    return LineProfile(sub=sub, name=name, picture=picture)
