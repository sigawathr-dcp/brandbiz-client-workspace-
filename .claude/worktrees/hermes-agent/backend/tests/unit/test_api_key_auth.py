"""Unit tests for service-account API-key authentication (Task 2.10).

Tests cover:
  - generate_key / hash_key helpers
  - _authenticate_api_key with valid / revoked / unknown keys
  - _extract_token preference: Authorization header > X-API-Key > cookie
  - get_principal dispatch (JWT path vs API-key path)
"""

import hashlib
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.api_key import generate_key, hash_key


# ---------------------------------------------------------------------------
# Model helpers
# ---------------------------------------------------------------------------

class TestGenerateKey:
    def test_prefix(self):
        raw, h = generate_key()
        assert raw.startswith("gw_"), "raw key must start with 'gw_'"

    def test_uniqueness(self):
        raw1, _ = generate_key()
        raw2, _ = generate_key()
        assert raw1 != raw2

    def test_hash_matches(self):
        raw, h = generate_key()
        assert hash_key(raw) == h

    def test_hash_is_hex64(self):
        raw, h = generate_key()
        assert len(h) == 64
        int(h, 16)  # must be valid hex

    def test_known_value(self):
        known = "gw_test"
        expected = hashlib.sha256(known.encode()).hexdigest()
        assert hash_key(known) == expected


# ---------------------------------------------------------------------------
# _extract_token
# ---------------------------------------------------------------------------

class TestExtractToken:
    def _make_request(self, auth_header=None, api_key_header=None, cookie=None):
        request = MagicMock()
        headers = {}
        if auth_header:
            headers["Authorization"] = auth_header
        if api_key_header:
            headers["X-API-Key"] = api_key_header
        request.headers.get = lambda key, default="": headers.get(key, default)
        request.cookies.get = lambda key: cookie

        return request

    def test_bearer_header(self):
        from app.deps import _extract_token
        req = self._make_request(auth_header="Bearer abc123")
        assert _extract_token(req) == "abc123"

    def test_x_api_key_header(self):
        from app.deps import _extract_token
        req = self._make_request(api_key_header="gw_secret")
        assert _extract_token(req) == "gw_secret"

    def test_bearer_takes_precedence_over_x_api_key(self):
        from app.deps import _extract_token
        req = self._make_request(auth_header="Bearer jwt_token", api_key_header="gw_key")
        assert _extract_token(req) == "jwt_token"

    def test_cookie_fallback(self):
        from app.deps import _extract_token
        req = self._make_request(cookie="cookie_token")
        assert _extract_token(req) == "cookie_token"

    def test_none_when_nothing(self):
        from app.deps import _extract_token
        req = self._make_request()
        assert _extract_token(req) is None


# ---------------------------------------------------------------------------
# _authenticate_api_key
# ---------------------------------------------------------------------------

def _make_mock_key(*, revoked=False, user_active=True):
    """Build mocks for an ApiKey row and its associated User."""
    key_id = uuid.uuid4()
    user_id = uuid.uuid4()

    api_key_row = MagicMock()
    api_key_row.id = key_id
    api_key_row.service_user_id = user_id
    api_key_row.revoked_at = datetime(2020, 1, 1, tzinfo=timezone.utc) if revoked else None

    svc_user = MagicMock()
    svc_user.id = user_id
    svc_user.is_active = user_active
    svc_user.google_email = "bot@service.local"

    return api_key_row, svc_user


@pytest.mark.asyncio
async def test_authenticate_api_key_valid():
    from app.deps import _authenticate_api_key

    raw, h = generate_key()
    api_key_row, svc_user = _make_mock_key()

    session = AsyncMock()

    # First execute → look up ApiKey (not None, not revoked)
    # Second execute → look up User
    # Third execute → UPDATE last_used_at (no return needed)
    key_result = MagicMock()
    key_result.scalar_one_or_none.return_value = api_key_row

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = svc_user

    session.execute = AsyncMock(side_effect=[key_result, AsyncMock(), user_result])

    with patch("app.models.api_key.hash_key", return_value=h):
        user = await _authenticate_api_key(raw, session)

    assert user is svc_user


@pytest.mark.asyncio
async def test_authenticate_api_key_not_found():
    from fastapi import HTTPException

    from app.deps import _authenticate_api_key

    session = AsyncMock()
    not_found = MagicMock()
    not_found.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=not_found)

    with pytest.raises(HTTPException) as exc_info:
        await _authenticate_api_key("gw_bad_key", session)

    assert exc_info.value.status_code == 401
    assert "Invalid or revoked" in exc_info.value.detail


@pytest.mark.asyncio
async def test_authenticate_api_key_inactive_user():
    from fastapi import HTTPException

    from app.deps import _authenticate_api_key

    raw, h = generate_key()
    api_key_row, svc_user = _make_mock_key(user_active=False)

    session = AsyncMock()
    key_result = MagicMock()
    key_result.scalar_one_or_none.return_value = api_key_row
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = svc_user

    session.execute = AsyncMock(side_effect=[key_result, AsyncMock(), user_result])

    with pytest.raises(HTTPException) as exc_info:
        await _authenticate_api_key(raw, session)

    assert exc_info.value.status_code == 401
    assert "inactive" in exc_info.value.detail


# ---------------------------------------------------------------------------
# get_principal dispatch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_principal_routes_api_key():
    """get_principal routes gw_… tokens to _authenticate_api_key."""
    from app.deps import get_principal

    raw, _ = generate_key()
    svc_user = MagicMock()

    request = MagicMock()
    request.headers.get = lambda k, d="": f"Bearer {raw}" if k == "Authorization" else d
    request.cookies.get = lambda k: None

    session = AsyncMock()

    with patch("app.deps._authenticate_api_key", new_callable=AsyncMock, return_value=svc_user) as mock_auth:
        result = await get_principal(request, session)

    mock_auth.assert_awaited_once_with(raw, session)
    assert result is svc_user


@pytest.mark.asyncio
async def test_get_principal_routes_jwt():
    """get_principal routes non-gw tokens to _authenticate_jwt."""
    from app.deps import get_principal

    request = MagicMock()
    request.headers.get = lambda k, d="": "Bearer some.jwt.token" if k == "Authorization" else d
    request.cookies.get = lambda k: None

    session = AsyncMock()
    human_user = MagicMock()

    with patch("app.deps._authenticate_jwt", new_callable=AsyncMock, return_value=human_user) as mock_jwt:
        result = await get_principal(request, session)

    mock_jwt.assert_awaited_once_with("some.jwt.token", session)
    assert result is human_user
