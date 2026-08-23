"""Unit tests for what POST /client/chat does with the seat's plan.

Three collaborating pieces, split because they answer different questions:

  - _resolve_chat_plan  — WHICH plan this turn is about. Access control: an
    explicit plan_id goes through plan_svc.get_plan (the ownership check that
    404s another seat's plan, same as GET /client/plans/{id}); no plan_id falls
    back to the engagement's active plan through the non-raising lookup, so a
    dangling engagements.active_plan_id degrades to an ordinary chat turn
    instead of making the seat unable to chat at all.
  - _plan_chat_context  — that plan rendered as system context, or "" when
    there is none.
  - _suggest_plan_edit  — whether to offer the "ปรับแผนให้เลย" chip. Gated on
    the intake being finished, checked server-side.

Resolution happens ONCE per turn and feeds both of the latter two, so they can
never disagree about which plan the client meant.

DB-free — the same mocked-session style as test_client_router_intake_edit.py.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.routers import client as client_router


class _FakeCtx:
    def __init__(self):
        self.user = MagicMock(id=uuid.uuid4())
        self.workspace_id = uuid.uuid4()


def _plan_svc(*, active_plan=None, get_plan=None, context="[CURRENT PLAN]\nTitle: X"):
    svc = AsyncMock()
    svc.get_active_plan = AsyncMock(return_value=active_plan)
    svc.get_plan = AsyncMock(return_value=get_plan)
    svc.plan_context_for_plan = AsyncMock(return_value=context)
    return svc


def _engagement_svc(active_plan_id=None, interview_status="done"):
    svc = AsyncMock()
    svc.get_or_create_active = AsyncMock(return_value=MagicMock(active_plan_id=active_plan_id))
    svc.get_step = AsyncMock(return_value=MagicMock(status=interview_status))
    return svc


# ---------------------------------------------------------------------------
# _resolve_chat_plan — access control
# ---------------------------------------------------------------------------

async def test_explicit_plan_id_is_ownership_checked():
    ctx = _FakeCtx()
    plan_id = uuid.uuid4()
    plan = MagicMock()
    svc = _plan_svc(get_plan=plan)

    with patch.object(client_router, "plan_svc", svc):
        resolved = await client_router._resolve_chat_plan(AsyncMock(), ctx, plan_id)

    assert resolved is plan
    # get_plan is the 404-on-another-seat's-plan check; it must be the path
    # taken, not the non-raising active-plan lookup.
    svc.get_plan.assert_awaited_once()
    assert svc.get_plan.await_args.args[1:] == (ctx.user, ctx.workspace_id, plan_id)
    svc.get_active_plan.assert_not_awaited()


async def test_another_seats_plan_id_propagates_404():
    ctx = _FakeCtx()
    svc = _plan_svc()
    svc.get_plan = AsyncMock(side_effect=HTTPException(status_code=404, detail="Plan not found"))

    with patch.object(client_router, "plan_svc", svc):
        with pytest.raises(HTTPException) as exc:
            await client_router._resolve_chat_plan(AsyncMock(), ctx, uuid.uuid4())

    assert exc.value.status_code == 404


async def test_no_plan_id_falls_back_to_the_engagements_active_plan():
    ctx = _FakeCtx()
    active_id = uuid.uuid4()
    plan = MagicMock()
    svc = _plan_svc(active_plan=plan)

    with patch.object(client_router, "plan_svc", svc), \
            patch.object(client_router, "engagement_svc", _engagement_svc(active_id)):
        resolved = await client_router._resolve_chat_plan(AsyncMock(), ctx, None)

    assert resolved is plan
    assert svc.get_active_plan.await_args.args[1:] == (ctx.user, ctx.workspace_id, active_id)
    svc.get_plan.assert_not_awaited()


async def test_dangling_active_plan_id_does_not_break_chat():
    """active_plan_id set but the row is gone/foreign: get_active_plan returns
    None rather than raising, so the client can still talk to their agent."""
    ctx = _FakeCtx()
    svc = _plan_svc(active_plan=None)

    with patch.object(client_router, "plan_svc", svc), \
            patch.object(client_router, "engagement_svc", _engagement_svc(uuid.uuid4())):
        resolved = await client_router._resolve_chat_plan(AsyncMock(), ctx, None)

    assert resolved is None


# ---------------------------------------------------------------------------
# _plan_chat_context — rendering
# ---------------------------------------------------------------------------

async def test_resolved_plan_is_rendered_as_context():
    svc = _plan_svc()

    with patch.object(client_router, "plan_svc", svc):
        block = await client_router._plan_chat_context(AsyncMock(), MagicMock())

    assert block == "[CURRENT PLAN]\nTitle: X"
    svc.plan_context_for_plan.assert_awaited_once()


async def test_seat_with_no_plan_yet_gets_no_block():
    """Pre-plan chat (during the intake, before step 4) must be unchanged —
    an empty block leaves prepare_chat's system prompt exactly as it was."""
    svc = _plan_svc()

    with patch.object(client_router, "plan_svc", svc):
        block = await client_router._plan_chat_context(AsyncMock(), None)

    assert block == ""
    svc.plan_context_for_plan.assert_not_awaited()


# ---------------------------------------------------------------------------
# _suggest_plan_edit — when the confirmation chip is offered
# ---------------------------------------------------------------------------

_EDIT_TURN = "ขอปรับแผน เพิ่มงบ content หน่อย"       # "adjust the plan, add content budget"
_QUESTION_TURN = "ทำไมงบเฟส 2 ถึงเพิ่มขึ้น"            # "why did phase 2's budget go up"


async def test_edit_request_with_a_finished_intake_offers_the_chip():
    ctx = _FakeCtx()

    with patch.object(client_router, "engagement_svc", _engagement_svc(interview_status="done")):
        assert await client_router._suggest_plan_edit(
            AsyncMock(), ctx, MagicMock(), _EDIT_TURN
        ) is True


async def test_no_chip_before_the_intake_is_finished():
    """Same gate POST /client/plan/draft enforces, and checked here rather than
    trusted from the frontend: a plan revised against a half-answered profile
    is a plan drafted from nothing."""
    ctx = _FakeCtx()

    with patch.object(client_router, "engagement_svc", _engagement_svc(interview_status="running")):
        assert await client_router._suggest_plan_edit(
            AsyncMock(), ctx, MagicMock(), _EDIT_TURN
        ) is False


async def test_no_chip_when_the_seat_has_no_plan_to_edit():
    ctx = _FakeCtx()
    svc = _engagement_svc()

    with patch.object(client_router, "engagement_svc", svc):
        assert await client_router._suggest_plan_edit(AsyncMock(), ctx, None, _EDIT_TURN) is False

    # ...and it short-circuits before spending a lookup on the engagement.
    svc.get_or_create_active.assert_not_awaited()


async def test_a_question_about_the_plan_is_not_an_edit_request():
    """The turn that made this whole feature risky: a question containing an
    edit verb ("เพิ่มขึ้น") must not offer to rewrite the budget."""
    ctx = _FakeCtx()
    svc = _engagement_svc()

    with patch.object(client_router, "engagement_svc", svc):
        assert await client_router._suggest_plan_edit(
            AsyncMock(), ctx, MagicMock(), _QUESTION_TURN
        ) is False

    svc.get_or_create_active.assert_not_awaited()
