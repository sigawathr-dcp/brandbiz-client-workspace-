import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from jose import jwt
from starlette.requests import Request
from starlette.testclient import TestClient

from app.deps import get_current_user, require_admin
from app.models.user import User

JWT_SECRET = "test-secret-for-unit-tests"


def _make_token(sub: str, secret: str = JWT_SECRET, exp_offset_hours: int = 8) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "email": "user@test.com",
        "role": "L1",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=exp_offset_hours)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _make_request(token: str | None = None, cookie: bool = False) -> Request:
    scope = {"type": "http", "headers": [], "method": "GET", "path": "/"}
    if token and not cookie:
        scope["headers"] = [(b"authorization", f"Bearer {token}".encode())]
    request = Request(scope)
    if token and cookie:
        request._cookies = {"access_token": token}
    return request


@pytest.fixture
def mock_user() -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.role = "L1"
    user.is_active = True
    return user


@pytest.fixture
def mock_admin_user() -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.role = "ADMIN"
    user.is_active = True
    return user


@pytest.mark.asyncio
async def test_no_token_raises_401():
    request = _make_request()
    session = AsyncMock()
    with patch("app.deps.settings") as s:
        s.jwt_secret = JWT_SECRET
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request, session)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_invalid_token_raises_401():
    request = _make_request(token="not.a.valid.jwt")
    session = AsyncMock()
    with patch("app.deps.settings") as s:
        s.jwt_secret = JWT_SECRET
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request, session)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_expired_token_raises_401():
    user_id = str(uuid.uuid4())
    token = _make_token(user_id, exp_offset_hours=-1)
    request = _make_request(token=token)
    session = AsyncMock()
    with patch("app.deps.settings") as s:
        s.jwt_secret = JWT_SECRET
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request, session)
    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_valid_bearer_token_returns_user(mock_user):
    user_id = str(mock_user.id)
    token = _make_token(user_id)
    request = _make_request(token=token)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    with patch("app.deps.settings") as s:
        s.jwt_secret = JWT_SECRET
        result = await get_current_user(request, session)

    assert result is mock_user


@pytest.mark.asyncio
async def test_valid_cookie_token_returns_user(mock_user):
    user_id = str(mock_user.id)
    token = _make_token(user_id)
    request = _make_request(token=token, cookie=True)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    with patch("app.deps.settings") as s:
        s.jwt_secret = JWT_SECRET
        result = await get_current_user(request, session)

    assert result is mock_user


@pytest.mark.asyncio
async def test_inactive_user_raises_401(mock_user):
    mock_user.is_active = False
    user_id = str(mock_user.id)
    token = _make_token(user_id)
    request = _make_request(token=token)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    with patch("app.deps.settings") as s:
        s.jwt_secret = JWT_SECRET
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request, session)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_user_not_found_raises_401():
    token = _make_token(str(uuid.uuid4()))
    request = _make_request(token=token)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    with patch("app.deps.settings") as s:
        s.jwt_secret = JWT_SECRET
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request, session)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_require_admin_passes_for_admin(mock_admin_user):
    result = await require_admin(mock_admin_user)
    assert result is mock_admin_user


@pytest.mark.asyncio
async def test_require_admin_raises_403_for_non_admin(mock_user):
    with pytest.raises(HTTPException) as exc:
        await require_admin(mock_user)
    assert exc.value.status_code == 403
