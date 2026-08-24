import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Agent that seeded this conversation (nullable; set on first turn if agent_id was passed).
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Denormalized workspace_id (DB redesign, migration 0050) — removes the
    # join through `users` that every workspace-scoped conversation query
    # otherwise needed. NULL for internal (non-client-workspace) chats.
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # The Engagement this conversation belongs to, when it's a client-
    # workspace seat's funnel thread (one conversation per engagement —
    # see app/models/engagement.py::Engagement.conversation_id, the
    # inverse side of this same relationship).
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="SET NULL"),
        nullable=True,
    )
    # "internal" | "client_workspace" — VARCHAR + convention (Gotcha #5),
    # not a PG enum. Not yet read anywhere; reserved so a future query can
    # distinguish the two without inferring it from workspace_id being set.
    kind: Mapped[str] = mapped_column(String(24), nullable=False, server_default="internal")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
