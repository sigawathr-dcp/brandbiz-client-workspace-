"""Knowledge-base file upload, listing, and deletion endpoints.

Storage model (demo / R1):
  Blobs are written to ``FILE_STORAGE_DIR/{user_id}/{file_id}_{filename}``.
  The ``files.s3_key`` column stores the relative path under ``FILE_STORAGE_DIR``.

Ingestion (chunking + embedding) runs via FastAPI ``BackgroundTasks`` — the
POST /files response returns 202 immediately and the caller polls
GET /files/{id} until ``is_processed=True``.
"""
from __future__ import annotations

import hashlib
import io
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile
from fastapi import Form
from fastapi.responses import FileResponse
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.deps import require_consent
from app.models.classification import DataTier
from app.models.file import File, FileChunk, VALID_SCOPES
from app.models.user import User
from app.schemas.file import ChunkListOut, ChunkOut, FileListOut, FileOut, FileStatusOut
from app.services.classifier import detect_tier
from app.services.ingestion import blob_path, delete_blob, process_file, save_upload
from app.services.workspace import is_client_seat, workspace_visibility_filter

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/files", tags=["files"])

_ALLOWED_MIME = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/octet-stream",  # some clients send this for unknown types
}
_ALLOWED_SUFFIXES = {".pdf", ".docx", ".doc", ".txt", ".md", ".csv"}


@router.post("", status_code=202)
async def upload_file(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: str = Form(default="personal"),
) -> dict:
    """Upload a document to the knowledge base.

    Returns 202 immediately; the caller should poll GET /files/{id} until
    ``is_processed=True`` before expecting retrieval results.
    """
    cfg = get_settings()

    # --- Validate scope ---
    if scope not in VALID_SCOPES:
        raise HTTPException(
            status_code=422,
            detail=f"scope must be one of {sorted(VALID_SCOPES)}",
        )
    # D23: every booth attendee shares one workspace (redeem_invite mints
    # into invite.workspace_id), so an org-scope upload from a client seat
    # would be readable by every other attendee in the same workspace, not
    # just by Brandbiz staff. Client seats may only upload personal files.
    if scope == "org" and is_client_seat(user):
        raise HTTPException(
            status_code=422,
            detail="Client workspace seats can only upload personal-scope files",
        )

    # --- Validate file type ---
    suffix = "." + (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if suffix not in _ALLOWED_SUFFIXES and content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{suffix or content_type}'. Allowed: PDF, DOCX, TXT, MD, CSV.",
        )

    # --- Read + size check ---
    data = await file.read()
    if len(data) > cfg.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {cfg.max_upload_bytes // (1024 * 1024)} MB.",
        )

    # --- Classify content for tier detection ---
    try:
        text_sample = data[:4096].decode("utf-8", errors="replace")
    except Exception:
        text_sample = file.filename or ""
    tier: DataTier = detect_tier(text_sample + " " + (file.filename or ""))

    # --- Create DB row ---
    file_id = uuid.uuid4()
    sha = hashlib.sha256(data).hexdigest()
    dest = save_upload(user.id, file_id, file.filename or "file", io.BytesIO(data))

    # s3_key = relative path from FILE_STORAGE_DIR
    try:
        s3_key = dest.relative_to(cfg.file_storage_dir).as_posix()
    except ValueError:
        s3_key = str(dest)

    db_file = File(
        id=file_id,
        user_id=user.id,
        filename=file.filename or "file",
        mime_type=content_type or None,
        size_bytes=len(data),
        s3_key=s3_key,
        sha256_hash=sha,
        detected_tier=tier.value,
        is_processed=False,
        scope=scope,
        # D23: stamps the uploader's tenant onto the row so
        # workspace_visibility_filter's org branch — and the uploader's own
        # RAG retrieval — see it correctly. NULL for internal staff,
        # unchanged from pre-D23 behavior.
        workspace_id=user.workspace_id,
    )
    session.add(db_file)
    await session.commit()
    await session.refresh(db_file)

    # --- Enqueue background ingestion ---
    background_tasks.add_task(process_file, file_id)

    _log.info(
        "File %s uploaded by user %s (scope=%s, tier=%s, size=%d)",
        file.filename, user.id, scope, tier.value, len(data),
    )

    return {
        "file_id": str(file_id),
        "filename": db_file.filename,
        "detected_tier": db_file.detected_tier,
        "scope": db_file.scope,
        "status": "processing",
    }


