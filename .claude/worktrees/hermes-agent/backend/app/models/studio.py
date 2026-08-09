"""
app/models/studio.py

ORM model for True Studio generation records.
Prompts are AES-256-GCM encrypted (§7.1 — never store plaintext user content).
type / status stored as VARCHAR to avoid PG enum migration pain (Gotcha #5).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Valid values — enforced in service layer, not as PG enum.
VALID_TYPES = frozenset({"image", "video", "music"})
VALID_STATUSES = frozenset({"completed", "processing", "mocked", "failed"})


class StudioGeneration(Base):
    __tablename__ = "studio_generations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Prior generation this one was derived from (image edit, video/music
    # regenerate). NULL for original generations.
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("studio_generations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # "image" | "video" | "music"
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    model_label: Mapped[str] = mapped_column(String(100), nullable=False)
    # AES-256-GCM encrypted prompt (§7.1)
    prompt_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    prompt_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    prompt_tag: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Per-mode generation settings (aspect ratio, resolution, duration, etc.)
    settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # "completed" | "processing" | "mocked" | "failed"
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="mocked")
    # data URL for images (multi-MB inline base64); placeholder URI for video/music
    output_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Estimated token cost (None for real image gen — not token-quota-gated)
    token_cost: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
