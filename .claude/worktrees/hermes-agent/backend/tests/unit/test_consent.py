"""Unit tests for Task 2.9 — privacy consent acknowledgement."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.deps import require_consent


# ---------------------------------------------------------------------------
# require_consent dependency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_require_consent_blocks_user_without_ack():
    """require_consent raises 403 REQUIRES_CONSENT when consent_acknowledged_at is None."""
    user = MagicMock()
    user.consent_acknowledged_at = None

    with pytest.raises(HTTPException) as exc_info:
        await require_consent(user)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "REQUIRES_CONSENT"


@pytest.mark.asyncio
async def test_require_consent_passes_user_with_ack():
    """require_consent returns the user when consent_acknowledged_at is set."""
    user = MagicMock()
    user.consent_acknowledged_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    result = await require_consent(user)

    assert result is user


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_me_requires_consent_true_for_new_user():
    """GET /auth/me returns requires_consent=True when consent not yet given."""
    from app.routers.auth import me

    user = MagicMock()
    user.id = uuid.uuid4()
    user.google_email = "new@company.com"
    user.display_name = "New User"
    user.avatar_url = None
    user.role = "L1"
    user.consent_acknowledged_at = None

    result = await me(user=user)

    assert result["requires_consent"] is True


@pytest.mark.asyncio
async def test_me_requires_consent_false_for_returning_user():
    """GET /auth/me returns requires_consent=False when consent already given."""
    from app.routers.auth import me

    user = MagicMock()
    user.id = uuid.uuid4()
    user.google_email = "old@company.com"
    user.display_name = "Old User"
    user.avatar_url = None
    user.role = "L1"
    user.consent_acknowledged_at = datetime(2025, 6, 1, tzinfo=timezone.utc)

    result = await me(user=user)

    assert result["requires_consent"] is False


# ---------------------------------------------------------------------------
# POST /auth/acknowledge-consent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_acknowledge_consent_sets_timestamp():
    """POST /auth/acknowledge-consent sets consent_acknowledged_at and returns requires_consent=False."""
    from app.routers.auth import acknowledge_consent

    user = MagicMock()
    user.id = uuid.uuid4()
    user.google_email = "test@company.com"
    user.display_name = "Test"
    user.avatar_url = None
    user.role = "L1"
    user.consent_acknowledged_at = None

    session = AsyncMock()

    result = await acknowledge_consent(user=user, session=session)

    assert user.consent_acknowledged_at is not None
    session.commit.assert_called_once()
    assert result["requires_consent"] is False


@pytest.mark.asyncio
async def test_acknowledge_consent_enqueues_audit(
    _silence_audit_celery,  # autouse fixture from conftest
):
    """POST /auth/acknowledge-consent enqueues exactly one consent_acknowledged audit event."""
    from app.routers.auth import acknowledge_consent

    user = MagicMock()
    user.id = uuid.uuid4()
    user.google_email = "test@company.com"
    user.display_name = "Test"
    user.avatar_url = None
    user.role = "L1"
    user.consent_acknowledged_at = None

    session = AsyncMock()

    await acknowledge_consent(user=user, session=session)

    # The autouse fixture captures apply_async calls
    calls = _silence_audit_celery.call_args_list
    assert len(calls) == 1
    payload = calls[0].kwargs.get("args", calls[0].args[0] if calls[0].args else None)
    if isinstance(payload, list):
        payload = payload[0]
    assert payload["action"] == "consent_acknowledged"


@pytest.mark.asyncio
async def test_acknowledge_consent_idempotent():
    """Calling acknowledge-consent twice does not change the timestamp or double-audit."""
    from app.routers.auth import acknowledge_consent

    already = datetime(2026, 1, 1, tzinfo=timezone.utc)
    user = MagicMock()
    user.id = uuid.uuid4()
    user.google_email = "already@company.com"
    user.display_name = "Already"
    user.avatar_url = None
    user.role = "L1"
    user.consent_acknowledged_at = already

    session = AsyncMock()

    result = await acknowledge_consent(user=user, session=session)

    # timestamp unchanged, no commit
    assert user.consent_acknowledged_at == already
    session.commit.assert_not_called()
    assert result["requires_consent"] is False
