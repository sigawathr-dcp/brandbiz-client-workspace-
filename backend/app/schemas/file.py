"""Pydantic DTOs for the knowledge-base / files API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

VALID_SCOPES = Literal["personal", "org"]


class FileOut(BaseModel):
    """Single file record returned to the frontend."""
    id: uuid.UUID
    filename: str
    mime_type: str | None
    size_bytes: int | None
    detected_tier: str | None
    is_processed: bool
    scope: str
    context: str = "upload"   # always "upload" — used by the Library UI Context column
    created_at: datetime

    model_config = {"from_attributes": True}


class FileListOut(BaseModel):
    """Paginated list of files."""
    items: list[FileOut]
    total: int


class FileStatusOut(BaseModel):
    """Lightweight polling response for the frontend stage stepper."""
    id: uuid.UUID
    is_processed: bool
    detected_tier: str | None
    scope: str

    model_config = {"from_attributes": True}


class ChunkOut(BaseModel):
    """One chunk row returned by GET /files/{id}/chunks."""
    id: uuid.UUID
    chunk_index: int
    token_count: int | None
    content_preview: str       # first 200 chars of the chunk
    has_embedding: bool
    created_at: datetime

    model_config = {"from_attributes": False}


class ChunkListOut(BaseModel):
    """Paginated list of chunks for a file."""
    file_id: uuid.UUID
    total: int
    embedded: int
    items: list[ChunkOut]
