import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# References type created by Alembic 0001_baseline — do not recreate it
_model_provider_pg = PgEnum(
    "local", "anthropic", "openai", "google", "perplexity", "hermes",
    name="model_provider",
    create_type=False,
)


class ModelCatalog(Base):
    __tablename__ = "model_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(_model_provider_pg, nullable=False)
    is_local: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cost_per_1k_input_tokens: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    cost_per_1k_output_tokens: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    max_context_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supports_images: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    supports_tools: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
