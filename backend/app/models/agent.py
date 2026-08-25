"""
app/models/agent.py

ORM model for AI Agents.
Agents are reusable personas that bundle a provider/model, system-prompt
instructions, capability flags, and creativity level (temperature).
Instructions and description are plaintext (creator-authored config,
displayed in the About modal — not user message content, so §7.1 does not apply).
provider / visibility / status stored as VARCHAR to avoid PG enum migration pain (Gotcha #5).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Valid values — enforced in service layer, not as PG enum.
VALID_VISIBILITIES = frozenset({"public", "personal"})
VALID_STATUSES = frozenset({"published", "draft"})


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    # model_catalog.code value — e.g. "claude-sonnet-4"
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    # {"web_search": bool, "think_longer": bool, "image_gen": bool, "video_gen": bool}
    capabilities: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # 0–100; service maps to temperature via creativity_level / 100.0
    creativity_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # "public" | "personal"
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="public")
    # NULL = internal-shared agent (unchanged pre-D21/D22 behavior). Set = only
    # visible to seats in that client workspace — e.g. the น้อง brandbiz persona.
    # Only meaningful with visibility="public"; ignored for "personal".
    # See app/services/workspace.py::workspace_visibility_filter.
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # "published" | "draft"
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="published")
    # Optional UI metadata
    avatar_color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class AgentFile(Base):
    """Association between an agent and a knowledge file.

    Reuses the existing files/file_chunks RAG pipeline — no new ingestion code.
    """
    __tablename__ = "agent_files"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
