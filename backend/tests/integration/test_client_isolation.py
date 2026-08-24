"""
D23 — integration proof that tenant isolation actually holds under the
real production queries, not just clause-structure assertions.

Requires real Postgres (pytest-docker) — same harness as the other
tests/integration/*.py files. Run:
    python -m pytest backend/tests/integration/test_client_isolation.py -q

Setup: two client workspaces (A, B) each with one seat, one internal staff
user, and nine rows (File/Skill/Agent x {A, B, NULL}) inserted directly via
ORM models — not through create_agent()/create_skill(), which call
audit_svc.log() and would fail silently against this harness's ENUM DDL
(see conftest.py's _ENUM_DDL — audit writes swallow errors by design, §7.3,
so a silent skip is worse than a loud one here).

Then the REAL production queries (routers.files.list_files,
services.skill.list_skills, services.agent.list_agents,
tools.rag_search._scope_filter) are run as each user, under both
CLIENT_INTERNAL_ACCESS_ENABLED states, and the visible-row sets are
asserted directly. This is the test clause-structure assertions
structurally cannot be: it catches `==` vs `is_not_distinct_from` (which
silently drops every internal-shared row), a missing disjunct, or a
disjunct widened on the wrong side.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.agent import Agent
from app.models.file import File
from app.models.plan import Plan
from app.models.skill import Skill
from app.models.user import User
from app.models.workspace import Workspace


async def _insert_workspace(session: AsyncSession, slug: str) -> uuid.UUID:
    ws = Workspace(name=slug, slug=slug, kind="client")
    session.add(ws)
    await session.flush()
    return ws.id


async def _insert_user(
    session: AsyncSession, *, email: str, workspace_id: uuid.UUID | None
) -> User:
    user = User(google_email=email, role="L1" if workspace_id else "L3", workspace_id=workspace_id)
    session.add(user)
    await session.flush()
    return user


async def _insert_file(
    session: AsyncSession, *, owner: User, workspace_id: uuid.UUID | None, name: str
) -> None:
    session.add(File(
        user_id=owner.id, filename=name, s3_key=f"/tmp/{name}",
        scope="org", is_processed=True, workspace_id=workspace_id,
    ))


async def _insert_skill(
    session: AsyncSession, *, owner: User, workspace_id: uuid.UUID | None, name: str
) -> None:
    session.add(Skill(
        user_id=owner.id, name=name, visibility="public", workspace_id=workspace_id,
    ))


async def _insert_agent(
    session: AsyncSession, *, owner: User, workspace_id: uuid.UUID | None, name: str
) -> None:
    session.add(Agent(
        user_id=owner.id, name=name, provider="local", model="gemma4:26b",
        visibility="public", status="published", workspace_id=workspace_id,
    ))


@pytest.fixture
def flag_off(monkeypatch):
    import app.services.workspace as workspace_module

    monkeypatch.setattr(workspace_module.settings, "client_internal_access_enabled", False)


@pytest.fixture
def flag_on(monkeypatch):
    import app.services.workspace as workspace_module

    monkeypatch.setattr(workspace_module.settings, "client_internal_access_enabled", True)


class _World:
    """Everything a test needs: three users and nine rows, {A, B, NULL} x
    {File, Skill, Agent}, all owned by an unrelated bystander user so the
    ownership branch of each accessible-filter never accidentally grants
    access — only the workspace-gated "shared" branch is under test."""

    def __init__(self, staff, seat_a, seat_b):
        self.staff = staff
        self.seat_a = seat_a
        self.seat_b = seat_b


async def _build_world(session: AsyncSession) -> _World:
    ws_a = await _insert_workspace(session, f"tenant-a-{uuid.uuid4().hex[:8]}")
    ws_b = await _insert_workspace(session, f"tenant-b-{uuid.uuid4().hex[:8]}")

    staff = await _insert_user(session, email=f"staff-{uuid.uuid4().hex}@test.local", workspace_id=None)
    seat_a = await _insert_user(session, email=f"seat-a-{uuid.uuid4().hex}@a.client.invalid", workspace_id=ws_a)
    seat_b = await _insert_user(session, email=f"seat-b-{uuid.uuid4().hex}@b.client.invalid", workspace_id=ws_b)
    # Bystander: owns every row, so no test result can be explained by the
    # ownership branch of _accessible_filter / list_files' own-row branch.
    bystander = await _insert_user(session, email=f"owner-{uuid.uuid4().hex}@test.local", workspace_id=None)

    for ws_id, tag in ((ws_a, "a"), (ws_b, "b"), (None, "null")):
        await _insert_file(session, owner=bystander, workspace_id=ws_id, name=f"file-{tag}")
        await _insert_skill(session, owner=bystander, workspace_id=ws_id, name=f"skill-{tag}")
        await _insert_agent(session, owner=bystander, workspace_id=ws_id, name=f"agent-{tag}")

    await session.commit()
    return _World(staff, seat_a, seat_b)


def _tags(names: list[str], prefix: str) -> set[str]:
    return {n[len(prefix):] for n in names if n.startswith(prefix)}


async def _visible_files(session: AsyncSession, user: User) -> set[str]:
    from app.routers.files import list_files

    result = await list_files(user, session)  # type: ignore[arg-type]
    return _tags([f.filename for f in result.items], "file-")


async def _visible_skills(session: AsyncSession, user: User) -> set[str]:
    from app.services.skill import list_skills

    skills, _total = await list_skills(session, user.id)
    return _tags([s.name for s in skills], "skill-")


async def _visible_agents(session: AsyncSession, user: User) -> set[str]:
    from app.services.agent import list_agents

    agents, _total = await list_agents(session, user.id)
    return _tags([a.name for a in agents], "agent-")


async def _visible_via_scope_filter(session: AsyncSession, user: User) -> set[str]:
    from app.tools.rag_search import _scope_filter

    result = await session.execute(select(File).where(_scope_filter(user, None)))
    return _tags([f.filename for f in result.scalars().all()], "file-")


@pytest.mark.asyncio
class TestClientIsolationFlagOff:
    """D21/D22 baseline: each client seat sees only its own workspace's
    shared rows; staff sees only the internal (NULL) shared rows."""

    async def test_isolation_holds(self, flag_off, db_engine_sync: str):
        engine = create_async_engine(db_engine_sync, echo=False)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            world = await _build_world(session)

            assert await _visible_files(session, world.seat_a) == {"a"}
            assert await _visible_files(session, world.seat_b) == {"b"}
            assert await _visible_files(session, world.staff) == {"null"}
            assert await _visible_via_scope_filter(session, world.seat_a) == {"a"}
            assert await _visible_via_scope_filter(session, world.staff) == {"null"}

            assert await _visible_skills(session, world.seat_a) == {"a"}
            assert await _visible_skills(session, world.seat_b) == {"b"}
            assert await _visible_skills(session, world.staff) == {"null"}

            assert await _visible_agents(session, world.seat_a) == {"a"}
            assert await _visible_agents(session, world.seat_b) == {"b"}
            assert await _visible_agents(session, world.staff) == {"null"}
        await engine.dispose()


@pytest.mark.asyncio
class TestClientIsolationFlagOn:
    """D23: each client seat additionally sees the shared internal (NULL)
    pool, same as staff — but two client seats must still never see each
    other's workspace. This is the invariant D23 does not relax."""

    async def test_seats_gain_the_shared_pool_but_not_each_other(self, flag_on, db_engine_sync: str):
        engine = create_async_engine(db_engine_sync, echo=False)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            world = await _build_world(session)

            assert await _visible_files(session, world.seat_a) == {"a", "null"}
            assert await _visible_files(session, world.seat_b) == {"b", "null"}
            assert await _visible_files(session, world.staff) == {"null"}
            assert await _visible_via_scope_filter(session, world.seat_a) == {"a", "null"}

            assert await _visible_skills(session, world.seat_a) == {"a", "null"}
            assert await _visible_skills(session, world.seat_b) == {"b", "null"}

            assert await _visible_agents(session, world.seat_a) == {"a", "null"}
            assert await _visible_agents(session, world.seat_b) == {"b", "null"}

            # The invariant: neither seat's set contains the other's tag.
            assert "b" not in await _visible_files(session, world.seat_a)
            assert "a" not in await _visible_files(session, world.seat_b)
            assert "b" not in await _visible_skills(session, world.seat_a)
            assert "a" not in await _visible_skills(session, world.seat_b)
            assert "b" not in await _visible_agents(session, world.seat_a)
            assert "a" not in await _visible_agents(session, world.seat_b)
        await engine.dispose()


