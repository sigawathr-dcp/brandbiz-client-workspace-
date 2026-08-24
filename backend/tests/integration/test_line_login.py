"""
Integration proof for the LINE Login entry point (migration 0063) — the
half that replaced single-use invite links.

Requires real Postgres (pytest-docker) — same harness as the other
tests/integration/*.py files. Run:
    python -m pytest backend/tests/integration/test_line_login.py -q

These are integration tests rather than unit tests on purpose: the whole
point of 0063 is that "one seat per LINE user" is a DATABASE invariant
(uq_users_line_user_id), not an application check. A stubbed session would
assert the check we wrote and prove nothing about the one that actually
holds under concurrency.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent, AgentFile
from app.models.engagement import Engagement
from app.models.file import File
from app.models.user import User
from app.models.workspace import Workspace
from app.services import engagement as engagement_svc
from app.services import workspace as workspace_svc

pytestmark = pytest.mark.asyncio


def _sub() -> str:
    """A LINE-shaped sub: 'U' + 32 hex chars."""
    return "U" + uuid.uuid4().hex


async def _provision(session: AsyncSession, sub: str, *, name: str = "สมชาย", consent: bool = True):
    # audit_svc.log opens its own session against the app's engine, which
    # this harness does not provide — same reason the other integration
    # tests patch it out.
    with patch.object(workspace_svc.audit_svc, "log", new=AsyncMock()):
        return await workspace_svc.provision_line_seat(
            session,
            line_user_id=sub,
            display_name=name,
            avatar_url=None,
            consent_given=consent,
        )


async def test_first_login_creates_one_seat_and_its_own_workspace(db_session: AsyncSession):
    sub = _sub()

    seat, workspace, is_new = await _provision(db_session, sub)

    assert is_new is True
    assert seat.line_user_id == sub
    assert seat.workspace_id == workspace.id
    assert seat.role == "L1"
    # Per-LINE-user workspace, so the pooled token budget is per person
    # rather than a pool one heavy client can drain for everyone.
    assert workspace.kind == "client"
    assert workspace.line_user_id == sub
    assert workspace.token_budget_limit is not None


async def test_returning_login_resumes_the_same_seat(db_session: AsyncSession):
    """The behavioural difference from an invite. A spent invite 410'd and
    locked the person out; the same LINE identity must land back in the seat
    it already has, with no second workspace created."""
    sub = _sub()

    first_seat, first_ws, first_new = await _provision(db_session, sub)
    second_seat, second_ws, second_new = await _provision(db_session, sub)

    assert first_new is True
    assert second_new is False
    assert second_seat.id == first_seat.id
    assert second_ws.id == first_ws.id

    seats = (await db_session.execute(
        select(func.count()).select_from(User).where(User.line_user_id == sub)
    )).scalar_one()
    workspaces = (await db_session.execute(
        select(func.count()).select_from(Workspace).where(Workspace.line_user_id == sub)
    )).scalar_one()
    assert seats == 1
    assert workspaces == 1


async def test_two_line_users_get_separate_seats_and_workspaces(db_session: AsyncSession):
    seat_a, ws_a, _ = await _provision(db_session, _sub(), name="A")
    seat_b, ws_b, _ = await _provision(db_session, _sub(), name="B")

    assert seat_a.id != seat_b.id
    assert ws_a.id != ws_b.id
    assert ws_a.slug != ws_b.slug


async def test_returning_login_refreshes_the_display_name(db_session: AsyncSession):
    sub = _sub()
    await _provision(db_session, sub, name="ชื่อเก่า")

    seat, _, _ = await _provision(db_session, sub, name="ชื่อใหม่")

    assert seat.display_name == "ชื่อใหม่"


async def test_consent_is_recorded_only_when_given(db_session: AsyncSession):
    """redeem_invite pre-set consent because a human had sent the link to a
    known contact. Self-serve LINE login has no such prior contact, so an
    unconsented seat must stay unconsented — require_consent (app/deps.py)
    is what keeps it out of /client/*."""
    seat, _, _ = await _provision(db_session, _sub(), consent=False)
    assert seat.consent_acknowledged_at is None

    consented, _, _ = await _provision(db_session, _sub(), consent=True)
    assert consented.consent_acknowledged_at is not None


async def test_deactivated_seat_cannot_log_back_in(db_session: AsyncSession):
    """Idempotent provisioning must not undo an admin's decision to
    deactivate a seat."""
    sub = _sub()
    seat, _, _ = await _provision(db_session, sub)
    seat.is_active = False
    await db_session.commit()

    with pytest.raises(Exception) as exc:
        await _provision(db_session, sub)

    assert getattr(exc.value, "status_code", None) == 403


async def test_single_engagement_cap_refuses_a_second_brief(db_session: AsyncSession):
    """Where "one client, one run" actually lives since 0063 — the entry
    point is reusable, so the funnel is what says no."""
    seat, workspace, _ = await _provision(db_session, _sub())

    with patch.object(engagement_svc.audit_svc, "log", new=AsyncMock()):
        first = await engagement_svc.get_or_create_active(db_session, seat, workspace.id)
        assert first.seq == 1

        with patch.object(engagement_svc.settings, "client_single_engagement", True):
            with pytest.raises(Exception) as exc:
                await engagement_svc.start_new(db_session, seat, workspace.id)

    assert getattr(exc.value, "status_code", None) == 409

    count = (await db_session.execute(
        select(func.count()).select_from(Engagement).where(Engagement.user_id == seat.id)
    )).scalar_one()
    assert count == 1


async def test_cap_can_be_lifted_by_configuration(db_session: AsyncSession):
    """The schema always supported repeat briefs (engagements.seq); 0063
    only changed the default. Proving the flag still opens it keeps the cap
    a policy rather than a one-way door."""
    seat, workspace, _ = await _provision(db_session, _sub())

    with patch.object(engagement_svc.audit_svc, "log", new=AsyncMock()):
        await engagement_svc.get_or_create_active(db_session, seat, workspace.id)
        with patch.object(engagement_svc.settings, "client_single_engagement", False):
            second = await engagement_svc.start_new(db_session, seat, workspace.id)

    assert second.seq == 2


# ---------------------------------------------------------------------------
# Agent provisioning (CLIENT_TEMPLATE_AGENT_ID)
# ---------------------------------------------------------------------------
# The invite flow got its agent from an admin running assign_agent() after
# POST /admin/clients. A LINE login has no admin in the loop, so a self-serve
# workspace came up agent-less — and stayed usable right up to
# POST /client/plan/draft, which 503s on a missing agent
# (services/plan.py::draft_plan). These pin the fix.


async def _template_agent(session: AsyncSession, *, n_files: int = 2):
    """An internally-authored, published agent standing in for น้องภูมิ,
    with knowledge files attached."""
    author = User(
        google_email=f"staff-{uuid.uuid4().hex}@example.com",
        display_name="Brandbiz staff",
        role="L3",
    )
    session.add(author)
    await session.flush()

    agent = Agent(
        user_id=author.id,
        name="น้องภูมิ",
        description="Brand consultant",
        instructions="คุณคือ น้องภูมิ ... ถามทีละคำถาม",
        provider="anthropic",
        model="claude-sonnet-4",
        capabilities={"web_search": True},
        creativity_level=40,
        visibility="public",
        status="published",
        # The template belongs to the demo workspace it already serves —
        # the whole reason a new workspace must get a COPY.
        workspace_id=None,
        avatar_color="#0b6",
        category="brand",
    )
    session.add(agent)
    await session.flush()

    for i in range(n_files):
        f = File(
            user_id=author.id,
            filename=f"case-{i}.pdf",
            s3_key=f"cases/{uuid.uuid4().hex}.pdf",
            scope="org",
        )
        session.add(f)
        await session.flush()
        session.add(AgentFile(agent_id=agent.id, file_id=f.id))
    await session.flush()
    return agent


async def test_line_login_clones_the_template_agent_into_its_workspace(db_session: AsyncSession):
    """The regression this whole change exists for: without an agent the
    funnel runs all the way to the plan step and then 503s."""
    template = await _template_agent(db_session)

    with patch.object(workspace_svc.settings, "client_template_agent_id", str(template.id)):
        seat, workspace, _ = await _provision(db_session, _sub())

    agent = await workspace_svc.get_workspace_agent(db_session, workspace.id)
    assert agent is not None, "self-serve workspace came up with no agent"
    assert agent.id != template.id, "the template itself was handed over, not a copy"
    assert agent.workspace_id == workspace.id
    assert agent.name == template.name
    assert agent.instructions == template.instructions
    assert agent.model == template.model
    assert agent.creativity_level == template.creativity_level
    # Forced regardless of the template's own values — a personal or draft
    # clone is invisible to the very seat it was made for.
    assert agent.visibility == "public"
    assert agent.status == "published"
    # Owned inside the workspace, so removing the template's author does not
    # CASCADE away every client's persona.
    assert agent.user_id == seat.id


async def test_clone_carries_the_knowledge_files(db_session: AsyncSession):
    """A clone without agent_files answers from nothing — the case library
    is the entire point of the persona."""
    template = await _template_agent(db_session, n_files=3)

    with patch.object(workspace_svc.settings, "client_template_agent_id", str(template.id)):
        _, workspace, _ = await _provision(db_session, _sub())

    agent = await workspace_svc.get_workspace_agent(db_session, workspace.id)
    cloned = set((await db_session.execute(
        select(AgentFile.file_id).where(AgentFile.agent_id == agent.id)
    )).scalars().all())
    original = set((await db_session.execute(
        select(AgentFile.file_id).where(AgentFile.agent_id == template.id)
    )).scalars().all())
    assert cloned == original
    assert len(cloned) == 3


async def test_template_is_left_alone(db_session: AsyncSession):
    """assign_agent() MOVES an agent (agents.workspace_id is single-valued).
    If cloning ever regressed into assigning, the first LINE login would
    silently strip the demo workspace of its persona."""
    template = await _template_agent(db_session)

    with patch.object(workspace_svc.settings, "client_template_agent_id", str(template.id)):
        _, ws_a, _ = await _provision(db_session, _sub())
        _, ws_b, _ = await _provision(db_session, _sub())

    await db_session.refresh(template)
    assert template.workspace_id is None

    # One clone each, and two different rows — not one row shuffled between
    # them, which is exactly what assign_agent() would have done.
    owned = {}
    for ws in (ws_a, ws_b):
        rows = (await db_session.execute(
            select(Agent.id).where(Agent.workspace_id == ws.id)
        )).scalars().all()
        assert len(rows) == 1, f"workspace {ws.slug} has {len(rows)} agents"
        owned[ws.id] = rows[0]
    assert len(set(owned.values())) == 2
    assert template.id not in set(owned.values())


async def test_unconfigured_template_still_lets_the_seat_in(db_session: AsyncSession):
    """No template configured is the pre-0063 state, not an error: the
    workspace is created and an admin assigns an agent by hand. Login must
    not fail over it."""
    with patch.object(workspace_svc.settings, "client_template_agent_id", ""):
        seat, workspace, is_new = await _provision(db_session, _sub())

    assert is_new is True
    assert seat.workspace_id == workspace.id
    assert await workspace_svc.get_workspace_agent(db_session, workspace.id) is None


async def test_draft_template_is_not_cloned(db_session: AsyncSession):
    """A half-edited draft must not become a live client's persona."""
    template = await _template_agent(db_session)
    template.status = "draft"
    await db_session.flush()

    with patch.object(workspace_svc.settings, "client_template_agent_id", str(template.id)):
        _, workspace, _ = await _provision(db_session, _sub())

    assert await workspace_svc.get_workspace_agent(db_session, workspace.id) is None
