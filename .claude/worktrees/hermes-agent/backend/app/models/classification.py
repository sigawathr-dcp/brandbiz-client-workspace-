from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# References the type created by Alembic 0001_baseline — do not recreate it.
_data_tier_pg = PgEnum(
    "TIER_1_PUBLIC",
    "TIER_2_INTERNAL",
    "TIER_3_CONFIDENTIAL",
    "TIER_4_RESTRICTED",
    name="data_tier",
    create_type=False,
)


class DataTier(str, Enum):
    """Sensitivity tiers, ascending order (TIER_1 = lowest, TIER_4 = highest).

    Inherits ``str`` so values compare equal to the raw PG enum strings and
    can be used directly in SQLAlchemy queries / JSON serialisation.
    """

    TIER_1_PUBLIC = "TIER_1_PUBLIC"
    TIER_2_INTERNAL = "TIER_2_INTERNAL"
    TIER_3_CONFIDENTIAL = "TIER_3_CONFIDENTIAL"
    TIER_4_RESTRICTED = "TIER_4_RESTRICTED"

    @property
    def rank(self) -> int:
        """Integer rank for 'highest wins' comparisons (1 = lowest)."""
        return {
            DataTier.TIER_1_PUBLIC: 1,
            DataTier.TIER_2_INTERNAL: 2,
            DataTier.TIER_3_CONFIDENTIAL: 3,
            DataTier.TIER_4_RESTRICTED: 4,
        }[self]


class DataClassificationRule(Base):
    """ORM model for ``data_classification_rules`` (created by 0001_baseline)."""

    __tablename__ = "data_classification_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # 'regex' | 'keyword' | 'ner'  (ner is Phase-4 deferred)
    pattern_type: Mapped[str] = mapped_column(String(50), nullable=False)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    detected_tier: Mapped[str] = mapped_column(_data_tier_pg, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
