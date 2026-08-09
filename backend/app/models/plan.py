"""
app/models/plan.py

ORM models for Plans — the 4-part draft plan promoted out of chat into a
standalone, versioned document (Phase 5 §4, D21/D22).

Two things force this to exist outside `messages.content_*`:
  1. D14 drops message content after 30 days; a plan living only inside a
     chat message would vanish with it.
  2. §7.1's "never write plaintext message content to the DB" is about chat
     turns — a saved Plan is a deliverable the client explicitly promoted
     ("Save as a plan"), not an ordinary message, but its body is still
     client-supplied/business-sensitive content, so it gets the same
     AES-256-GCM treatment as messages.content_* by the same reasoning.

`budget` and `provenance` are plain JSONB, not encrypted: they're computed
structured output (rate-card line items, case/web references), not
free-text client content — same treatment as research_runs.findings.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

VALID_PLAN_STATUSES: frozenset[str] = frozenset({"draft", "expert_review", "final"})


class Plan(Base):
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
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    # "draft" | "expert_review" | "final" — the design's "draft · awaiting
    # expert review" badge is a liability control, not decoration; keep it
    # in every surface that renders a Plan.
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="draft")
    body_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    body_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    body_tag: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    # {"lines": [...], "needs_expert": [...], "subtotal": .., "contingency": .., "total": .., "currency": "THB"}
    budget: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {"rate_card": [...], "cases": [...], "research_run_id": "..."}
    provenance: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # SHA-256 hex of the raw share token (Phase 6) — mirrors api_keys/client_invites.
    share_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PlanVersion(Base):
    """Append-only snapshot taken each time a Plan's body/budget changes —
    backs the design's Versions panel."""

    __tablename__ = "plan_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    body_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    body_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    body_tag: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    budget: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


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
