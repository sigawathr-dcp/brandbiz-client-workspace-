import uuid
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
    if user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def require_consent(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Block access until the user has acknowledged the privacy notice."""
    if user.consent_acknowledged_at is None:
        raise HTTPException(status_code=403, detail="REQUIRES_CONSENT")
    return user
