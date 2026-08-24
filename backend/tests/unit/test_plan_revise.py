"""Unit tests for plan_svc.revise_plan() (Task 5.11 — profile edit ->
resubmit -> plan v2+).

DB redesign: Plan is now a head row only (see app/models/plan.py) —
version/title/body/budget/provenance all live on PlanVersion, and writing
one (including exploding its budget/provenance into PlanBudgetLine/
PlanSource rows) is `_persist_version()`'s job, not revise_plan()'s. So
these tests mock plan_svc.get_plan (ownership/404 — exercised for real by
the DB-backed integration suite) and plan_svc._persist_version (row
creation — likewise), and pin exactly the logic that's revise_plan()'s own
responsibility and easy to get wrong: which version number gets requested,
that Plan.current_version_id gets repointed, that status never changes,
and the audit log.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services import plan as plan_svc


def _draft(**overrides) -> dict:
    draft = {
        "title": "Revised plan",
        "core_idea": "New core idea",
        "analogous_case": "New analogous case",
        "adapted_plan": [{"period": "Wk 1-2", "text": "Do the new thing"}],
        "budget": {"lines": [], "needs_expert": [], "subtotal": "0", "contingency": "0", "total": "0", "currency": "THB"},
        "provenance": {"research_run_id": "new-run-id"},
    }
    draft.update(overrides)
    return draft


def _version_no_result(n: int) -> MagicMock:
    result = MagicMock()
    result.scalar_one.return_value = n
    return result


def _new_version(version_no: int) -> MagicMock:
    v = MagicMock()
    v.id = uuid.uuid4()
    v.version_no = version_no
    v.title = "Revised plan"
    return v


@pytest.mark.asyncio
async def test_revise_requests_the_next_version_number_and_repoints_current():
    user = MagicMock()
    user.id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    plan_id = uuid.uuid4()

    plan = MagicMock()
    plan.id = plan_id
    plan.status = "draft"

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_version_no_result(1))
    new_version = _new_version(2)

    with (
        patch.object(plan_svc, "get_plan", new=AsyncMock(return_value=plan)),
        patch.object(plan_svc, "_persist_version", new=AsyncMock(return_value=new_version)) as persist,
        patch.object(plan_svc.audit_svc, "log", new=AsyncMock()),
    ):
        result = await plan_svc.revise_plan(session, user, workspace_id, plan_id, _draft())

    assert result is plan
    assert plan.current_version_id == new_version.id
    persist.assert_awaited_once()
    args = persist.call_args[0]
    assert args[0] is session
    assert args[1] is plan
    assert args[2] is user
    assert args[3] == workspace_id
    assert args[4] == 2  # latest (1) + 1


@pytest.mark.asyncio
async def test_revise_never_changes_status():
    # "draft · awaiting expert review" is a liability control, not
    # decoration (PLAN.md Phase 5 redesign notes) — a revision must stay a
    # draft exactly like the original.
    user = MagicMock()
    user.id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    plan_id = uuid.uuid4()

    plan = MagicMock()
    plan.id = plan_id
    plan.status = "draft"

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_version_no_result(1))

    with (
        patch.object(plan_svc, "get_plan", new=AsyncMock(return_value=plan)),
        patch.object(plan_svc, "_persist_version", new=AsyncMock(return_value=_new_version(2))),
        patch.object(plan_svc.audit_svc, "log", new=AsyncMock()),
    ):
        await plan_svc.revise_plan(session, user, workspace_id, plan_id, _draft())

    assert plan.status == "draft"


@pytest.mark.asyncio
async def test_revise_logs_plan_updated_with_the_new_version():
    user = MagicMock()
    user.id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    plan_id = uuid.uuid4()

    plan = MagicMock()
    plan.id = plan_id
    plan.status = "draft"

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_version_no_result(3))

    with (
        patch.object(plan_svc, "get_plan", new=AsyncMock(return_value=plan)),
        patch.object(plan_svc, "_persist_version", new=AsyncMock(return_value=_new_version(4))),
        patch.object(plan_svc.audit_svc, "log", new=AsyncMock()) as log,
    ):
        await plan_svc.revise_plan(session, user, workspace_id, plan_id, _draft())

    log.assert_awaited_once()
    _, kwargs = log.call_args
    assert kwargs["action"] == "plan_updated"
    assert kwargs["details"]["version"] == 4


@pytest.mark.asyncio
async def test_revise_404s_for_a_plan_the_caller_does_not_own():
    user = MagicMock()
    user.id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    plan_id = uuid.uuid4()

    session = AsyncMock()

    with patch.object(
        plan_svc,
        "get_plan",
        new=AsyncMock(side_effect=HTTPException(status_code=404, detail="Plan not found")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await plan_svc.revise_plan(session, user, workspace_id, plan_id, _draft())

    assert exc_info.value.status_code == 404
    session.execute.assert_not_called()