@router.get("", response_model=FileListOut)
async def list_files(
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
    date_from: Annotated[datetime | None, Query(description="ISO 8601 lower bound")] = None,
    date_to: Annotated[datetime | None, Query(description="ISO 8601 upper bound")] = None,
    sort: Annotated[str, Query()] = "recent",
    context: Annotated[str | None, Query(description="'upload' or 'generate'")] = None,
    q: Annotated[str | None, Query(description="Filename search (case-insensitive)")] = None,
) -> FileListOut:
    """List files the caller owns plus org-scoped files from the same tenant
    (D21/D22 — this router is internal-only, so in practice this excludes
    client-workspace files from the internal file browser)."""
    # Files are always context=upload; generate context yields empty
    if context and context.lower() == "generate":
        return FileListOut(items=[], total=0)

    stmt = select(File).where(
        or_(
            File.user_id == user.id,
            and_(File.scope == "org", workspace_visibility_filter(user, File)),
        )
    )
    if date_from is not None:
        stmt = stmt.where(File.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(File.created_at < date_to)
    if q:
        stmt = stmt.where(File.filename.ilike(f"%{q}%"))
    if sort == "oldest":
        stmt = stmt.order_by(File.created_at.asc())
    else:
        stmt = stmt.order_by(File.created_at.desc())

    rows = (await session.execute(stmt)).scalars().all()
    items = [FileOut.model_validate(r) for r in rows]
    return FileListOut(items=items, total=len(items))


@router.get("/{file_id}", response_model=FileStatusOut)
async def get_file_status(
    file_id: uuid.UUID,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FileStatusOut:
    """Poll ingestion status for a single file."""
    row = await _get_accessible_file(session, user, file_id)
    return FileStatusOut.model_validate(row)


@router.get("/{file_id}/chunks", response_model=ChunkListOut)
async def list_file_chunks(
    file_id: uuid.UUID,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
    offset: int = 0,
) -> ChunkListOut:
    """Return paginated chunk metadata for a file, including embedding status.

    Access rules mirror GET /files/{id}: personal files only for the owner,
    org-scoped files for any authenticated user.
    """
    await _get_accessible_file(session, user, file_id)

    stmt = (
        select(FileChunk)
        .where(FileChunk.file_id == file_id)
        .order_by(FileChunk.chunk_index)
        .offset(offset)
        .limit(min(limit, 200))
    )
    rows = (await session.execute(stmt)).scalars().all()

    # Total and embedded counts (unaffected by pagination)
    count_stmt = select(FileChunk).where(FileChunk.file_id == file_id)
    all_rows = (await session.execute(count_stmt)).scalars().all()
    total = len(all_rows)
    embedded = sum(1 for r in all_rows if r.embedding is not None)

    items = [
        ChunkOut(
            id=r.id,
            chunk_index=r.chunk_index,
            token_count=r.token_count,
            content_preview=r.content[:200],
            has_embedding=r.embedding is not None,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return ChunkListOut(file_id=file_id, total=total, embedded=embedded, items=items)


@router.get("/{file_id}/download")
async def download_file(
    file_id: uuid.UUID,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FileResponse:
    """Stream the raw file bytes to the caller.

    Access rules mirror GET /files/{id}: personal files only for the owner,
    org-scoped files for any authenticated user.
    """
    row = await _get_accessible_file(session, user, file_id)
    blob = blob_path(row.user_id, row.id, row.filename)
    if not Path(blob).is_file():
        raise HTTPException(status_code=404, detail="File blob not found on disk")
    return FileResponse(
        path=blob,
        filename=row.filename,
        media_type=row.mime_type or "application/octet-stream",
    )


@router.delete("/{file_id}", status_code=204, response_model=None)
async def delete_file(
    file_id: uuid.UUID,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a file and its chunks. Only the original uploader may delete."""
    row = await _get_owned_file(session, user, file_id)

    # Delete chunks
    await session.execute(delete(FileChunk).where(FileChunk.file_id == file_id))
    # Delete blob
    delete_blob(row.user_id, row.id, row.filename)
    # Delete DB row (chunks cascade)
    await session.delete(row)
    await session.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_accessible_file(
    session: AsyncSession,
    user: User,
    file_id: uuid.UUID,
) -> File:
    """Return a File the user is allowed to read (own, or org-scoped within
    the same tenant — D21/D22)."""
    row = (
        await session.execute(
            select(File).where(
                File.id == file_id,
                or_(
                    File.user_id == user.id,
                    and_(File.scope == "org", workspace_visibility_filter(user, File)),
                ),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="File not found")
    return row


async def _get_owned_file(
    session: AsyncSession,
    user: User,
    file_id: uuid.UUID,
) -> File:
    """Return a File owned by this user; 404 for non-existent or other owners."""
    row = (
        await session.execute(
            select(File).where(File.id == file_id, File.user_id == user.id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404, detail="File not found or you do not own it"
        )
    return row
