"""D21/D22, amended by D23 — require_internal / require_staff /
require_staff_principal route-lockout dependencies.

require_internal is applied at include_router() level in main.py for the
internal-app routers (chat, conversations, agents, skills, studio, tasks,
files, image) — a client-workspace seat browsing to any of those paths
must 403 unless settings.client_internal_access_enabled is on (D23).

require_staff / require_staff_principal are the hard, never-flag-aware
carve-outs applied to hermes and automations respectively — ops/machine
surfaces that stay staff-only even with the D23 flag on.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

import app.deps as deps_module
from app.deps import require_internal, require_staff, require_staff_principal
from app.models.user import User


def _make_user(*, workspace_id: uuid.UUID | None, consent: bool = True) -> User:
    from datetime import datetime, timezone

    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.role = "L1"
    user.is_active = True
    user.workspace_id = workspace_id
    user.consent_acknowledged_at = datetime.now(timezone.utc) if consent else None
    return user


@pytest.fixture
def flag_off(monkeypatch):
    monkeypatch.setattr(deps_module.settings, "client_internal_access_enabled", False)


@pytest.fixture
def flag_on(monkeypatch):
    monkeypatch.setattr(deps_module.settings, "client_internal_access_enabled", True)


class TestRequireInternalFlagOff:
    @pytest.mark.asyncio
    async def test_internal_user_passes(self, flag_off):
        user = _make_user(workspace_id=None)
        result = await require_internal(user)
        assert result is user

    @pytest.mark.asyncio
    async def test_client_seat_raises_403(self, flag_off):
        user = _make_user(workspace_id=uuid.uuid4())
        with pytest.raises(HTTPException) as exc:
            await require_internal(user)
        assert exc.value.status_code == 403


class TestRequireInternalFlagOn:
    @pytest.mark.asyncio
    async def test_internal_user_still_passes(self, flag_on):
        user = _make_user(workspace_id=None)
        result = await require_internal(user)
        assert result is user

    @pytest.mark.asyncio
    async def test_client_seat_now_passes(self, flag_on):
        """The D23 behavior change: with the flag on, a client seat is
        admitted to the internal-app routers instead of 403ing."""
        user = _make_user(workspace_id=uuid.uuid4())
        result = await require_internal(user)
        assert result is user


class TestRequireStaff:
    """The hard carve-out gate — must reject a client seat regardless of
    the D23 flag, since require_staff never reads it. This is the guard
    against someone later "simplifying" require_staff back into a thin
    wrapper around require_internal."""

    @pytest.mark.asyncio
    async def test_staff_passes(self):
        user = _make_user(workspace_id=None)
        result = await require_staff(user)
        assert result is user

    @pytest.mark.asyncio
    async def test_client_seat_raises_403_even_with_flag_on(self, flag_on):
        user = _make_user(workspace_id=uuid.uuid4())
        with pytest.raises(HTTPException) as exc:
            await require_staff(user)
        assert exc.value.status_code == 403


class TestRequireStaffPrincipal:
    """Same invariant as require_staff, but exercised through the
    get_principal-based signature used for automations (fixes n8n's gw_…
    key path, which require_internal's JWT-only chain used to 401)."""

    @pytest.mark.asyncio
    async def test_service_account_passes(self):
        user = _make_user(workspace_id=None)
        result = await require_staff_principal(user)
        assert result is user

    @pytest.mark.asyncio
    async def test_client_seat_raises_403_even_with_flag_on(self, flag_on):
        user = _make_user(workspace_id=uuid.uuid4())
        with pytest.raises(HTTPException) as exc:
            await require_staff_principal(user)
        assert exc.value.status_code == 403


class TestRequireConsentBlocksUnacknowledgedSeat:
    @pytest.mark.asyncio
    async def test_require_consent_blocks_before_require_client_context_runs(self):
        """require_client_context's FastAPI signature is
        Depends(require_consent) -> require_client_context's own workspace
        resolution. This test exercises require_consent itself — the piece
        that actually blocks a not-yet-consented client seat when a real
        request is routed through both dependencies in sequence."""
        from app.deps import require_consent

        user = _make_user(workspace_id=uuid.uuid4(), consent=False)
        with pytest.raises(HTTPException) as exc:
            await require_consent(user)
        assert exc.value.status_code == 403
        assert exc.value.detail == "REQUIRES_CONSENT"
