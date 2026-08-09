"""
app/models/agent_task.py

ORM model for Task 3.12 — "Cowork-style" background tasks run unattended by
Hermes Agent. A task is submitted, runs server-side via BackgroundTasks (no
Celery in demo mode — D9), and is polled for status until it reaches a
terminal state.

Prompt and result are AES-256-GCM encrypted (§7.1 — never store plaintext
user content). status stored as VARCHAR to avoid PG enum migration pain
(Gotcha #5), same convention as StudioGeneration / VaultSyncRun.

schedule_cron / next_run_at / last_run_at are placeholders for Phase 2
(recurring tasks) — unused and nullable in Phase 1.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Valid values — enforced in service layer, not as PG enum (Gotcha #5).
# "awaiting_approval" is reserved for Phase 3 (pre-run approval gate); Phase 1
# never sets it.
VALID_TASK_STATUSES = frozenset(
    {"queued", "running", "succeeded", "failed", "cancelled", "awaiting_approval"}
)
ACTIVE_TASK_STATUSES = frozenset({"queued", "running"})


class AgentTask(Base):
    __tablename__ = "agent_task"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Conversation seeded by run_chat_collect() for this task — lets the task's
    # exchange be inspected/audited the same way an ordinary chat is. Kept even
    # if the conversation is later deleted (SET NULL) since the task row is the
    # durable record.
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # First ~60 chars of the prompt, for the task-list view (not sensitive on
    # its own truncated form, but still only ever derived from the encrypted
    # prompt at write time — never re-derived from plaintext later).
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # AES-256-GCM encrypted prompt (§7.1)
    prompt_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    prompt_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    prompt_tag: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # AES-256-GCM encrypted result — nullable until the task completes.
    result_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    result_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    result_tag: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    result_key_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # AES-256-GCM encrypted live activity log / partial output, throttled-flushed
    # by the worker while status == "running" so the Tasks page can show Hermes
    # working in near-real-time. Cleared (set back to NULL) once the task
    # reaches a terminal state -- result_* / error_text become the durable
    # record at that point.
    progress_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    progress_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    progress_tag: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    progress_key_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # "queued" | "running" | "succeeded" | "failed" | "cancelled" | "awaiting_approval"
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    # True if PolicyEngine downgraded this task to the local model (Tier 3/4
    # payload) — Hermes never saw it. Surfaced to the UI as a note.
    downgrade_to_local: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tokens_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Phase 2 (scheduling) placeholders — unused, nullable in Phase 1 ---
    schedule_cron: Mapped[str | None] = mapped_column(String(100), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
