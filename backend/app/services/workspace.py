"""
app/services/workspace.py

Tenant isolation helpers for Client Workspaces (D21/D22, Phase 5; amended
by D23).

Two tenant classes share this one gateway instance:
  - internal staff: users.workspace_id IS NULL — sees only internal-shared
    rows (files.scope="org", skills/agents visibility="public" with
    workspace_id IS NULL too). Unchanged from pre-D21/D22 behavior.
  - client seats: users.workspace_id = <workspace> — sees only rows scoped
    to that same workspace, never another workspace's. By default (D21/D22)
    that means never internal rows either. D23
    (settings.client_internal_access_enabled) widens this one step: a
    client seat also reads the shared internal pool (workspace_id IS NULL),
    same as staff — see _tenant_match() below. Cross-workspace isolation
    between two client seats is unaffected either way, and is the one
    invariant D23 does not relax; see is_client_seat() and its write-path
    callers for how client seats' own writes stay private under D23.

workspace_visibility_filter() is applied ON TOP OF the existing scope/
visibility predicate in app/tools/rag_search.py, app/services/skill.py, and
app/services/agent.py — it narrows the "shared" branch, it does not replace
personal/private ownership checks or touch the routers/services that only
ever look at a user's own rows.

Provisioning (workspaces, invites, redemption — Phase 2) lives in this
module too as it grows.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.config import settings
from app.models.agent import Agent
from app.models.client_invite import ClientInvite
from app.models.department import Department, UserDepartment
from app.models.user import User
from app.models.workspace import VALID_WORKSPACE_KINDS, Workspace
from app.services import audit as audit_svc

# Every client seat joins this department on redemption (D19: department
# permissions are additive over role permissions). Client seats stay at
# role=L1 — this is how they reach Perplexity for /client/research without
# touching role_model_permissions or the meaning of L1 for employees. An
# admin grants the actual model(s) once via the existing
# GET/PUT /admin/permissions/department UI — this constant only ensures the
# department itself, and every seat's membership in it, always exist.
CLIENT_DEPARTMENT_CODE = "client-workspaces"


def is_client_seat(user: User) -> bool:
    """True for a redeemed client-workspace seat (users.workspace_id set).

    D23: once client seats can reach the internal-app write paths
    (POST /files, /skills, /agents), this is used to keep their writes
    private to the seat — every booth attendee shares one workspace
    (redeem_invite mints into invite.workspace_id), so workspace-grained
    stamping alone would let attendee A read attendee B's org-scope upload
    or public skill/agent. See app/routers/files.py, app/services/skill.py
    ::create_skill, app/services/agent.py::create_agent.
    """
    return user.workspace_id is not None


def _tenant_match(column, workspace_ref) -> ColumnElement[bool]:
    """The shared predicate behind both workspace_visibility_filter()
    overloads below.

    Default (D21/D22): `column IS NOT DISTINCT FROM workspace_ref` — NULL
    matches NULL, so an internal user (workspace_ref IS NULL) matches an
    internal-shared row, and a client seat matches only its own workspace's
    rows. Plain `==` would make NULL = NULL evaluate to NULL/false and
    silently hide every internal-shared row from internal users.

    D23 (settings.client_internal_access_enabled): widens this to "the
    shared internal pool (column IS NULL) is readable by everyone; a
    workspace's own rows stay readable only in-workspace" — `column IS
    NULL OR column IS NOT DISTINCT FROM workspace_ref`. For an internal
    user both disjuncts reduce to the same `column IS NULL` clause, so
    this is a no-op for staff either way. For a client seat it adds read
    access to the shared pool without touching cross-workspace isolation:
    a row belonging to a *different* workspace still matches neither
    disjunct.
    """
    own = column.is_not_distinct_from(workspace_ref)
    if settings.client_internal_access_enabled:
        return or_(column.is_(None), own)
    return own


def workspace_visibility_filter(user: User, model) -> ColumnElement[bool]:
    """WHERE clause: does `model.workspace_id` match `user`'s tenant?

    `model` must be an ORM class with a nullable `workspace_id` column
    (File, Skill, Agent). See _tenant_match() for the exact predicate and
    how it changes under D23.

    Use this overload when the caller already has a loaded `User` (e.g.
    app/tools/rag_search.py::_scope_filter, which takes `user: User`).
    """
    return _tenant_match(model.workspace_id, user.workspace_id)


def workspace_visibility_filter_by_user_id(user_id: uuid.UUID, model) -> ColumnElement[bool]:
    """Same predicate as workspace_visibility_filter(), for call sites that
    only carry a bare user_id (app/services/skill.py and
    app/services/agent.py's `_accessible_filter(user_id)` helpers) — a
    correlated scalar subquery avoids widening those functions' signatures
    just for this.
    """
    user_workspace = select(User.workspace_id).where(User.id == user_id).scalar_subquery()
    return _tenant_match(model.workspace_id, user_workspace)


def workspace_visibility_filter_by_workspace_id(
    workspace_id: uuid.UUID | None, model
) -> ColumnElement[bool]:
    """Same predicate as workspace_visibility_filter(), keyed by an explicit
    *effective* workspace id rather than `user.workspace_id`.

    Exists for /client/* preview reads (app/deps.py::require_client_context,
    ClientContext.workspace_id): an internal staff member previewing the
    demo funnel has `user.workspace_id IS NULL`, but the funnel should read
    against the seeded demo workspace, not the staff member's own (absent)
    tenant. `workspace_id` here is that effective value — never written back
    onto `user.workspace_id`, so quota/PolicyEngine and every other caller
    that keys off the real column are unaffected. For a real client seat,
    the caller passes `ctx.workspace_id`, which already equals
    `user.workspace_id`, so this is a no-op vs. the by-user overload.
    """
    return _tenant_match(model.workspace_id, workspace_id)


# ---------------------------------------------------------------------------
# Provisioning (Phase 2) — workspaces, invites, redemption
# ---------------------------------------------------------------------------

_INVITE_TOKEN_PREFIX = "try_"


def _generate_invite_token() -> tuple[str, str]:
    """Return (raw_token, token_hash) — mirrors app/models/api_key.py's
    generate_key(): the raw token is shown/linked exactly once by the
    caller, only the SHA-256 hash is persisted."""
    raw = _INVITE_TOKEN_PREFIX + secrets.token_urlsafe(24)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, token_hash


async def create_workspace(
    session: AsyncSession,
    *,
    name: str,
    slug: str,
    kind: str = "demo",
    monthly_token_limit: int | None = None,
    token_budget_limit: int | None = None,
    contact_name: str | None = None,
    contact_email: str | None = None,
    contact_phone: str | None = None,
) -> Workspace:
    if kind not in VALID_WORKSPACE_KINDS:
        raise HTTPException(400, f"kind must be one of {sorted(VALID_WORKSPACE_KINDS)}")
    # D23: an unconfigured workspace used to mean uncapped (both defaulted
    # to None) — PolicyEngine's Rule 5 pooled-budget check is a no-op when
    # token_budget_limit IS NULL. Fall back to a finite default so
    # POST /admin/clients callers who don't think about caps still get one;
    # an admin who genuinely wants uncapped can still pass an explicit huge
    # number.
    ws = Workspace(
        name=name,
        slug=slug,
        kind=kind,
        monthly_token_limit=(
            monthly_token_limit if monthly_token_limit is not None
            else settings.client_default_monthly_token_limit
        ),
        token_budget_limit=(
            token_budget_limit if token_budget_limit is not None
            else settings.client_default_workspace_budget
        ),
        contact_name=contact_name,
        contact_email=contact_email,
        contact_phone=contact_phone,
    )
    session.add(ws)
    await session.commit()
    await session.refresh(ws)
    return ws


async def list_workspaces(session: AsyncSession) -> list[Workspace]:
    result = await session.execute(select(Workspace).order_by(Workspace.created_at.desc()))
    return list(result.scalars().all())


async def get_workspace(session: AsyncSession, workspace_id: uuid.UUID) -> Workspace | None:
    return (await session.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )).scalar_one_or_none()


async def get_preview_workspace(session: AsyncSession) -> Workspace | None:
    """The workspace internal staff land in via app/deps.py::
    require_client_context when they have no workspace of their own — the
    oldest non-archived "demo"-kind workspace, i.e. the one
    backend/scripts/seed_client_demo.py creates. Not per-user configurable;
    if a different preview target is needed, archive the old one and seed
    a new one."""
    return (await session.execute(
        select(Workspace)
        .where(Workspace.kind == "demo", Workspace.archived_at.is_(None))
        .order_by(Workspace.created_at.asc())
    )).scalars().first()


async def create_invite(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    created_by: uuid.UUID,
    expires_in_hours: int = 72,
    line_user_id: str | None = None,
    contact_name: str | None = None,
) -> tuple[ClientInvite, str]:
    """Mint an invite. Returns (row, raw_token) — the raw token is the
    caller's one and only chance to see it; it goes into the /try/<token>
    link (Phase 2) and is never retrievable again.

    This is the LINE integration seam: today an admin mints invites by hand
    (app/routers/client_admin.py); later, n8n will call this same function
    (via the admin router, using a service API key) after receiving a LINE
    profile, passing line_user_id/contact_name through.
    """
    workspace = await get_workspace(session, workspace_id)
    if workspace is None or workspace.archived_at is not None:
        raise HTTPException(404, "Workspace not found")

    raw, token_hash = _generate_invite_token()
    invite = ClientInvite(
        workspace_id=workspace_id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_in_hours),
        created_by=created_by,
        line_user_id=line_user_id,
        contact_name=contact_name,
    )
    session.add(invite)
    await session.commit()
    await session.refresh(invite)

    await audit_svc.log(
        action="client_invited",
        user_id=created_by,
        resource_type="workspace",
        resource_id=workspace_id,
        details={"invite_id": str(invite.id), "expires_at": invite.expires_at.isoformat()},
    )
    return invite, raw


async def list_invites(session: AsyncSession, workspace_id: uuid.UUID) -> list[ClientInvite]:
    result = await session.execute(
        select(ClientInvite)
        .where(ClientInvite.workspace_id == workspace_id)
        .order_by(ClientInvite.created_at.desc())
    )
    return list(result.scalars().all())


async def _ensure_client_department(session: AsyncSession) -> Department:
    dept = (await session.execute(
        select(Department).where(Department.code == CLIENT_DEPARTMENT_CODE)
    )).scalar_one_or_none()
    if dept is not None:
        return dept
    dept = Department(code=CLIENT_DEPARTMENT_CODE, name="Client Workspaces")
    session.add(dept)
    await session.flush()
    return dept


async def redeem_invite(session: AsyncSession, *, raw_token: str) -> tuple[User, Workspace]:
    """Validate a raw invite token, create the seat User, mark the invite
    spent, and return (seat, workspace). The caller (app/routers/
    client_public.py) then issues the JWT cookie via the same
    _create_jwt/_set_jwt_cookie helpers auth.py uses for password login —
    a redeemed invite IS the login, there is no separate password step.

    Each invite redeems exactly once (redeemed_at gates re-use) — this is
    deliberately not idempotent-on-retry: a second POST with the same token
    must not silently mint a second seat.
    """
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    invite = (await session.execute(
        select(ClientInvite).where(ClientInvite.token_hash == token_hash)
    )).scalar_one_or_none()
    if invite is None:
        raise HTTPException(404, "Invalid invite link")
    if invite.redeemed_at is not None:
        raise HTTPException(410, "This invite link has already been used")
    if invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(410, "This invite link has expired")

    workspace = await get_workspace(session, invite.workspace_id)
    if workspace is None or workspace.archived_at is not None:
        raise HTTPException(404, "Workspace is no longer available")

    # Synthetic unique identity — client seats never have a real Google
    # account (users.google_email is NOT NULL UNIQUE). ".client.invalid"
    # uses the RFC 2606 reserved .invalid TLD so this can never collide
    # with, or be typo'd into, a real domain.
    #
    # consent_acknowledged_at is pre-set: the invite link itself — sent by
    # Brandbiz to a known contact — stands in for the login-time privacy
    # notice an internal employee sees via ConsentGate. See
    # require_client_context in app/deps.py, which still composes with
    # require_consent.
    now = datetime.now(timezone.utc)
    seat = User(
        google_email=f"client-{uuid.uuid4().hex}@{workspace.slug}.client.invalid",
        display_name=invite.contact_name or workspace.contact_name or workspace.name,
        role="L1",
        workspace_id=workspace.id,
        is_active=True,
        consent_acknowledged_at=now,
    )
    session.add(seat)
    await session.flush()  # need seat.id before writing it onto the invite row

    dept = await _ensure_client_department(session)
    session.add(UserDepartment(user_id=seat.id, department_id=dept.id))

    invite.redeemed_at = now
    invite.redeemed_user_id = seat.id
    await session.commit()
    await session.refresh(seat)

    await audit_svc.log(
        action="client_redeemed",
        user_id=seat.id,
        resource_type="workspace",
        resource_id=workspace.id,
        details={"invite_id": str(invite.id)},
    )
    return seat, workspace


# ---------------------------------------------------------------------------
# Agent assignment (Phase 3) — which Agent is "the" persona for a workspace
# ---------------------------------------------------------------------------

async def get_workspace_agent(session: AsyncSession, workspace_id: uuid.UUID) -> Agent | None:
    """Return the client-facing Agent scoped to this workspace (the น้องภูมิ
    persona) — the oldest published Agent row with
    agent.workspace_id == workspace_id. Deliberately not a new UI concept:
    an admin authors this Agent through the existing internal Agent form,
    then assign_agent() below scopes it to a workspace — no separate
    "client agent" primitive exists. status=="published" is required so a
    draft agent an admin is mid-editing never becomes reachable by a client
    seat ahead of an already-live one."""
    return (await session.execute(
        select(Agent)
        .where(Agent.workspace_id == workspace_id, Agent.status == "published")
        .order_by(Agent.created_at.asc())
    )).scalars().first()


async def assign_agent(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    admin_id: uuid.UUID,
) -> Agent:
    """Scope an existing (internally-authored) Agent to a client workspace.

    Forces visibility="public" — a workspace-scoped agent that stayed
    "personal" would be invisible to every client seat via
    app/services/agent.py::_accessible_filter's public branch, the only
    branch workspace_visibility_filter is applied to.
    """
    agent = (await session.execute(
        select(Agent).where(Agent.id == agent_id)
    )).scalar_one_or_none()
    if agent is None:
        raise HTTPException(404, "Agent not found")

    agent.workspace_id = workspace_id
    agent.visibility = "public"
    await session.commit()
    await session.refresh(agent)

    await audit_svc.log(
        action="agent_updated",
        user_id=admin_id,
        resource_type="workspace",
        resource_id=workspace_id,
        details={"agent_id": str(agent_id), "fields": ["workspace_id", "visibility"]},
    )
    return agent
