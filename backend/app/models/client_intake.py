"""
app/models/client_intake.py

ORM models for the client-workspace intake pipeline (Phase 5 §3, D21/D22):
ClientProfile (the 8-question intake answers), ResearchRun (the Perplexity
market scan), CaseMatch (case-library retrieval results). See
app/services/client_intake.py for the deterministic question script and
app/routers/client.py for the endpoints that populate these.

Scoped by (workspace_id, user_id), not workspace_id alone: a single
workspace can have more than one redeemed seat (e.g. an event "demo"
workspace with many attendee invites all pointing at it), and each seat
must get its own independent intake/research/cases — never another
attendee's. Conversation/Message rows are already seat-scoped via
Conversation.user_id (unchanged, pre-existing behavior); these three tables
need the same treatment since they're new.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ClientProfile(Base):
    """The structured intake answers for one client conversation — a real
    field, not parsed-out-of-chat-text (see DSME_ai.md's gap analysis, which
    called this out as a gap the demo needed to close)."""

    __tablename__ = "client_profiles"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_client_profiles_workspace_user"),
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
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Index into INTAKE_SCRIPT of the next unanswered question; == len(script)
    # once complete.
    step: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Answers, JSON-encoded then AES-256-GCM encrypted as one blob (business
    # answers are user-supplied content — §7.1 in spirit, mirrors
    # messages.content_*). See app/crypto.py.
    fields_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    fields_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    fields_tag: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ResearchRun(Base):
    """One market-research scan (routed through PolicyEngine at the
    Perplexity model code — see app/routers/client.py::run_research).
    Findings/citations are structured output about the external market, not
    client-supplied content, so they're stored as plain JSONB (same
    treatment as plans.provenance in Phase 4) rather than encrypted."""

    __tablename__ = "research_runs"

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
    query: Mapped[str] = mapped_column(Text, nullable=False)
    # [{"text": "...", "citation_indexes": [1,2]}, ...]
    findings: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # [{"index": 1, "title": "...", "source": "bangkokpost.com"}, ...]
    citations: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CaseMatch(Base):
    """One case-library retrieval result — a persisted snapshot of a
    rag_search.RetrievedChunk scored against the client's profile, so the
    Cases tab has stable data to show without re-running retrieval."""

    __tablename__ = "case_matches"

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
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    # Similarity score, 0..1 (1 - cosine_distance) — see app/routers/client.py.
    score: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
