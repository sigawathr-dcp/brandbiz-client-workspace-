"""
Integration proof for the DB redesign's engagement backbone — real
Postgres (pytest-docker), same harness as the other tests/integration/*.py
files. Run:
    python -m pytest backend/tests/integration/test_engagement_funnel.py -q

Supersedes the pre-redesign tests/unit/test_client_bootstrap_replay.py,
test_client_router_intake.py, and test_client_router_intake_edit.py, which
mocked ClientProfile and the router's old query-by-query internals
directly. Those internals no longer exist (client_profiles was replaced by
engagements/engagement_steps/intake_answers — see app/models/engagement.py
and app/models/intake.py), and hand-mocking the new router's several
sequential async DB calls would pin implementation, not behavior. This
file exercises the same behavioral guarantees against a real database
instead:
  - bootstrap creates one engagement with 4 idle steps
  - the "insight" in POST /intake/answer's response belongs to the step
    just answered, not the next one returned in current_step
  - PATCH /intake/fields only allows editing an already-reached question,
    and edits are append-only (supersede, never overwrite)
  - a zero-match case run reports done/0 from engagement_steps directly —
    no audit_log probe anywhere in this path anymore
  - save_plan()/revise_plan() version bumps and Plan.current_version_id

This intentionally does NOT exercise POST /client/research or
POST /client/plan/draft's LLM call (those need a real/mocked model
provider) — case-match's RAG call and the drafting prompt's LLM call are
mocked out so this stays a database-behavior test, not an LLM-availability
test.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intake import IntakeOption, IntakeQuestion, IntakeScript
from app.models.user import User
from app.models.workspace import Workspace
from app.routers import client as client_router
from app.services import client_intake as intake_svc
from app.services import engagement as engagement_svc
from app.services import plan as plan_svc
from app.services.case_match import CaseMatchRun
from app.deps import ClientContext


async def _seed_intake_script(session: AsyncSession) -> None:
    """This integration harness builds its schema from Base.metadata
    (conftest.py::_create_schema), not by running Alembic — so migration
    0052's one-time seed of intake_scripts/questions/options never runs
    here. Mirror it directly from the same INTAKE_SCRIPT literal.

    Version is randomized per call: the router functions this test drives
    (bootstrap/answer_intake/...) commit mid-request, same as they do in
    production, so db_session's end-of-test rollback can't undo a script
    seeded earlier in the SAME test session — a fixed version=1 would
    collide with uq_intake_scripts_version_locale the moment a second test
    in this file runs."""
    script = IntakeScript(version=uuid.uuid4().int % 1_000_000_000, locale="th", name="Test script", active=True)
    session.add(script)
    await session.flush()
    for ordinal, step in enumerate(intake_svc.INTAKE_SCRIPT):
        question = IntakeQuestion(
            script_id=script.id, ordinal=ordinal, field_key=step["field"],
            prompt=step["question"], insight=step.get("insight"),
        )
        session.add(question)
        await session.flush()
        for opt_ordinal, option in enumerate(step["options"]):
            session.add(IntakeOption(
                question_id=question.id, ordinal=opt_ordinal, label=option["label"], value=option["value"],
            ))
    await session.flush()


async def _make_seat(session: AsyncSession) -> tuple[Workspace, User]:
    ws = Workspace(name="Funnel WS", slug=f"funnel-{uuid.uuid4().hex[:8]}", kind="demo")
    session.add(ws)
    await session.flush()
    user = User(google_email=f"funnel-{uuid.uuid4().hex[:8]}@example.com", role="L1", workspace_id=ws.id)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return ws, user


@pytest.mark.asyncio
async def test_bootstrap_creates_one_engagement_with_four_idle_steps(db_session: AsyncSession):
    await _seed_intake_script(db_session)
    ws, user = await _make_seat(db_session)

    with patch.object(client_router.settings, "client_surface_enabled", True):
        out = await client_router.bootstrap(
            ClientContext(user=user, workspace_id=ws.id, is_preview=False), db_session,
        )

    assert out.step == 0
    assert out.total_steps == 8
    assert out.completed is False
    assert out.research_status == "idle"
    assert out.cases_status == "idle"
    assert out.plan_count == 0
    assert out.active_plan_id is None

    steps = await engagement_svc.get_steps(db_session, out.engagement_id)
    assert {s.step_key: s.status for s in steps.values()} == {
        "interview": "idle", "market": "idle", "cases": "idle", "plan": "idle",
    }


@pytest.mark.asyncio
async def test_insight_belongs_to_the_step_just_answered_not_the_next_one(db_session: AsyncSession):
    await _seed_intake_script(db_session)
    ws, user = await _make_seat(db_session)
    ctx = ClientContext(user=user, workspace_id=ws.id, is_preview=False)

    with patch.object(client_router.settings, "client_surface_enabled", True):
        await client_router.bootstrap(ctx, db_session)  # creates the engagement

        first = await client_router.answer_intake(
            client_router.IntakeAnswerIn(option_index=1, free_text=None), ctx, db_session,
        )
        # INTAKE_SCRIPT[0]'s (industry) insight, not INTAKE_SCRIPT[1]'s (stage).
        assert first.insight == intake_svc.INTAKE_SCRIPT[0]["insight"]
        assert first.current_step.field == "stage"
        assert first.step == 1

        second = await client_router.answer_intake(
            client_router.IntakeAnswerIn(option_index=0, free_text=None), ctx, db_session,
        )
        assert second.insight == intake_svc.INTAKE_SCRIPT[1]["insight"]
        assert second.step == 2


@pytest.mark.asyncio
async def test_edit_intake_fields_rejects_a_question_not_yet_reached_and_is_append_only(db_session: AsyncSession):
    await _seed_intake_script(db_session)
    ws, user = await _make_seat(db_session)
    ctx = ClientContext(user=user, workspace_id=ws.id, is_preview=False)

    with patch.object(client_router.settings, "client_surface_enabled", True):
        boot = await client_router.bootstrap(ctx, db_session)
        step1 = await engagement_svc.get_step(db_session, boot.engagement_id, "interview")
        await client_router.answer_intake(
            client_router.IntakeAnswerIn(option_index=1, free_text=None), ctx, db_session,
        )  # answers 'industry' only — progress_current == 1

        # 'stage' (index 1) hasn't been asked yet.
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await client_router.edit_intake_fields(
                client_router.IntakeEditIn(updates=[
                    client_router.IntakeFieldEditIn(field="stage", option_index=0)
                ]),
                ctx, db_session,
            )
        assert exc_info.value.status_code == 400

        # PATCH /intake/fields is rate-limited to 1/60s per user
        # (app/services/rate_limit.py) — the rejected call above already
        # consumed this test's slot, so clear it before the real edit
        # below. Not a redesign concern; this limiter predates it.
        from app.services import rate_limit as rate_limit_svc
        rate_limit_svc._WINDOWS.pop(f"intake_edit:{user.id}", None)

        # 'industry' has been asked — editing it is allowed and supersedes.
        edited = await client_router.edit_intake_fields(
            client_router.IntakeEditIn(updates=[
                client_router.IntakeFieldEditIn(field="industry", option_index=2)
            ]),
            ctx, db_session,
        )
        assert edited.changed == ["industry"]
        assert edited.fields["industry"] == intake_svc.INTAKE_SCRIPT[0]["options"][2]["value"]

        from app.models.intake import IntakeAnswer
        rows = (await db_session.execute(
            select(IntakeAnswer).where(
                IntakeAnswer.engagement_step_id == step1.id, IntakeAnswer.field_key == "industry"
            )
        )).scalars().all()
        assert len(rows) == 2  # original (now superseded) + the edit
        assert sum(1 for r in rows if r.superseded_at is None) == 1


@pytest.mark.asyncio
async def test_case_match_zero_results_reports_done_without_any_audit_log_probe(db_session: AsyncSession):
    await _seed_intake_script(db_session)
    ws, user = await _make_seat(db_session)
    ctx = ClientContext(user=user, workspace_id=ws.id, is_preview=False)

    with patch.object(client_router.settings, "client_surface_enabled", True):
        await client_router.bootstrap(ctx, db_session)
        for i in range(8):
            await client_router.answer_intake(
                client_router.IntakeAnswerIn(option_index=0, free_text=None), ctx, db_session,
            )

        with (
            patch.object(client_router.workspace_svc, "get_workspace_agent", new=AsyncMock(return_value=None)),
            patch.object(
                client_router.case_match_svc, "match_cases",
                new=AsyncMock(return_value=CaseMatchRun(query="q", chunks_retrieved=0, results=[])),
            ),
            patch.object(client_router.audit_svc, "log", new=AsyncMock()),
        ):
            cases_out = await client_router.run_case_match(ctx, db_session)

        assert cases_out == {"matches": []}

        # Reload via bootstrap — must report done/empty from
        # engagement_steps directly, not by probing audit_log.
        with patch.object(client_router, "audit_svc") as audit_mod:
            audit_mod.log = AsyncMock()
            out = await client_router.bootstrap(ctx, db_session)
        assert out.cases_status == "done"
        assert out.cases == {"matches": []}


@pytest.mark.asyncio
async def test_save_then_revise_bumps_version_and_repoints_current(db_session: AsyncSession):
    await _seed_intake_script(db_session)
    ws, user = await _make_seat(db_session)
    engagement = await engagement_svc.get_or_create_active(db_session, user, ws.id)

    def _draft(title: str) -> dict:
        return {
            "title": title, "core_idea": "idea", "analogous_case": "case", "adapted_plan": [],
            "budget": {"lines": [], "needs_expert": [], "subtotal": "0", "contingency": "0",
                       "total": "0", "currency": "THB"},
            "provenance": {},
        }

    with patch.object(plan_svc.audit_svc, "log", new=AsyncMock()):
        plan = await plan_svc.save_plan(db_session, user, ws.id, engagement, _draft("v1 title"))
        v1 = await plan_svc.get_current_version(db_session, plan)
        assert v1.version_no == 1
        assert v1.title == "v1 title"

        revised = await plan_svc.revise_plan(db_session, user, ws.id, plan.id, _draft("v2 title"))
        assert revised.id == plan.id
        v2 = await plan_svc.get_current_version(db_session, revised)
        assert v2.version_no == 2
        assert v2.title == "v2 title"

        versions = await plan_svc.list_versions(db_session, plan.id)
        assert [v.version_no for v in versions] == [1, 2]

    await db_session.refresh(engagement)
    assert engagement.active_plan_id == plan.id
