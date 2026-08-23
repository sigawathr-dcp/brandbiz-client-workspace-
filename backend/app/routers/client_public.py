"""
app/routers/client_public.py

Unauthenticated entry points for Client Workspaces (Phase 5 §2/§6, D21/D22):
  POST /public/redeem       — exchange a raw invite token for a session cookie
  GET  /public/plans/{token} — read-only view of a plan someone shared

These are the ONLY unauthenticated endpoints besides POST /auth/login. Both
are guessable-token surfaces, so both carry a per-IP rate limit
(app/services/rate_limit.py) — Phase 7 hardening. Everything else
client-facing stays behind require_client_context (Phase 3) or require_admin
(client_admin.py).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.routers.auth import _create_jwt, _set_jwt_cookie, _user_response
from app.services import plan as plan_svc
from app.services import workspace as workspace_svc
from app.services.rate_limit import rate_limit

router = APIRouter(prefix="/public", tags=["client-workspaces"])

# 10 redemption attempts/minute/IP — generous for a real attendee (one
# redemption, ever) while bounding brute-force token guessing.
_redeem_limit = rate_limit("public_redeem", limit=10, window_seconds=60)
# 30 views/minute/IP — a shared link may get refreshed a few times.
_shared_plan_limit = rate_limit("public_shared_plan", limit=30, window_seconds=60)


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
