"""Document ingestion pipeline for the RAG knowledge base (demo mode).

Storage model (R1): file blobs are saved to a local directory
(``FILE_STORAGE_DIR``).  The ``files.s3_key`` column holds the relative path
``{user_id}/{file_id}_{filename}``.

Pipeline (runs via FastAPI BackgroundTasks):
  read blob → extract text → chunk → embed (batched) → write FileChunk rows
  → mark files.is_processed = True → audit "file_uploaded"

All steps are idempotent: existing chunks for a file are deleted before
re-inserting, so retrying a failed ingestion is safe (PLAN Task 3.2 accept).
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import uuid
from pathlib import Path
from typing import IO

from sqlalchemy import delete, select, update as sa_update

from app.config import get_settings
from app.db import session_factory
from app.llm.embeddings import EmbeddingError, get_embedder
from app.models.classification import DataTier
from app.models.file import File, FileChunk
from app.services import audit as audit_svc
from app.services.classifier import detect_tier

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Local storage helpers
# ---------------------------------------------------------------------------

def _storage_root() -> Path:
    return Path(get_settings().file_storage_dir)


def blob_path(user_id: uuid.UUID, file_id: uuid.UUID, filename: str) -> Path:
    """Return the absolute path where a file's blob is stored."""
    safe_name = Path(filename).name  # strip any directory separators
    return _storage_root() / str(user_id) / f"{file_id}_{safe_name}"


def save_upload(
    user_id: uuid.UUID,
    file_id: uuid.UUID,
    filename: str,
    data: bytes | IO[bytes],
) -> Path:
    """Write upload bytes to local storage; return the absolute path."""
    dest = blob_path(user_id, file_id, filename)
    dest.parent.mkdir(parents=True, exist_ok=True)
    content = data if isinstance(data, bytes) else data.read()
    dest.write_bytes(content)
    return dest


def delete_blob(user_id: uuid.UUID, file_id: uuid.UUID, filename: str) -> None:
    """Remove a stored blob (best-effort; logs warning on failure)."""
    path = blob_path(user_id, file_id, filename)
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        _log.warning("Could not delete blob %s: %s", path, exc)


