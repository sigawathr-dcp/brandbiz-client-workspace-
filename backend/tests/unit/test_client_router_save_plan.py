"""Unit test for plan_svc.save_plan() creating an independent plan even
when the seat already has one (Task 5.12 — multiple plans per seat).

POST /client/plans always delegates straight to save_plan(); the frontend
relies on that staying true (it's how "Save as a new plan" differs from
"Save as vN" -> PUT /client/plans/{id}, which calls revise_plan() instead).
save_plan() takes no plan_id and never queries for an existing plan before
inserting — this pins that it can't accidentally find and touch one.

DB redesign: Plan is now a head row only — version/title live on
PlanVersion (see app/models/plan.py) — and save_plan() takes the seat's
Engagement (for conversation_id/id) rather than a bare conversation_id.
_persist_version() does issue a SELECT per non-empty budget line (to
resolve rate_card_item_id), so this test uses an empty `lines: []` draft
to keep the "no query before insert" guarantee meaningful and checkable.
"""
from __future__ import annotations

import base64
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services import plan as plan_svc


@pytest.fixture(autouse=True)
def set_encryption_key(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", base64.b64encode(b"A" * 32).decode())
    import app.crypto as crypto_mod
    crypto_mod._key = None
    yield
    crypto_mod._key = None


def _draft(title: str) -> dict:
    return {
        "title": title,
        "core_idea": "idea",
        "analogous_case": "case",
        "adapted_plan": [],
        "budget": {"lines": [], "needs_expert": [], "subtotal": "0", "contingency": "0", "total": "0", "currency": "THB"},
        "provenance": {},
    }


class _FakeUser:
    def __init__(self):
        self.id = uuid.uuid4()


class _FakeEngagement:
    def __init__(self):
        self.id = uuid.uuid4()
        self.conversation_id = uuid.uuid4()
        self.active_plan_id = None


@pytest.mark.asyncio
async def test_save_plan_never_queries_for_an_existing_plan_before_inserting():
    user = _FakeUser()
    workspace_id = uuid.uuid4()
    engagement = _FakeEngagement()
    session = AsyncMock()

    with patch.object(plan_svc.audit_svc, "log", new=AsyncMock()):
        plan = await plan_svc.save_plan(session, user, workspace_id, engagement, _draft("Second plan"))

    # No SELECT ever ran (an empty budget has no rate-card codes to look
    # up) — save_plan() is unconditional, so calling it twice produces two
    # independent rows rather than ever colliding with/overwriting one.
    session.execute.assert_not_called()
    assert plan.engagement_id == engagement.id
    # The active engagement now tracks which plan is "current" — replaces
    # the old bb:activePlan:* localStorage key.
    assert engagement.active_plan_id == plan.id
    added_versions = [c.args[0] for c in session.add.call_args_list if hasattr(c.args[0], "version_no")]
    assert len(added_versions) == 1
    assert added_versions[0].version_no == 1
    assert added_versions[0].title == "Second plan"
