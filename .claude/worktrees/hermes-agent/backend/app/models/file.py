"""ORM models for the knowledge-base feature.

Tables ``files`` and ``file_chunks`` were created by Alembic 0001_baseline.
The ``scope`` column is added by 0007_file_scope. The ``source`` /
``source_path`` columns are added by 0027_obsidian_source_columns.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ENUM as PgEnum, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# References the existing PG enum — do not recreate.
_data_tier_pg = PgEnum(
    "TIER_1_PUBLIC",
    "TIER_2_INTERNAL",
    "TIER_3_CONFIDENTIAL",
    "TIER_4_RESTRICTED",
    name="data_tier",
    create_type=False,
)

# Valid scope values (stored as VARCHAR to avoid PG enum migration pain — Gotcha #5).
VALID_SCOPES: frozenset[str] = frozenset({"personal", "org"})


class File(Base):
    """A document uploaded by a user to the knowledge base."""

    __tablename__ = "files"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # In demo mode: relative path under FILE_STORAGE_DIR (reuses the s3_key column).
    s3_key: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detected_tier: Mapped[str | None] = mapped_column(_data_tier_pg, nullable=True)
    is_processed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # "personal" — only uploader can retrieve; "org" — all users can retrieve.
    scope: Mapped[str] = mapped_column(String(16), nullable=False, server_default="personal")
    # Provenance: "upload" (user upload via POST /files, default) or
    # "obsidian" (synced from the vault by app/services/vault_sync.py).
    source: Mapped[str] = mapped_column(String(32), nullable=False, server_default="upload")
    # Vault-relative POSIX path; the upsert key for vault_sync (unique per
    # source="obsidian" row). NULL for regular uploads.
    source_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FileChunk(Base):
    """One chunk of an ingested document, with its BGE-M3 embedding vector."""

    __tablename__ = "file_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 1024-dimensional BGE-M3 vector (HNSW index created by 0001_baseline).
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
