import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, func
from sqlalchemy.dialects.postgresql import ENUM as PgEnum, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# References types created by Alembic 0001_baseline — do not recreate them
_message_role_pg = PgEnum(
    "user", "assistant", "system", "tool",
    name="message_role",
    create_type=False,
)
_data_tier_pg = PgEnum(
    "TIER_1_PUBLIC", "TIER_2_INTERNAL", "TIER_3_CONFIDENTIAL", "TIER_4_RESTRICTED",
    name="data_tier",
    create_type=False,
)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Which funnel chapter this turn belongs to, when the conversation is a
    # client-workspace engagement's thread (DB redesign, migration 0050) —
    # lets a client-workspace transcript replay per chapter instead of
    # being rebuilt synthetically on every reload. NULL for internal chats
    # and for any turn not tied to a specific step (general free-form chat
    # within an engagement's conversation).
    engagement_step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagement_steps.id", ondelete="SET NULL"),
        nullable=True,
    )
    role: Mapped[str] = mapped_column(_message_role_pg, nullable=False)
    # Nullable (as of 0047_message_retention) — D14 drops these 30 days after
    # created_at via app/services/retention.py::purge_expired_messages. The
    # row itself, and every other column, is kept indefinitely; only the
    # encrypted content is dropped. See crypto.py::decrypt_message for the
    # read-side placeholder this produces.
    content_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    content_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    content_tag: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content_purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detected_tier: Mapped[str | None] = mapped_column(_data_tier_pg, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tokens_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
