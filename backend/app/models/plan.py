"""
app/models/plan.py

ORM models for Plans — the 4-part draft plan promoted out of chat into a
standalone, versioned document (Phase 5 §4, D21/D22; restructured by the
"Client Workspace — Database Redesign" plan).

Two things force this to exist outside `messages.content_*`:
  1. D14 drops message content after 30 days; a plan living only inside a
     chat message would vanish with it.
  2. §7.1's "never write plaintext message content to the DB" is about chat
     turns — a saved Plan is a deliverable the client explicitly promoted
     ("Save as a plan"), not an ordinary message, but its body is still
     client-supplied/business-sensitive content, so it gets the same
     AES-256-GCM treatment as messages.content_* by the same reasoning.

Redesign: `plans` used to be BOTH the container and the current version —
it carried title/body_*/budget/provenance/version directly, and
plan_versions duplicated most of the same columns (title/provenance were
even bolted on later, nullable, by migration 0049). Now `plans` is a head
row only (id, status, current_version_id, share token); every version's
full content lives in PlanVersion, with UNIQUE(plan_id, version_no)
replacing the old "no unique constraint, compensate with
ORDER BY created_at DESC LIMIT 1" workaround.

`budget`/`provenance` JSONB are replaced by PlanBudgetLine/PlanSource rows:
money as NUMERIC (was a JSON string), a real FK to rate_card_items (the
JSONB had none), and `needs_expert` as a DB invariant
(rate_card_item_id IS NULL) rather than a parallel JSON key that could
silently drift from `lines`.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

VALID_PLAN_STATUSES: frozenset[str] = frozenset({"draft", "expert_review", "final"})
VALID_SOURCE_KINDS: frozenset[str] = frozenset({"rate_card", "case_study", "research_citation"})


class Plan(Base):
    """Head row only — title/body/budget/provenance all live on the
    current PlanVersion (`current_version_id`). Still keyed by
    (workspace_id, user_id) directly (not only via engagement_id) so
    existing ownership checks in app/services/plan.py stay a single-table
    lookup."""

    __tablename__ = "plans"

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
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plan_versions.id", ondelete="SET NULL", use_alter=True, name="fk_plans_current_version"),
        nullable=True,
    )
    # "draft" | "expert_review" | "final" — the design's "draft · awaiting
    # expert review" badge is a liability control, not decoration; keep it
    # in every surface that renders a Plan. Never touched by a revision
    # (app/services/plan.py::revise_plan).
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="draft")
    # SHA-256 hex of the raw share token (Phase 6) — mirrors api_keys/client_invites.
    share_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PlanVersion(Base):
    """Append-only — every field a rendered plan needs, snapshotted at
    save/revise time. `title` is NOT NULL (the pre-redesign column, added
    late by migration 0049, was nullable and every reader needed fallback
    logic); `unit_price`/amounts on PlanBudgetLine are frozen at draft
    time, so a later rate-card change never silently rewrites a plan a
    client already saw or a strategist already signed off on."""

    __tablename__ = "plan_versions"
    __table_args__ = (
        UniqueConstraint("plan_id", "version_no", name="uq_plan_versions_plan_version_no"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    body_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    body_tag: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    subtotal_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    contingency_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    contingency_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PlanBudgetLine(Base):
    """Replaces plans.budget's JSONB `lines`/`needs_expert` arrays.
    `needs_expert = TRUE` if and only if `rate_card_item_id IS NULL` — the
    anti-hallucination guard (the model may only emit a rate-card CODE,
    never a price; app/services/rate_card.py::price() looks the amount up)
    is now a DB invariant instead of a parallel JSON flag that could drift
    from the row it describes."""

    __tablename__ = "plan_budget_lines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plan_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plan_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    rate_card_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rate_card_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    section: Mapped[str | None] = mapped_column(String(16), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    qty: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, server_default="1")
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    needs_expert: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class PlanSource(Base):
    """Replaces plans.provenance JSONB, whose own docstring (`rate_card`/
    `cases`) never matched what app/services/plan.py::draft_plan() actually
    wrote (`rate_card_codes`/`case_files`/`research_sources`). One row per
    cited source, `label_snapshot` frozen at draft time so a later rename
    (a rate-card label edit, a case-study re-parse) never rewrites a
    plan's provenance rail after the fact."""

    __tablename__ = "plan_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plan_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plan_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)  # rate_card | case_study | research_citation
    ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    label_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_snapshot: Mapped[float | None] = mapped_column(nullable=True)


class PlanDraft(Base):
    """Persists POST /client/plan/draft's ephemeral output — previously an
    expensive LLM call whose result existed only in browser memory and was
    lost on reload. `budget_json` stays JSONB (a draft is disposable
    scratch space, not the durable artifact PlanBudgetLine models);
    discarded (not deleted — kept for the eval/analytics trail) once
    POST/PUT /client/plans turns it into a real PlanVersion."""

    __tablename__ = "plan_drafts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    engagement_step_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagement_steps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    body_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    body_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    body_tag: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    budget_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    discarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PlanRating(Base):
    """A client's NPS-style rating of a saved plan (PLAN.md Task 5.10) — so
    the expert on the handoff sees the client's reaction before they call
    (app/routers/admin_leads.py's LeadOut.nps_score/nps_comment).

    One row per (plan_id, user_id), upserted on re-rate rather than
    append-only: the reader that matters (the leads inbox) wants a single
    current value, not a history to reconcile. The submit itself is still
    audited (action="plan_rated", details={"score": n}) on every call, so
    the change trail exists without a second table.

    `comment` is a deliberate exception to §7.1's "never write plaintext
    message content to the DB": it's client feedback ABOUT a plan, not
    conversational content, and the strategist needs to read it inline on
    the leads inbox before the call — see docs/adr/ for the reasoning."""

    __tablename__ = "plan_ratings"
    __table_args__ = (
        UniqueConstraint("plan_id", "user_id", name="uq_plan_ratings_plan_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
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
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..10, enforced at the API layer
    comment: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
