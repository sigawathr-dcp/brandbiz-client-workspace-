"""
app/models/client_invite.py

ORM model for client-workspace invite links (Phase 5, D21/D22, Phase 2).

Mirrors app/models/api_key.py's hash-only-storage pattern: the raw token is
returned exactly once at mint time (from create_invite()) and only its
SHA-256 hash is persisted. redeem_invite() looks the raw token up by hash,
creates the seat User, and marks the invite spent — see
app/services/workspace.py.

This is the LINE-integration seam: n8n will eventually call
POST /admin/clients/{id}/invites with a service API key after receiving a
LINE profile, and push the resulting /try/<token> link back into LINE. Until
that's wired up, invites are minted by hand from the admin UI (Phase 2) —
line_user_id/contact_name are populated by whichever path created the invite.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ClientInvite(Base):
    __tablename__ = "client_invites"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # SHA-256 hex of the raw token — the raw value is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The seat User created at redemption time (NULL until redeemed).
    redeemed_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Admin who minted this invite (NULL if minted by a service account /
    # future LINE-bot flow rather than a human in the admin UI).
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # LINE seam (not yet wired to a real LINE connection) — populated when
    # the invite is minted on behalf of a specific LINE contact.
    line_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
