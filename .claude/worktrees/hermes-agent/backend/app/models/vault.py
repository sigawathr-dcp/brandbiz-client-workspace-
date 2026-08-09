"""ORM models for the admin-configurable Obsidian vault connection.

Tables ``vault_connection`` and ``vault_sync_run`` are created by Alembic
0028_vault_connection.

Security note (deviation from PLAN.md D13, explicitly user-approved):
D13 locks secrets to env vars for v1. ``vault_connection.git_url`` /
``branch`` /``bot_email`` /``templates_dirname`` are plaintext admin-editable
config, but the access token is the one secret this project stores in the
app database — it is AES-256-GCM encrypted at rest via ``app/crypto.py``,
using the same 4-column (ciphertext/nonce/tag/key_version) pattern already
used for message content (see ``models/message.py``). The token is never
returned by any API response; see ``app/services/vault_connection.py`` and
``app/routers/vault.py``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, LargeBinary, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Status values a vault_sync_run row can hold. Stored as VARCHAR (not a PG
# enum) — mirrors files.scope / files.source (see VALID_SCOPES in
# app/models/file.py, "Gotcha #5 — avoid PG enum migration pain").
VALID_SYNC_STATUSES: frozenset[str] = frozenset(
    {"cloning", "pulling", "reconciling", "done", "failed"}
)
# Non-terminal statuses — a run in one of these blocks a new sync (409).
ACTIVE_SYNC_STATUSES: frozenset[str] = frozenset({"cloning", "pulling", "reconciling"})


class VaultConnection(Base):
    """Admin-configured Obsidian vault git connection (singleton row).

    The service layer (app/services/vault_connection.py) always reads the
    most recently updated row; there is no DB-level uniqueness constraint,
    only a by-convention singleton (see PLAN risk note).
    """

    __tablename__ = "vault_connection"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    git_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    branch: Mapped[str] = mapped_column(String(255), nullable=False, server_default="main")
    bot_email: Mapped[str] = mapped_column(String(320), nullable=False)
    templates_dirname: Mapped[str] = mapped_column(
        String(255), nullable=False, server_default="templates"
    )
    # AES-256-GCM encrypted access token — see app/crypto.py. Nullable: a
    # connection may have its URL/branch set before a token is entered.
    token_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    token_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    token_tag: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    token_key_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class VaultSyncRun(Base):
    """One admin-triggered (or CLI-triggered) vault sync execution."""

    __tablename__ = "vault_sync_run"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="cloning")
    added: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    updated: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    deleted: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    quarantined: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # Named failed_count (not `failed`) to avoid clashing with status="failed".
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
