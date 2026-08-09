"""
app/models/workspace.py

ORM model for client workspaces (D21/D22, Phase 5 — Client Workspaces).

A workspace is a client tenant sharing this single gateway instance. Internal
staff have ``users.workspace_id IS NULL`` and are unaffected by any of this —
see ``app/services/workspace.py::workspace_visibility_filter`` for the
isolation rule applied on top of the existing org/public scoping in
rag_search.py, skill.py, and agent.py.

``kind`` distinguishes the event-demo workspace(s) from real client
engagements; both use identical code paths, only seed data differs.
``token_budget_limit`` / ``token_budget_used`` are a hard pooled cost cap
across every seat in the workspace (an attendee pasting a book into the
composer should hit this, not the per-seat monthly quota, which is sized for
a single employee). ``monthly_token_limit`` overrides the per-seat
``quota_defaults`` role limit for seats in this workspace — see
PolicyEngine._get_or_create_current_quota.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Stored as VARCHAR, not a PG enum — Gotcha #5.
VALID_WORKSPACE_KINDS: frozenset[str] = frozenset({"demo", "client"})


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # "demo" (event/test workspaces) | "client" (real engagements)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default="demo")

    # LINE integration seam (Phase 2) — populated once an invite is redeemed
    # via a LINE-sourced link. NULL until the real LINE connection lands.
    line_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Per-seat monthly token ceiling override (NULL = fall back to the
    # role's quota_defaults row, same as internal users).
    monthly_token_limit: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Pooled hard cap shared by every seat in this workspace — the event
    # cost-control backstop. NULL = no pooled cap (per-seat quota still applies).
    token_budget_limit: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    token_budget_used: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