async def _insert_library_file(session: AsyncSession, *, owner: User, name: str) -> None:
    session.add(File(
        user_id=owner.id, filename=name, s3_key=f"/tmp/{name}",
        scope="library", is_processed=True, workspace_id=None,
    ))


@pytest.mark.asyncio
class TestCaseLibraryScope:
    """ADR 0002 — a scope='library' file is visible to every tenant (both
    seats and staff) under BOTH flag states, while org isolation between
    seats is untouched. Runs the real rag_search._scope_filter and
    routers.files.list_files, like the classes above."""

    async def _assert_library_visible_to_everyone(self, session: AsyncSession) -> None:
        world = await _build_world(session)
        bystander = await _insert_user(
            session, email=f"lib-owner-{uuid.uuid4().hex}@test.local", workspace_id=None
        )
        await _insert_library_file(session, owner=bystander, name="file-library")
        await session.commit()

        for user in (world.seat_a, world.seat_b, world.staff):
            assert "library" in await _visible_via_scope_filter(session, user)
            assert "library" in await _visible_files(session, user)

        # Tenant isolation between seats is unchanged by the new disjunct.
        assert "b" not in await _visible_via_scope_filter(session, world.seat_a)
        assert "a" not in await _visible_via_scope_filter(session, world.seat_b)

    async def test_flag_off(self, flag_off, db_engine_sync: str):
        engine = create_async_engine(db_engine_sync, echo=False)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            await self._assert_library_visible_to_everyone(session)
        await engine.dispose()

    async def test_flag_on(self, flag_on, db_engine_sync: str):
        engine = create_async_engine(db_engine_sync, echo=False)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            await self._assert_library_visible_to_everyone(session)
        await engine.dispose()


