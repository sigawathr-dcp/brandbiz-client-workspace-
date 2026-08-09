"""
app/models/lead.py

ORM model for expert-handoff leads (Phase 5 §5, D21/D22) — the CTA at the
bottom of a saved plan ("Talk to an expert"). This is the commercial point
of the whole funnel (per DSME_ai.md: "the only real code" in the demo
track). The lead row is the durable record; app/services/n8n_client.py's
outbound POST is best-effort — n8n_response/n8n_error let a failed webhook
be retried without losing the lead.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

VALID_LEAD_STATUSES: frozenset[str] = frozenset({"new", "assigned", "done"})


class Lead(Base):
    __tablename__ = "leads"

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
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone_or_line: Mapped[str | None] = mapped_column(String(64), nullable=True)
    best_time: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="new")
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    n8n_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    n8n_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
