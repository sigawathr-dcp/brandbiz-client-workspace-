import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from jose import ExpiredSignatureError, JWTError, jwt
from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db as get_db  # noqa: F401 — re-export for router imports
from app.models.user import User

_API_KEY_PREFIX = "gw_"


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    # X-API-Key header as alternative for service accounts
    api_key_header = request.headers.get("X-API-Key", "")
    if api_key_header:
        return api_key_header
    return request.cookies.get("access_token")


# ---------------------------------------------------------------------------
# Internal helpers (not FastAPI dependencies themselves)
# ---------------------------------------------------------------------------

async def _authenticate_jwt(token: str, session: AsyncSession) -> User:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid token claims")

    try:
        user_id = uuid.UUID(sub)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token subject")

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user


async def _authenticate_api_key(token: str, session: AsyncSession) -> User:
    """Look up a gw_… API key, update last_used_at, and return the service User."""
    from app.models.api_key import ApiKey, hash_key  # lazy import — avoids circular at module level

    key_hash = hash_key(token)

    result = await session.execute(
        select(ApiKey).where(
            ApiKey.key_hash == key_hash,
            ApiKey.revoked_at.is_(None),
        )
    )
    api_key_row = result.scalar_one_or_none()
    if api_key_row is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")

    # Best-effort last_used_at — stays in the same transaction as the request
    await session.execute(
        sa_update(ApiKey)
        .where(ApiKey.id == api_key_row.id)
        .values(last_used_at=datetime.now(timezone.utc))
    )

    result = await session.execute(
        select(User).where(User.id == api_key_row.service_user_id)
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Service account not found or inactive")

    return user


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Authenticate via JWT only (human users). Unchanged from original."""
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return await _authenticate_jwt(token, session)


async def get_api_principal(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Authenticate via service-account API key (gw_… prefix) only."""
    token = _extract_token(request)
    if not token or not token.startswith(_API_KEY_PREFIX):
        raise HTTPException(status_code=401, detail="API key required (Bearer gw_… or X-API-Key header)")

    return await _authenticate_api_key(token, session)


async def get_principal(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Accept either a human JWT or a service-account API key (gw_… prefix).

    Used by the OpenAI-compat passthrough endpoint so both humans and n8n
    service accounts can call it with the same dependency.
    """
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if token.startswith(_API_KEY_PREFIX):
        return await _authenticate_api_key(token, session)

    return await _authenticate_jwt(token, session)


async def require_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    # workspace_id is not None guards against a client-workspace seat ever
    # holding role=ADMIN (D23) — PATCH /admin/users/{id} resolves its target
    # by id alone and would otherwise happily promote a seat. Cannot affect
    # a real admin: every staff row has workspace_id IS NULL.
    if user.role != "ADMIN" or user.workspace_id is not None:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def require_consent(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Block access until the user has acknowledged the privacy notice."""
    if user.consent_acknowledged_at is None:
        raise HTTPException(status_code=403, detail="REQUIRES_CONSENT")
    return user


async def require_staff(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Hard staff-only gate — NOT affected by CLIENT_INTERNAL_ACCESS_ENABLED
    (D23). Reserved for ops/machine surfaces that stay off-limits to client
    seats even when D23 opens the rest of the internal app: hermes (host
    telemetry + job logs, unscoped by user) and automations (outbound n8n
    side effects). Internal staff have users.workspace_id IS NULL —
    unchanged since before Client Workspaces existed.
    """
    if user.workspace_id is not None:
        raise HTTPException(status_code=403, detail="Internal access required")
    return user


async def require_staff_principal(
    user: Annotated[User, Depends(get_principal)],
) -> User:
    """Same check as require_staff, but chains off get_principal so gw_…
    service-account keys pass (fixes /automations, which was silently
    unreachable over HTTP: main.py used to gate it with require_internal —
    JWT-only — while its handlers authenticate with get_principal, so an
    n8n call bearing a gw_… key failed JWT decode before reaching the
    handler). Service accounts have workspace_id IS NULL, same as staff.
    """
    if user.workspace_id is not None:
        raise HTTPException(status_code=403, detail="Internal access required")
    return user


async def require_internal(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Gate for the internal-app routers (D21/D22, amended by D23).

    Internal staff (users.workspace_id IS NULL) always pass. Client-
    workspace seats pass only when settings.client_internal_access_enabled
    is on — a single reversible switch, default off in code — otherwise
    they get the original D21/D22 403. Applied at include_router() level in
    main.py for chat/conversations/agents/skills/studio/tasks/files/image,
    so individual route handlers need no changes. hermes and automations
    are carved out onto require_staff / require_staff_principal instead:
    D23 opens product features, not ops/machine surfaces.
    """
    if settings.client_internal_access_enabled:
        return user
    return await require_staff(user)


@dataclass
class ClientContext:
    """(user, effective workspace) pair for /client/* routes — see
    require_client_context. workspace_id is NEVER written back onto
    `user.workspace_id`; it's carried alongside so require_internal and
    everything else that reads the real column elsewhere in the app stays
    correct for the request's lifetime."""

    user: User
    workspace_id: uuid.UUID
    is_preview: bool


async def require_client_context(
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ClientContext:
    """Resolve which workspace a /client/* request runs against.

    Real client seats (workspace_id set at invite redemption, see
    app/services/workspace.py::redeem_invite) use their own workspace,
    exactly as require_client always did.

    Internal staff (workspace_id IS NULL) are routed into "preview mode":
    the single seeded demo workspace, so anyone who logs in normally can
    click through the real client funnel before it goes live to outside
    attendees — without ever becoming a seat and without touching
    users.workspace_id on their own row. Because that column stays NULL,
    quota/PolicyEngine (which key off user.workspace_id, not this context)
    bill preview traffic against the staff member's own internal role
    quota, never the event's pooled workspace budget.
    """
    if user.workspace_id is not None:
        return ClientContext(user=user, workspace_id=user.workspace_id, is_preview=False)

    from app.services import workspace as workspace_svc  # lazy: avoid import-order coupling

    workspace = await workspace_svc.get_preview_workspace(session)
    if workspace is None:
        raise HTTPException(
            status_code=404,
            detail="No demo workspace is set up yet — run scripts/seed_client_demo.py first",
        )
    return ClientContext(user=user, workspace_id=workspace.id, is_preview=True)
