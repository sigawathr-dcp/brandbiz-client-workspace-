"""
app/models/api_key.py

Service-account API keys for machine-to-machine authentication (n8n integration).

Keys are stored as SHA-256 hashes — the raw secret is shown exactly once at
creation time and never persisted. The "gw_" prefix allows the auth middleware
to route the token to the API-key path without hitting the JWT decoder first.
"""

import hashlib
import secrets
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_KEY_PREFIX = "gw_"


def generate_key() -> tuple[str, str]:
    """Return (raw_secret, key_hash).

    raw_secret starts with 'gw_' and must be shown to the user exactly once.
    key_hash (hex SHA-256) is what gets stored in the database.
    """
    raw = _KEY_PREFIX + secrets.token_urlsafe(40)
    h = hashlib.sha256(raw.encode()).hexdigest()
    return raw, h


def hash_key(raw: str) -> str:
    """Return the SHA-256 hex digest of a raw key string."""
    return hashlib.sha256(raw.encode()).hexdigest()


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="Human-readable label")
    key_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="SHA-256 of the raw secret"
    )
    service_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="The User row that this key authenticates as",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
