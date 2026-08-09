"""
app/models/skill.py

ORM model for Skills.
A Skill is a reusable instruction fragment: a name (kebab-case, used as the
/slug command), a description (drives auto-invocation matching), and an
instructions body injected into the chat system prompt when selected.

Instructions and description are plaintext (creator-authored config, same as
Agent.instructions — not user message content, so §7.1 does not apply).
enabled / visibility stored as BOOLEAN / VARCHAR to avoid PG enum migration
pain (Gotcha #5).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Valid values — enforced in service layer, not as PG enum.
VALID_SKILL_VISIBILITIES = frozenset({"public", "personal"})


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_skills_user_id_name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Kebab-case slug — also the /name command. Unique per owner.
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    # The trigger field: drives auto-match against the user's message.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The SKILL.md body, injected into the chat system prompt when selected.
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Raw uploaded SKILL.md source, kept for display/re-editing; null when
    # the skill was authored via the "Write skill instructions" form.
    source_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    # On/off toggle — disabled skills are never auto-matched or forced.
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # "public" | "personal"
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="personal")
    # NULL = internal-shared skill (unchanged pre-D21/D22 behavior). Set = only
    # visible to seats in that client workspace. Only meaningful with
    # visibility="public"; ignored for "personal". See app/services/workspace.py.
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class AgentSkill(Base):
    """Association between an agent and a skill.

    A pinned skill is always injected into that agent's chat turns, in
    addition to whatever the description-matching selector picks.
    """
    __tablename__ = "agent_skills"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
