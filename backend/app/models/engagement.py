"""
app/models/engagement.py

ORM models for the client-workspace journey backbone (DB redesign, PLAN.md
Phase 5 follow-up — see the "Client Workspace — Database Redesign" plan).

Before this module existed, the 4-step funnel (Interview -> Market scan ->
Case match -> Plan & budget) had NO row anywhere representing "one client's
run through the steps" — the four step tables (client_profiles/research_runs/
case_matches/plans) were glued together only by repeating
(workspace_id, user_id, conversation_id) on each one, and the journey itself
was reconstructed from scratch in the browser on every load
(frontend-chat/components/client/journey.ts::deriveJourney). Consequences:
no server-side journey state, three different status vocabularies for the
same concept, and a zero-match case run being distinguished from "never
ran" by querying audit_log as if it were application state
(app/routers/client.py's old _bootstrap_research_and_cases).

Engagement is that missing row: one per client's run through the funnel. A
seat may run the funnel more than once (a returning client can start a new
brief) — see the partial unique index below — so `seq` numbers repeats and
only one may be `status='active'` at a time.

EngagementStep gives all 4 steps the SAME 5-state lifecycle
(idle -> running -> done/failed), replacing:
  - research_runs.status (pending|done|failed, with 'pending' unreachable —
    there is no background worker, so a stuck run can never resolve)
  - the API/journey vocabulary (idle|pending|done|error)
  - step 3, which previously had no status column at all
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Stored as VARCHAR, not a PG enum (house convention — see Gotcha #5 in
# PLAN.md: new status/kind columns are VARCHAR + a module-level frozenset
# enforced in the service layer).
VALID_ENGAGEMENT_STATUSES: frozenset[str] = frozenset({"active", "completed", "abandoned"})
VALID_STEP_STATUSES: frozenset[str] = frozenset({"idle", "running", "done", "failed", "skipped"})

# The 4 chapters, in order — the frontend's CHAPTER_ORDER
# (frontend-chat/components/client/journey.ts) uses the exact same ids, so
# nothing needs translating at the API boundary.
STEP_KEYS: tuple[str, ...] = ("interview", "market", "cases", "plan")


class Engagement(Base):
    """One client's run through the 4-step funnel. `seq` (1, 2, 3, ...)
    lets a seat start a fresh brief after completing (or abandoning) an
    earlier one — the old client_profiles table had
    UNIQUE(workspace_id, user_id), capping a seat at exactly one intake
    forever; this replaces that with "one ACTIVE engagement per seat,
    unlimited archived ones" (see the partial unique index below)."""

    __tablename__ = "engagements"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", "seq", name="uq_engagements_workspace_user_seq"),
        # Partial unique index: at most one ACTIVE engagement per seat, but
        # unlimited completed/abandoned ones — replaces client_profiles'
        # old UNIQUE(workspace_id, user_id), which capped a seat at exactly
        # one intake forever.
        Index(
            "uq_engagements_one_active_per_seat",
            "workspace_id", "user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Which intake_scripts row this engagement's questions/answers are
    # pinned to (app/models/intake.py) — reordering or republishing the
    # script never reinterprets an existing engagement's stored answers.
    intake_script_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intake_scripts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # Replaces the frontend's `bb:activePlan:${workspaceId}` localStorage
    # key — which plan a PUT /client/plans/{id} revision targets is now
    # server state, not a per-device browser preference.
    active_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EngagementStep(Base):
    """One row per chapter (step_no 1..4) per engagement — created all at
    once (all `idle`) when the engagement is created. Every step transition
    goes through app/services/engagement.py::mark_step; nothing else writes
    `status`."""

    __tablename__ = "engagement_steps"
    __table_args__ = (
        UniqueConstraint("engagement_id", "step_no", name="uq_engagement_steps_engagement_step"),
        CheckConstraint("step_no BETWEEN 1 AND 4", name="ck_engagement_steps_step_no_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    step_key: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="idle")
    # For step 1 (interview): how many of the script's questions have been
    # answered / the script's total question count — what
    # client_profiles.step / total_steps() tracked before this redesign.
    progress_current: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    progress_total: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
