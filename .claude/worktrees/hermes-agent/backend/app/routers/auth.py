from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from jose import jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.models.user import User
from app.services import audit as audit_svc
from app.services.password import verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

TOKEN_TTL_HOURS = 8


def _user_response(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.google_email,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "role": user.role,
        "requires_consent": user.consent_acknowledged_at is None,
    }


def _create_jwt(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "email": user.google_email,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=TOKEN_TTL_HOURS)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _set_jwt_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="none" if settings.cookie_secure else "lax",
        max_age=TOKEN_TTL_HOURS * 3600,
        domain=settings.cookie_domain or None,
    )


@router.get("/me")
async def me(user: Annotated[User, Depends(get_current_user)]) -> dict:
    return _user_response(user)


@router.post("/acknowledge-consent")
async def acknowledge_consent(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Record that the user has read and accepted the privacy notice. Idempotent."""
    now = datetime.now(timezone.utc)
    if user.consent_acknowledged_at is None:
        user.consent_acknowledged_at = now
        await session.commit()
        await session.refresh(user)
        await audit_svc.log(
            action="consent_acknowledged",
            user_id=user.id,
            details={"acknowledged_at": now.isoformat()},
        )
    return _user_response(user)


@router.post("/logout")
async def logout(
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    await audit_svc.log(action="logout", user_id=user.id)
    response.delete_cookie("access_token", httponly=True, samesite="lax")
    return {"status": "ok"}


class LoginRequest(BaseModel):
    identifier: str  # username or email
    password: str


@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Mock login: username/email + password against seeded users.

    Only available when GOOGLE_OAUTH_CLIENT_ID is blank. Set a non-blank
    client ID to disable this endpoint and enforce real OAuth. Accounts are
    provisioned via scripts/seed_mock_users.py — there is no self-service
    registration.
    """
    if settings.google_oauth_client_id:
        raise HTTPException(
            status_code=403,
            detail="Password login is disabled when Google OAuth is configured",
        )

    identifier = body.identifier.strip().lower()
    result = await session.execute(
        select(User).where(
            (User.username == identifier) | (User.google_email == identifier)
        )
    )
    user = result.scalar_one_or_none()

    if (
        user is None
        or not user.is_active
        or not user.password_hash
        or not verify_password(body.password, user.password_hash)
    ):
        await audit_svc.log(
            action="login_failed",
            user_id=user.id if user else None,
            details={"identifier": identifier},
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user.last_login_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(user)

    await audit_svc.log(
        action="login",
        user_id=user.id,
        details={"email": user.google_email, "mode": "password"},
    )

    token = _create_jwt(user)
    _set_jwt_cookie(response, token)
    return _user_response(user)
