"""
app/models/rate_card.py

ORM model for rate-card line items (Phase 5 §4, D21/D22).

The correctness fix this repo's plan called for: the design's own budget
guardrail ("refuse any line without a rate-card row") is a prompt-level
instruction and a local model will violate it. Making it structural instead
— the model emits only {code, qty} pairs (app/services/plan.py::draft_plan),
never a number, and app/services/rate_card.py::price() looks up the actual
THB amount from this table in Python. A code with no matching row becomes a
"needs_expert" line, never a fabricated price.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RateCardItem(Base):
    __tablename__ = "rate_card_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # NULL = shared/default rate card, usable by any workspace. Set = a
    # workspace-specific override or addition (e.g. a special client rate).
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    section: Mapped[str | None] = mapped_column(String(16), nullable=True)  # e.g. "1.2"
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, server_default="THB")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
