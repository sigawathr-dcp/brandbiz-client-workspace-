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
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.config import settings
from app.models.agent import Agent, AgentFile
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

_logger = logging.getLogger(__name__)


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
# LINE Login entry point (0063) — replaces single-use invite links
# ---------------------------------------------------------------------------

def _line_workspace_slug(line_user_id: str) -> str:
    """Deterministic slug for a LINE-provisioned workspace.

    Derived from the LINE sub rather than random so support can answer
    "which workspace is this LINE user?" from the sub alone, without a
    query. Hashed rather than embedded verbatim because the slug appears in
    the seat's synthetic email and in admin URLs, and a raw LINE user id is
    a stable cross-service identifier we would rather not scatter.
    """
    digest = hashlib.sha256(line_user_id.encode()).hexdigest()
    return f"line-{digest[:12]}"


async def get_seat_by_line_user_id(session: AsyncSession, line_user_id: str) -> User | None:
    return (await session.execute(
        select(User).where(User.line_user_id == line_user_id)
    )).scalar_one_or_none()


async def provision_line_seat(
    session: AsyncSession,
    *,
    line_user_id: str,
    display_name: str | None,
    avatar_url: str | None,
    consent_given: bool,
) -> tuple[User, Workspace, bool]:
    """Find-or-create the seat for a verified LINE identity. Returns
    (seat, workspace, is_new).

    This is the LINE-login counterpart to redeem_invite, and the contrast is
    the whole point of 0063. redeem_invite is deliberately NOT idempotent —
    a second POST with the same token must not mint a second seat, so it
    410s. This one IS idempotent by design: a returning LINE user logs back
    into the same seat and the same finished plan. "One use" is enforced one
    level up, at POST /client/engagements (engagement.py::start_new refuses
    a second brief when settings.client_single_engagement is on), not by
    locking the person out of the door.

    Each LINE user gets their OWN workspace, so the pooled
    token_budget_limit (PolicyEngine.decide Rule 5) is per person — with a
    single shared workspace one heavy user would starve everyone else's
    budget for the rest of the month.
    """
    existing = await get_seat_by_line_user_id(session, line_user_id)
    if existing is not None:
        return await _refresh_line_seat(
            session,
            seat=existing,
            display_name=display_name,
            avatar_url=avatar_url,
            consent_given=consent_given,
        )

    try:
        return await _create_line_seat(
            session,
            line_user_id=line_user_id,
            display_name=display_name,
            avatar_url=avatar_url,
            consent_given=consent_given,
        )
    except IntegrityError:
        # uq_users_line_user_id fired: a concurrent login for the same sub
        # won the race between our SELECT above and this INSERT — a
        # double-tap on the LIFF login button is exactly two in-flight
        # requests. The other request created the seat we wanted, so adopt
        # it. This is why the constraint lives in the database and not only
        # in the check above.
        await session.rollback()
        seat = await get_seat_by_line_user_id(session, line_user_id)
        if seat is None:
            raise
        return await _refresh_line_seat(
            session,
            seat=seat,
            display_name=display_name,
            avatar_url=avatar_url,
            consent_given=consent_given,
        )


async def _refresh_line_seat(
    session: AsyncSession,
    *,
    seat: User,
    display_name: str | None,
    avatar_url: str | None,
    consent_given: bool,
) -> tuple[User, Workspace, bool]:
    """A returning LINE user. Refreshes the display fields from the current
    LINE profile (they may have renamed themselves since) and records the
    visit; never touches workspace assignment."""
    if not seat.is_active:
        # An admin deactivated this seat. Re-provisioning would hand back
        # access they deliberately removed, so stop here.
        raise HTTPException(403, "This account is no longer active")

    workspace = await get_workspace(session, seat.workspace_id) if seat.workspace_id else None
    if workspace is None or workspace.archived_at is not None:
        raise HTTPException(404, "Workspace is no longer available")

    now = datetime.now(timezone.utc)
    if display_name:
        seat.display_name = display_name
    if avatar_url:
        seat.avatar_url = avatar_url
    if consent_given and seat.consent_acknowledged_at is None:
        seat.consent_acknowledged_at = now
    seat.last_login_at = now
    await session.commit()
    await session.refresh(seat)

    await audit_svc.log(
        action="client_line_login",
        user_id=seat.id,
        resource_type="workspace",
        resource_id=workspace.id,
        details={"returning": True},
    )
    return seat, workspace, False


