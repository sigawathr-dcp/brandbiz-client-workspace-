"""
app/models/hermes_host_job.py

ORM model for Task 3.14 — one-click native Hermes setup via a host helper.

A job is a *trigger*, not a script: the host helper's only capability is the
hardcoded install/start-Hermes routine baked into helper.ps1, and the row
carries nothing executable — just lifecycle state and an operational log the
helper reports back for the Tasks-page banner to display. No user content
lives here (so no §7.1 encryption), and the helper is instructed to never
write secrets into the log.

status stored as VARCHAR to avoid PG enum migration pain (Gotcha #5), same
convention as AgentTask / StudioGeneration / VaultSyncRun.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Valid values — enforced in service layer, not as PG enum (Gotcha #5).
VALID_HOST_JOB_STATUSES = frozenset({"queued", "running", "succeeded", "failed"})
ACTIVE_HOST_JOB_STATUSES = frozenset({"queued", "running"})

# The only job kind Phase 1 knows. The column exists so a future kind (e.g.
# "stop", "restart") is a value, not a migration.
HOST_JOB_KIND_SETUP = "setup"


class HermesHostJob(Base):
    __tablename__ = "hermes_host_job"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default=HOST_JOB_KIND_SETUP)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued", index=True)

    # ADMIN who clicked the button (audit convenience; the audit_log row is the
    # authoritative record).
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Plain operational log lines reported by the helper ("installing…",
    # "gateway started"). Capped in the service layer; never secrets.
    log_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
