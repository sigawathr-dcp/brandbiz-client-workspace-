"""
app/routers/client_public.py

Unauthenticated entry points for Client Workspaces (Phase 5 §2/§6, D21/D22):
  POST /public/line/login    — exchange a verified LINE id_token for a session cookie
  POST /public/redeem        — exchange a raw invite token for a session cookie
  GET  /public/plans/{token} — read-only view of a plan someone shared

/public/line/login is the primary entry point since 0063; /public/redeem is
kept as the break-glass path for when LINE login fails in front of a live
client, not as a second supported flow.

These are the ONLY unauthenticated endpoints besides POST /auth/login. All
three are token surfaces reachable without a session, so all three carry a
rate limit
(app/services/rate_limit.py) — Phase 7 hardening. Everything else
client-facing stays behind require_client_context (Phase 3) or require_admin
(client_admin.py).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.routers.auth import _create_jwt, _set_jwt_cookie, _user_response
from app.services import line_auth
from app.services import plan as plan_svc
from app.services import workspace as workspace_svc
from app.services.rate_limit import check as rate_limit_check
from app.services.rate_limit import rate_limit

router = APIRouter(prefix="/public", tags=["client-workspaces"])

# 10 redemption attempts/minute/IP — generous for a real attendee (one
# redemption, ever) while bounding brute-force token guessing.
_redeem_limit = rate_limit("public_redeem", limit=10, window_seconds=60)
# 30 views/minute/IP — a shared link may get refreshed a few times.
_shared_plan_limit = rate_limit("public_shared_plan", limit=30, window_seconds=60)
# LINE login is IP-limited only loosely, and generously: D23 puts a whole
# booth behind one shared NAT IP, and the LIFF webview adds LINE's own
# egress on top, so a tight per-IP bucket would lock out real clients rather
# than attackers. The meaningful limit is the per-sub one below, applied
# AFTER LINE has verified the token — an unverified caller cannot pick which
# bucket they land in.
_line_login_ip_limit = rate_limit("public_line_login_ip", limit=60, window_seconds=60)


class RedeemRequest(BaseModel):
    token: str


@router.post("/redeem", dependencies=[Depends(_redeem_limit)])
async def redeem(
    body: RedeemRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """A redeemed invite IS the login — there is no separate password step
    for a client seat. Reuses the exact JWT-cookie mechanics auth.py uses
    for password login (_create_jwt/_set_jwt_cookie), so every downstream
    auth check (get_current_user, require_client_context, middleware.ts)
    works unmodified for a client seat.
    """
    seat, workspace = await workspace_svc.redeem_invite(session, raw_token=body.token)

    token = _create_jwt(seat)
    _set_jwt_cookie(response, token)

    return {
        **_user_response(seat),
        "workspace": {"id": str(workspace.id), "name": workspace.name, "slug": workspace.slug},
    }


class LineLoginRequest(BaseModel):
    id_token: str
    # Explicit PDPA consent, ticked on the LIFF page before login fires.
    # redeem_invite pre-set consent_acknowledged_at on the grounds that the
    # invite link had been sent by Brandbiz to a known contact and so stood
    # in for the login-time privacy notice. Self-serve LINE login has no
    # prior contact and nobody sent the client anything, so that reasoning
    # does not carry over and the consent has to be real.
    consent: bool = False


@router.post("/line/login", dependencies=[Depends(_line_login_ip_limit)])
async def line_login(
    body: LineLoginRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """LINE Login IS the login for a client seat — same shape as redeem
    above, same JWT cookie, so every downstream check
    (get_current_user, require_client_context, middleware.ts) is unchanged.

    What differs from an invite is WHERE "one client, one run" lives. An
    invite bound it to a link, which could be forwarded and, once spent,
    locked out the person who closed their tab. Here it is bound to the
    verified LINE identity (users.line_user_id, UNIQUE — migration 0063), a
    returning login resumes the SAME seat, and the single-run rule is
    enforced at POST /client/engagements instead.
    """
    if not line_auth.is_enabled():
        raise HTTPException(503, "LINE login is not available")
    if not body.consent:
        # 403 rather than 400: the request is well-formed, we are declining
        # to create an account without consent. The LIFF page disables its
        # button until the box is ticked, so reaching this is a client that
        # bypassed the UI.
        raise HTTPException(403, "Consent is required to continue")

    profile = await line_auth.verify_id_token(body.id_token)

    # Now that LINE has vouched for the sub, rate limit on it. Keyed per
    # identity, so one person hammering login cannot spend the bucket that
    # the rest of a booth shares through one NAT IP.
    rate_limit_check(f"public_line_login:{profile.sub}", limit=10, window_seconds=60)

    seat, workspace, is_new = await workspace_svc.provision_line_seat(
        session,
        line_user_id=profile.sub,
        display_name=profile.name,
        avatar_url=profile.picture,
        consent_given=body.consent,
    )

    token = _create_jwt(seat)
    _set_jwt_cookie(response, token)

    return {
        **_user_response(seat),
        "workspace": {"id": str(workspace.id), "name": workspace.name, "slug": workspace.slug},
        # Lets the LIFF page greet a first-time client and quietly resume a
        # returning one, without a second call to /client/bootstrap.
        "is_new": is_new,
    }


@router.get("/plans/{token}", dependencies=[Depends(_shared_plan_limit)])
async def get_shared_plan(
    token: str,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Read-only view for a plan's share link (Phase 6) — no chat, no
    profile, just the plan itself. Resolves plans.share_token_hash, which is
    only ever set by the owning seat via POST /client/plans/{id}/share
    (Phase 6) — a plan with no share token is unreachable here regardless of
    its id."""
    plan = await plan_svc.get_plan_by_share_token(session, token)
    version = await plan_svc.get_current_version(session, plan)
    body = plan_svc.decrypt_body(version)
    return {
        "id": str(plan.id),
        "title": version.title,
        "status": plan.status,
        "version": version.version_no,
        "core_idea": body.get("core_idea", ""),
        "analogous_case": body.get("analogous_case", ""),
        "adapted_plan": body.get("adapted_plan", []),
        "budget": await plan_svc.budget_out(session, version),
        "created_at": plan.created_at.isoformat(),
    }
