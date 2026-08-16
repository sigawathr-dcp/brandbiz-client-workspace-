"""
app/models/client_intake.py

ORM models for steps 2 and 3 of the client-workspace funnel — market
research and case matching. Module kept at its original path/name for
import-site stability, even though its third original resident
(ClientProfile, step 1) moved to app/models/intake.py in the DB redesign
(see the "Client Workspace — Database Redesign" plan for the full
rationale).

Both run-record tables (ResearchRun, CaseMatchExecution) now hang off
app.models.engagement.EngagementStep rather than repeating
(workspace_id, user_id, conversation_id) — that triple used to be a
de-facto foreign key to a table (Engagement) that didn't exist.

Changes from the pre-redesign shape:
  - ResearchRun.query is now encrypted (was plaintext `Text` — a plaintext
    copy of answers that are encrypted two tables over in
    client_profiles.fields_ciphertext).
  - ResearchRun.findings/citations (JSONB, fake structure — findings were
    just `full_text.split("\n")`, and the promised `citation_indexes`/
    `title` keys were never written) become real tables: ResearchFinding,
    ResearchCitation, ResearchFindingCitation (a real many-to-many join,
    not an integer index living inside a JSONB blob).
  - CaseMatch drops workspace_id/user_id/conversation_id/filename (all
    reachable via case_match_run_id -> engagement_step -> engagement, or
    via case_study_id -> case_studies -> files) and gains
    case_match_run_id + case_study_id + rank. Rows are now append-only per
    run instead of deleted and re-inserted on every POST /client/cases, so
    the case-match eval harness can reconstruct what a real client
    actually saw.
  - CaseStudy is new: the case-library catalog, parsed ONCE at ingestion
    time via app/services/case_card.py::parse_case_card() (re-parsed only
    when content_sha256 changes) instead of on every request.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

VALID_RUN_STATUSES: frozenset[str] = frozenset({"idle", "running", "done", "failed"})


class ResearchRun(Base):
    """One market-research scan (routed through PolicyEngine at the
    Perplexity model code — see app/routers/client.py::run_research)."""

    __tablename__ = "research_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    engagement_step_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagement_steps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The composed research query embeds the client's (encrypted) profile
    # answers verbatim — §7.1 applies to it exactly as it does to the
    # answers themselves.
    query_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    query_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    query_tag: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="running")
    tokens_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchFinding(Base):
    __tablename__ = "research_findings"
    __table_args__ = (
        UniqueConstraint("research_run_id", "ordinal", name="uq_research_findings_run_ordinal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)


class ResearchCitation(Base):
    __tablename__ = "research_citations"
    __table_args__ = (
        UniqueConstraint("research_run_id", "ordinal", name="uq_research_citations_run_ordinal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ResearchFindingCitation(Base):
    """A real many-to-many join between findings and the citations that
    support them — replaces the never-written `citation_indexes` key the
    old findings JSONB docstring promised but the writer never produced."""

    __tablename__ = "research_finding_citations"

    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_findings.id", ondelete="CASCADE"),
        primary_key=True,
    )
    citation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_citations.id", ondelete="CASCADE"),
        primary_key=True,
    )


class CaseStudy(Base):
    """The case-library catalog — one row per case-study file, parsed ONCE
    (services/case_card.py::parse_case_card()) instead of on every
    /client/cases or /client/bootstrap request. Re-parsed only when
    content_sha256 changes (a re-uploaded/edited file)."""

    __tablename__ = "case_studies"
    __table_args__ = (
        UniqueConstraint("file_id", name="uq_case_studies_file_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parser_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    parsed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CaseMatchExecution(Base):
    """One run of case-library retrieval against a client's profile. A run
    row exists even at zero matches, so bootstrap can tell "never ran"
    from "ran, found nothing" without the old audit_log probe
    (app/routers/client.py's former _bootstrap_research_and_cases, which
    queried audit_log WHERE action='case_matched' — and wasn't even scoped
    to the current conversation)."""

    __tablename__ = "case_match_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    engagement_step_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagement_steps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    query_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    query_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    query_tag: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    top_k: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="running")
    match_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CaseMatch(Base):
    """One case-study result within a CaseMatchExecution — append-only per
    run (the old table deleted-and-reinserted this seat's rows on every
    POST /client/cases, destroying match history the eval harness could
    otherwise use to see what a real client actually saw)."""

    __tablename__ = "case_matches"
    __table_args__ = (
        UniqueConstraint("case_match_run_id", "case_study_id", name="uq_case_matches_run_case"),
        CheckConstraint("rank >= 0", name="ck_case_matches_rank_nonneg"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_match_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("case_match_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("case_studies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rank: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # Similarity score, 0..1 (1 - cosine_distance) — see
    # app/services/case_match.py::to_match_score. Not yet calibrated
    # against a golden set (PLAN.md Task 5.9's eval harness tracks that
    # separately); this column's meaning is unchanged by this redesign.
    score: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