@pytest.mark.asyncio
class TestPlanRatingIsolation:
    """PLAN.md Task 5.10 — a client seat must never be able to rate (or read
    the rating of) a plan it doesn't own, even across workspaces. This goes
    through the real plan_svc.get_plan() scoping, not a hand-rolled query —
    the same function POST /client/plans/{id}/rating calls."""

    async def test_seat_cannot_rate_another_seats_plan(self, db_engine_sync: str):
        from fastapi import HTTPException

        from app.services import plan_rating as plan_rating_svc

        engine = create_async_engine(db_engine_sync, echo=False)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            ws_a = await _insert_workspace(session, f"tenant-a-{uuid.uuid4().hex[:8]}")
            ws_b = await _insert_workspace(session, f"tenant-b-{uuid.uuid4().hex[:8]}")
            seat_a = await _insert_user(session, email=f"seat-a-{uuid.uuid4().hex}@a.client.invalid", workspace_id=ws_a)
            seat_b = await _insert_user(session, email=f"seat-b-{uuid.uuid4().hex}@b.client.invalid", workspace_id=ws_b)

            plan = Plan(
                workspace_id=ws_a, user_id=seat_a.id, title="Seat A's plan",
                body_ciphertext=b"x", body_nonce=b"x", body_tag=b"x",
            )
            session.add(plan)
            await session.commit()
            await session.refresh(plan)

            # Seat B rating seat A's plan must 404, not silently rate it or
            # leak whether it exists.
            with pytest.raises(HTTPException) as exc_info:
                await plan_rating_svc.upsert_rating(
                    session, seat_b, ws_b, plan.id, score=8, comment=None
                )
            assert exc_info.value.status_code == 404

            # The owner rating their own plan succeeds and is readable back.
            rating = await plan_rating_svc.upsert_rating(
                session, seat_a, ws_a, plan.id, score=9, comment="great plan"
            )
            assert rating.score == 9

            # Seat B still can't read seat A's rating via get_rating (wrong
            # workspace_id/user_id combination returns None, not seat A's row).
            assert await plan_rating_svc.get_rating(session, seat_b, ws_b, plan.id) is None
        await engine.dispose()
