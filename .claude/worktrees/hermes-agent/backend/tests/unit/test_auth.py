import os
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from jose import jwt

# Provide required env vars before importing app modules
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("ENCRYPTION_KEY", "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdA==")  # 32-byte base64
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-unit-tests-only")

from app.models.user import User  # noqa: E402
from app.routers.auth import TOKEN_TTL_HOURS, LoginRequest, _create_jwt, login  # noqa: E402
from app.services.password import hash_password  # noqa: E402


def _make_user(**kwargs) -> User:
    defaults = {
        "id": uuid.uuid4(),
        "google_email": "alice@company.com",
        "role": "L1",
    }
    defaults.update(kwargs)
    return User(**defaults)


def test_create_jwt_contains_expected_claims():
    user = _make_user()
    secret = os.environ["JWT_SECRET"]
    token = _create_jwt(user)
    payload = jwt.decode(token, secret, algorithms=["HS256"])

    assert payload["sub"] == str(user.id)
    assert payload["email"] == "alice@company.com"
    assert payload["role"] == "L1"


def test_create_jwt_expiry_is_eight_hours():
    user = _make_user()
    token = _create_jwt(user)
    secret = os.environ["JWT_SECRET"]
    payload = jwt.decode(token, secret, algorithms=["HS256"])

    delta = payload["exp"] - payload["iat"]
    assert abs(delta - TOKEN_TTL_HOURS * 3600) < 5  # within 5 seconds


def test_create_jwt_role_preserved():
    for role in ("L1", "L2", "L3", "L4", "L5", "L6", "ADMIN"):
        user = _make_user(role=role)
        token = _create_jwt(user)
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])
        assert payload["role"] == role


def test_create_jwt_unique_per_user():
    u1 = _make_user(google_email="a@company.com")
    u2 = _make_user(google_email="b@company.com")
    assert _create_jwt(u1) != _create_jwt(u2)


def test_create_jwt_tampered_secret_raises():
    user = _make_user()
    token = _create_jwt(user)
    with pytest.raises(Exception):
        jwt.decode(token, "wrong-secret", algorithms=["HS256"])


# ---------------------------------------------------------------------------
# POST /auth/login (mock username/email + password)
# ---------------------------------------------------------------------------

def _make_login_user(**kwargs) -> MagicMock:
    user = MagicMock()
    defaults = {
        "id": uuid.uuid4(),
        "username": "l1.associate",
        "google_email": "l1.associate@company.local",
        "role": "L1",
        "is_active": True,
        "password_hash": hash_password("Passw0rd!"),
        "display_name": "l1.associate",
        "avatar_url": None,
        "consent_acknowledged_at": None,
    }
    defaults.update(kwargs)
    for key, value in defaults.items():
        setattr(user, key, value)
    return user


def _session_returning(user) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_login_succeeds_with_username():
    user = _make_login_user()
    session = _session_returning(user)

    with patch("app.routers.auth.settings.google_oauth_client_id", ""):
        result = await login(
            LoginRequest(identifier="l1.associate", password="Passw0rd!"),
            response=MagicMock(),
            session=session,
        )

    assert result["role"] == "L1"
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_login_succeeds_with_email():
    user = _make_login_user()
    session = _session_returning(user)

    with patch("app.routers.auth.settings.google_oauth_client_id", ""):
        result = await login(
            LoginRequest(identifier="L1.ASSOCIATE@COMPANY.LOCAL", password="Passw0rd!"),
            response=MagicMock(),
            session=session,
        )

    assert result["email"] == "l1.associate@company.local"


@pytest.mark.asyncio
async def test_login_wrong_password_raises_401():
    user = _make_login_user()
    session = _session_returning(user)

    with patch("app.routers.auth.settings.google_oauth_client_id", ""):
        with pytest.raises(HTTPException) as exc_info:
            await login(
                LoginRequest(identifier="l1.associate", password="wrong"),
                response=MagicMock(),
                session=session,
            )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_user_raises_401():
    session = _session_returning(None)

    with patch("app.routers.auth.settings.google_oauth_client_id", ""):
        with pytest.raises(HTTPException) as exc_info:
            await login(
                LoginRequest(identifier="nobody", password="whatever"),
                response=MagicMock(),
                session=session,
            )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_login_inactive_user_raises_401():
    user = _make_login_user(is_active=False)
    session = _session_returning(user)

    with patch("app.routers.auth.settings.google_oauth_client_id", ""):
        with pytest.raises(HTTPException) as exc_info:
            await login(
                LoginRequest(identifier="l1.associate", password="Passw0rd!"),
                response=MagicMock(),
                session=session,
            )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_login_disabled_when_google_oauth_configured():
    session = _session_returning(None)

    with patch("app.routers.auth.settings.google_oauth_client_id", "some-client-id"):
        with pytest.raises(HTTPException) as exc_info:
            await login(
                LoginRequest(identifier="l1.associate", password="Passw0rd!"),
                response=MagicMock(),
                session=session,
            )

    assert exc_info.value.status_code == 403