async def _create_line_seat(
    session: AsyncSession,
    *,
    line_user_id: str,
    display_name: str | None,
    avatar_url: str | None,
    consent_given: bool,
) -> tuple[User, Workspace, bool]:
    slug = _line_workspace_slug(line_user_id)
    now = datetime.now(timezone.utc)

    workspace = Workspace(
        name=display_name or "LINE client",
        slug=slug,
        kind="client",
        line_user_id=line_user_id,
        contact_name=display_name,
        monthly_token_limit=settings.client_default_monthly_token_limit,
        token_budget_limit=settings.client_default_workspace_budget,
    )
    session.add(workspace)
    await session.flush()  # need workspace.id for the seat below

    seat = User(
        # Same synthetic-identity trick redeem_invite uses: users.google_email
        # is NOT NULL UNIQUE and a client seat has no Google account. The
        # RFC 2606 .invalid TLD guarantees this can never collide with, or be
        # typo'd into, a real domain.
        google_email=f"client-{uuid.uuid4().hex}@{slug}.client.invalid",
        display_name=display_name or workspace.name,
        avatar_url=avatar_url,
        role="L1",
        workspace_id=workspace.id,
        line_user_id=line_user_id,
        is_active=True,
        # NOT pre-set the way redeem_invite does it. That shortcut was
        # justified by the invite link being sent by Brandbiz to a known
        # contact, which stood in for the login-time privacy notice. A
        # self-serve LINE login has no such prior contact, so consent has to
        # be collected at the door — the LIFF page ticks it and the router
        # refuses a login without it. require_consent (app/deps.py) is what
        # would otherwise bounce this seat out of every /client/* route.
        consent_acknowledged_at=now if consent_given else None,
        last_login_at=now,
    )
    session.add(seat)
    await session.flush()

    dept = await _ensure_client_department(session)
    session.add(UserDepartment(user_id=seat.id, department_id=dept.id))

    # Before the commit, so a workspace never exists without its persona.
    # The invite flow gets its agent from an admin running assign_agent()
    # after POST /admin/clients; a self-serve login has no admin in the
    # loop, and an agent-less workspace 503s the moment the funnel reaches
    # POST /client/plan/draft (services/plan.py::draft_plan).
    agent = await clone_template_agent(session, workspace_id=workspace.id, owner_id=seat.id)

    await session.commit()
    await session.refresh(seat)
    await session.refresh(workspace)

    await audit_svc.log(
        action="client_line_login",
        user_id=seat.id,
        resource_type="workspace",
        resource_id=workspace.id,
        details={
            "returning": False,
            "workspace_slug": slug,
            "agent_id": str(agent.id) if agent else None,
        },
    )
    return seat, workspace, True


# ---------------------------------------------------------------------------
# Agent assignment (Phase 3) — which Agent is "the" persona for a workspace
# ---------------------------------------------------------------------------

async def get_workspace_agent(session: AsyncSession, workspace_id: uuid.UUID) -> Agent | None:
    """Return the client-facing Agent scoped to this workspace (the น้อง brandbiz
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


async def clone_template_agent(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> Agent | None:
    """Copy settings.client_template_agent_id into `workspace_id` as its own
    Agent row, and return it (None if no template is configured or the id
    does not resolve to a published agent).

    A *copy*, not assign_agent(): agents.workspace_id is single-valued, so
    handing the template itself to a new workspace would strip it from the
    one it already serves. Each workspace owning its row also means an admin
    can tune one client's persona without touching every other client's.

    agent_files rows are copied too — the น้อง brandbiz template carries the case
    library (21 files at time of writing) and a clone without them answers
    from nothing. Files themselves are not duplicated; both agents point at
    the same files.id rows, which is safe because agent_files is a pure
    association and the RAG path re-checks file visibility per query
    (app/tools/rag_search.py).

    Does NOT commit — the caller is mid-transaction building the workspace.
    """
    template_id = (settings.client_template_agent_id or "").strip()
    if not template_id:
        _logger.warning(
            "clone_template_agent: CLIENT_TEMPLATE_AGENT_ID unset — workspace %s "
            "comes up with no agent and cannot draft a plan until an admin assigns one",
            workspace_id,
        )
        return None
    try:
        parsed = uuid.UUID(template_id)
    except ValueError:
        _logger.warning(
            "clone_template_agent: CLIENT_TEMPLATE_AGENT_ID is not a uuid — ignoring"
        )
        return None

    template = (await session.execute(
        select(Agent).where(Agent.id == parsed, Agent.status == "published")
    )).scalar_one_or_none()
    if template is None:
        _logger.warning(
            "clone_template_agent: CLIENT_TEMPLATE_AGENT_ID %s is not a published agent", parsed
        )
        return None

    clone = Agent(
        # The seat, not the template's author: a client workspace's agent is
        # owned inside that workspace, so deleting the internal admin who
        # authored the template does not CASCADE away every client's persona.
        user_id=owner_id,
        name=template.name,
        description=template.description,
        instructions=template.instructions,
        provider=template.provider,
        model=template.model,
        capabilities=dict(template.capabilities) if template.capabilities else None,
        creativity_level=template.creativity_level,
        # Both forced, for the same reason assign_agent() forces them: a
        # "personal" or "draft" clone is invisible to the seat it was made
        # for (agent.py::_accessible_filter, get_workspace_agent()).
        visibility="public",
        status="published",
        workspace_id=workspace_id,
        avatar_color=template.avatar_color,
        category=template.category,
    )
    session.add(clone)
    await session.flush()

    file_ids = (await session.execute(
        select(AgentFile.file_id).where(AgentFile.agent_id == template.id)
    )).scalars().all()
    for file_id in file_ids:
        session.add(AgentFile(agent_id=clone.id, file_id=file_id))
    await session.flush()

    return clone


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
