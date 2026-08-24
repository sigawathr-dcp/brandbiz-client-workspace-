"""Unit tests for PATCH /client/intake/fields (Task 5.11 — editable company
profile), restored after the DB redesign dropped the original file.

Coverage moved to tests/integration/test_engagement_funnel.py, which needs a
real Postgres and so is absent from the routine `pytest tests/unit` run — the
edit path was effectively untested there. These pin the router's own logic with
a mocked session: the two 400 gates, the no-op path, and the rate-limit
contract (checked only when something will really be written, so a rejected or
no-op request can't burn the caller's slot and silently 429 the retry).

The supersede-then-insert history itself lives in _record_answer() and is
asserted in the integration test against real rows; here it's mocked out so
these stay DB-free.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.routers import client as client_router
from app.routers.client import IntakeEditIn, IntakeFieldEditIn


class _FakeUser:
    def __init__(self):
        self.id = uuid.uuid4()


class _FakeCtx:
    def __init__(self):
        self.user = _FakeUser()
        self.workspace_id = uuid.uuid4()


class _FakeEngagement:
    def __init__(self):
        self.id = uuid.uuid4()
        self.intake_script_id = uuid.uuid4()


class _FakeStep:
    def __init__(self, progress_current: int | None = 8):
        self.id = uuid.uuid4()
        self.status = "done"
        self.progress_current = progress_current


def _patches(
    *,
    fields_before: dict[str, str],
    field_index: int | None,
    resolved_value: str = "Retail + online",
):
    """Everything edit_intake_fields() reaches for, mocked. Returns the list of
    context managers plus the AsyncMocks a test needs to assert on."""
    engagement = _FakeEngagement()
    step1 = _FakeStep()

    engagement_svc = AsyncMock()
    engagement_svc.get_or_create_active = AsyncMock(return_value=engagement)
    engagement_svc.get_step = AsyncMock(return_value=step1)

    intake_svc = AsyncMock()
    intake_svc.index_of_field_db = AsyncMock(return_value=field_index)
    intake_svc.total_steps_db = AsyncMock(return_value=8)

    record_answer = AsyncMock()
    rate_check = MagicMock()  # rate_limit_svc.check is sync

    resolve = AsyncMock(
        return_value=({"field": "industry"}, resolved_value, uuid.uuid4(), [uuid.uuid4()], "chip")
    )

    cms = [
        patch.object(client_router, "engagement_svc", engagement_svc),
        patch.object(client_router, "intake_svc", intake_svc),
        patch.object(client_router, "_load_fields", AsyncMock(return_value=fields_before)),
        patch.object(client_router, "_resolve_answer_value", resolve),
        patch.object(client_router, "_record_answer", record_answer),
        patch.object(client_router.audit_svc, "log", new=AsyncMock()),
        patch.object(client_router.rate_limit_svc, "check", rate_check),
    ]
    return cms, record_answer, rate_check


def _body(field: str = "industry", option_index: int = 1) -> IntakeEditIn:
    return IntakeEditIn(updates=[IntakeFieldEditIn(field=field, option_index=option_index)])


@pytest.mark.asyncio
async def test_edit_records_answer_and_reports_it_changed():
    cms, record_answer, rate_check = _patches(
        fields_before={"industry": "Services / B2B"}, field_index=0
    )
    session = AsyncMock()
    with cms[0], cms[1], cms[2], cms[3], cms[4], cms[5], cms[6]:
        out = await client_router.edit_intake_fields(_body(), _FakeCtx(), session)

    assert out.changed == ["industry"]
    record_answer.assert_awaited_once()
    # The row must be marked as a correction, not as an original answer — the
    # distinction the old single-blob client_profiles could never record.
    assert record_answer.await_args.kwargs["source"] == "edit"
    session.commit.assert_awaited()
    rate_check.assert_called_once()


@pytest.mark.asyncio
async def test_unknown_field_is_rejected_without_spending_the_rate_limit():
    cms, record_answer, rate_check = _patches(fields_before={}, field_index=None)
    with cms[0], cms[1], cms[2], cms[3], cms[4], cms[5], cms[6]:
        with pytest.raises(HTTPException) as exc:
            await client_router.edit_intake_fields(_body(field="nope"), _FakeCtx(), AsyncMock())

    assert exc.value.status_code == 400
    assert "Unknown field" in exc.value.detail
    record_answer.assert_not_awaited()
    rate_check.assert_not_called()


@pytest.mark.asyncio
async def test_field_not_yet_asked_is_rejected_without_spending_the_rate_limit():
    # progress_current is 8, so index 8 has not been reached yet.
    cms, record_answer, rate_check = _patches(fields_before={}, field_index=8)
    with cms[0], cms[1], cms[2], cms[3], cms[4], cms[5], cms[6]:
        with pytest.raises(HTTPException) as exc:
            await client_router.edit_intake_fields(_body(), _FakeCtx(), AsyncMock())

    assert exc.value.status_code == 400
    assert "hasn't been asked yet" in exc.value.detail
    record_answer.assert_not_awaited()
    rate_check.assert_not_called()


@pytest.mark.asyncio
async def test_resubmitting_the_same_value_is_a_no_op():
    cms, record_answer, rate_check = _patches(
        fields_before={"industry": "Retail + online"}, field_index=0, resolved_value="Retail + online"
    )
    session = AsyncMock()
    with cms[0], cms[1], cms[2], cms[3], cms[4], cms[5], cms[6]:
        out = await client_router.edit_intake_fields(_body(), _FakeCtx(), session)

    assert out.changed == []
    record_answer.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited()
    # A no-op must not cost the caller their slot either.
    rate_check.assert_not_called()
