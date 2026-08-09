import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import BIGINT, ENUM as PgEnum, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# References type created by Alembic 0001_baseline — do not recreate it
_role_level_pg = PgEnum(
    "L1", "L2", "L3", "L4", "L5", "L6", "ADMIN",
    name="role_level",
    create_type=False,
)


class Quota(Base):
    __tablename__ = "quotas"
    __table_args__ = (UniqueConstraint("user_id", "period_start"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    tokens_limit: Mapped[int] = mapped_column(BIGINT, nullable=False)
    tokens_used: Mapped[int] = mapped_column(BIGINT, nullable=False, server_default="0")
    cost_used_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, server_default="0")


class QuotaDefault(Base):
    __tablename__ = "quota_defaults"

    role: Mapped[str] = mapped_column(_role_level_pg, primary_key=True, nullable=False)
    monthly_token_limit: Mapped[int] = mapped_column(BIGINT, nullable=False)
