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
    role: Mapped[str] = mapped_column(_message_role_pg, nullable=False)
    content_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_tag: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    detected_tier: Mapped[str | None] = mapped_column(_data_tier_pg, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tokens_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
