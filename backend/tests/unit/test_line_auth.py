"""
Unit tests for app/services/line_auth.py — the verification half of the LINE
Login entry point (migration 0063).

These cover the trust boundary specifically: what the service accepts as an
identity and, more importantly, what it refuses. The HTTP call to LINE is
stubbed; nothing here talks to the network or a database.
"""
from __future__ import annotations

import httpx
import pytest
from fastapi import HTTPException

from app.config import settings
from app.services import line_auth


class _StubResponse:
    def __init__(self, status_code: int, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or str(payload)

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _StubClient:
    """Stands in for httpx.AsyncClient as an async context manager."""

    def __init__(self, response=None, error: Exception | None = None):
        self._response = response
        self._error = error
        self.last_data: dict | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, data=None, headers=None):
        self.last_data = data
        if self._error is not None:
            raise self._error
        return self._response


@pytest.fixture(autouse=True)
def _configure_line(monkeypatch):
    monkeypatch.setattr(settings, "line_login_channel_id", "1234567890", raising=False)
    monkeypatch.setattr(settings, "line_login_channel_secret", "secret", raising=False)


def _patch_client(monkeypatch, client: _StubClient) -> None:
    monkeypatch.setattr(line_auth.httpx, "AsyncClient", lambda **kwargs: client)


@pytest.mark.asyncio
async def test_verify_returns_claims_on_success(monkeypatch):
    client = _StubClient(
        _StubResponse(200, {"sub": "U" + "a" * 32, "name": "สมชาย", "picture": "https://x/y.jpg"})
    )
    _patch_client(monkeypatch, client)

    profile = await line_auth.verify_id_token("tok")

    assert profile.sub == "U" + "a" * 32
    assert profile.name == "สมชาย"
    assert profile.picture == "https://x/y.jpg"


@pytest.mark.asyncio
async def test_verify_sends_channel_id_as_expected_audience(monkeypatch):
    """LINE rejects a token minted for another channel only if we tell it
    which audience to expect — losing this makes any valid LINE token from
    any app a valid login here."""
    client = _StubClient(_StubResponse(200, {"sub": "U" + "b" * 32}))
    _patch_client(monkeypatch, client)

    await line_auth.verify_id_token("tok")

    assert client.last_data["client_id"] == "1234567890"
    assert client.last_data["id_token"] == "tok"


@pytest.mark.asyncio
async def test_rejected_token_is_401_without_leaking_the_reason(monkeypatch):
    """LINE distinguishes expired from wrong-audience in error_description.
    Echoing that back would hand an unauthenticated caller a probe oracle."""
    _patch_client(
        monkeypatch,
        _StubClient(_StubResponse(400, {"error_description": "IdToken expired."}, text="expired")),
    )

    with pytest.raises(HTTPException) as exc:
        await line_auth.verify_id_token("tok")

    assert exc.value.status_code == 401
    assert "expired" not in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_unreachable_line_is_502_not_401(monkeypatch):
    """Our outage must not read to the client as their token being bad —
    502 is the retryable one."""
    _patch_client(monkeypatch, _StubClient(error=httpx.ConnectError("boom")))

    with pytest.raises(HTTPException) as exc:
        await line_auth.verify_id_token("tok")

    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_success_without_sub_is_refused(monkeypatch):
    """A 200 carrying no sub would otherwise mint an anonymous seat keyed on
    the empty string — and every subsequent anonymous login would resolve to
    that same seat."""
    _patch_client(monkeypatch, _StubClient(_StubResponse(200, {"name": "no sub here"})))

    with pytest.raises(HTTPException) as exc:
        await line_auth.verify_id_token("tok")

    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_oversized_sub_is_refused(monkeypatch):
    """users.line_user_id is VARCHAR(64); catching it here gives a real
    message instead of a driver error at INSERT time."""
    _patch_client(monkeypatch, _StubClient(_StubResponse(200, {"sub": "U" * 200})))

    with pytest.raises(HTTPException) as exc:
        await line_auth.verify_id_token("tok")

    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_empty_token_is_401_without_calling_line(monkeypatch):
    client = _StubClient(_StubResponse(200, {"sub": "U" + "c" * 32}))
    _patch_client(monkeypatch, client)

    with pytest.raises(HTTPException) as exc:
        await line_auth.verify_id_token("   ")

    assert exc.value.status_code == 401
    assert client.last_data is None


@pytest.mark.asyncio
async def test_unconfigured_channel_is_503(monkeypatch):
    monkeypatch.setattr(settings, "line_login_channel_id", "", raising=False)

    assert line_auth.is_enabled() is False
    with pytest.raises(HTTPException) as exc:
        await line_auth.verify_id_token("tok")

    assert exc.value.status_code == 503