def sha256_of_path(path: Path) -> str:
    """Return hex SHA-256 of the file at ``path``."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _sanitize(text: str) -> str:
    """Remove characters that PostgreSQL UTF-8 rejects (null bytes) and strip
    other ASCII control chars except tab/newline/CR that are safe in text."""
    # \x00 is the main culprit from PDF font encodings; also strip \x01-\x08,
    # \x0b-\x0c, \x0e-\x1f which are rarely meaningful in document text.
    return text.translate(
        str.maketrans("", "", "".join(chr(c) for c in range(32) if c not in (9, 10, 13)))
    )


def extract_text(path: Path, mime_type: str | None) -> str:
    """Return plaintext from a document file.

    Supports: PDF, DOCX, plain text (TXT/MD/CSV).
    Falls back to UTF-8 read with error replacement for unknown types.
    """
    mime = (mime_type or "").lower()
    suffix = path.suffix.lower()

    if mime == "application/pdf" or suffix == ".pdf":
        raw = _extract_pdf(path)
    elif (
        mime in {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        }
        or suffix in {".docx", ".doc"}
    ):
        raw = _extract_docx(path)
    else:
        # Fallback: UTF-8 text (covers .txt, .md, .csv, etc.)
        raw = path.read_text(encoding="utf-8", errors="replace")

    return _sanitize(raw)


def _extract_pdf(path: Path) -> str:
    try:
        import pypdf  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "pypdf is required for PDF extraction. Add it to pyproject.toml."
        ) from exc

    parts: list[str] = []
    with open(path, "rb") as fh:
        reader = pypdf.PdfReader(fh)
        for page in reader.pages:
            text = page.extract_text() or ""
            parts.append(text)
    return "\n".join(parts)


def _extract_docx(path: Path) -> str:
    try:
        import docx  # noqa: PLC0415  (python-docx)
    except ImportError as exc:
        raise RuntimeError(
            "python-docx is required for DOCX extraction. Add it to pyproject.toml."
        ) from exc

    doc = docx.Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_text(
    text: str,
    chunk_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[str]:
    """Split ``text`` into overlapping windows.

    Uses a character approximation of 4 chars ≈ 1 token to avoid a tokenizer
    dependency. Returns a list of non-empty chunk strings.
    """
    cfg = get_settings()
    chars_per_chunk = (chunk_tokens or cfg.rag_chunk_tokens) * 4
    overlap_chars = (overlap_tokens or cfg.rag_chunk_overlap) * 4

    if not text.strip():
        return []

    chunks: list[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chars_per_chunk, text_len)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_len:
            break
        # Advance by chunk size minus overlap
        start += chars_per_chunk - overlap_chars

    return chunks


# ---------------------------------------------------------------------------
# Background ingestion task
# ---------------------------------------------------------------------------

_EMBED_BATCH_SIZE = 32  # chunks per embedding request


async def process_file(file_id: uuid.UUID) -> None:
    """Ingest a file: chunk → embed → persist FileChunks → mark is_processed.

    This runs as a FastAPI BackgroundTask after ``POST /files`` saves the blob
    and creates the ``files`` row with ``is_processed=False``.

    Idempotent: existing chunks are deleted first.
    Uses its own DB session (not the request session, which is already closed).
    """
    _log.info("process_file: starting file_id=%s", file_id)
    async with session_factory() as session:
        # 1. Load the file row
        row: File | None = (
            await session.execute(select(File).where(File.id == file_id))
        ).scalar_one_or_none()

        if row is None:
            _log.error("process_file: file_id=%s not found — skipping", file_id)
            return

        # 2. Extract text from the stored blob
        path = blob_path(row.user_id, row.id, row.filename)
        try:
            text = extract_text(path, row.mime_type)
        except Exception as exc:
            _log.exception("process_file: text extraction failed for %s: %s", path, exc)
            return

        if not text.strip():
            _log.warning("process_file: no text extracted from %s — marking processed", path)
            await session.execute(
                sa_update(File).where(File.id == file_id).values(is_processed=True)
            )
            await session.commit()
            return

        # 3. Chunk
        chunks = chunk_text(text)
        _log.info("process_file: %d chunks for file_id=%s", len(chunks), file_id)

        # 4. Delete any existing chunks (idempotency)
        await session.execute(delete(FileChunk).where(FileChunk.file_id == file_id))

        # 5. Embed in batches and write FileChunk rows
        embedder = get_embedder()
        for batch_start in range(0, len(chunks), _EMBED_BATCH_SIZE):
            batch = chunks[batch_start : batch_start + _EMBED_BATCH_SIZE]
            try:
                vectors = await embedder.embed(batch)
            except EmbeddingError as exc:
                _log.error(
                    "process_file: embedding failed for file_id=%s batch %d: %s",
                    file_id, batch_start, exc,
                )
                # Store chunks without embeddings so retrieval can still be attempted
                # once the embed server is available again (partial progress).
                vectors = [None] * len(batch)  # type: ignore[list-item]

            for local_idx, (chunk_text_content, vec) in enumerate(zip(batch, vectors)):
                chunk_index = batch_start + local_idx
                token_count = len(chunk_text_content) // 4  # heuristic
                session.add(FileChunk(
                    file_id=file_id,
                    chunk_index=chunk_index,
                    content=chunk_text_content,
                    embedding=vec,
                    token_count=token_count,
                ))

        # 6. Mark file as processed + update sha256 if not already set
        if row.sha256_hash is None:
            try:
                sha = sha256_of_path(path)
            except OSError:
                sha = None
        else:
            sha = row.sha256_hash

        await session.execute(
            sa_update(File).where(File.id == file_id).values(
                is_processed=True,
                sha256_hash=sha,
            )
        )
        await session.commit()

        # 7. Audit (§7.3: append-only, async-safe)
        await audit_svc.log(
            action="file_uploaded",
            user_id=row.user_id,
            details={
                "file_id": str(file_id),
                "filename": row.filename,
                "chunks": len(chunks),
                "tier": row.detected_tier,
                "scope": row.scope,
            },
        )

    _log.info("process_file: done file_id=%s (%d chunks)", file_id, len(chunks))
