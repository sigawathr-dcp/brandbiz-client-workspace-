"""Read-only Obsidian vault ingestion into the RAG corpus.

Reuses the existing upload pipeline (app/services/ingestion.py) wholesale:
each vault note becomes a ``files`` row owned by a dedicated service-account
user, with ``scope="org"`` (searchable by every employee) and
``source="obsidian"`` / ``source_path=<vault-relative path>`` identifying it
as a synced note rather than a manual upload.

Reconcile algorithm (full-tree, every run — see PLAN discussion / grilling
session for why no git-commit-diff shortcut is used: hard-remove semantics
require comparing the DB against the *current* tree, and sha-gating already
makes unchanged files cheap):

    1. Walk the vault dir, excluding .obsidian/, .trash/, the templates dir,
       and any dotdir. Keep files extract_text() supports.
    2. Load existing ``files`` rows with source="obsidian" (keyed by source_path).
    3. For each tree file:
         - unchanged (sha + is_processed match) -> skip, no extraction/embed
         - otherwise extract + classify:
             - Tier 3+ -> quarantine (remove any prior row; do not ingest)
             - no prior row -> add
             - prior row, content changed -> update in place (same file_id)
    4. Any remaining DB row not seen in the tree -> hard-remove (delete
       covers renames too: old path removed, new path added).

Callers MUST call ``app.services.classifier.load_rules(session)`` before
invoking ``sync_vault`` when running outside the FastAPI process (the
classifier's rule cache is otherwise empty and every note silently scores
TIER_1_PUBLIC — see scripts/sync_vault.py).
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.models.classification import DataTier
from app.models.file import File, FileChunk
from app.services import audit as audit_svc
from app.services.classifier import detect_tier
from app.services.ingestion import delete_blob, extract_text, process_file, save_upload, sha256_of_path

_log = logging.getLogger(__name__)

# Mirrors _ALLOWED_MIME / _ALLOWED_SUFFIXES in app/routers/files.py, minus
# .doc (legacy binary Word — not reliably extractable and not part of the
# locked file-scope decision).
_MIME_BY_SUFFIX = {
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_EXTRACTABLE_SUFFIXES = frozenset(_MIME_BY_SUFFIX)

_ALWAYS_EXCLUDED_DIRNAMES = {".obsidian", ".trash"}


@dataclass
class SyncSummary:
    added: int = 0
    updated: int = 0
    deleted: int = 0
    quarantined: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Tree walk
# ---------------------------------------------------------------------------

def _is_excluded_dir(dirname: str, templates_dirname: str) -> bool:
    lowered = dirname.lower()
    if dirname.startswith("."):
        return True
    if lowered in _ALWAYS_EXCLUDED_DIRNAMES:
        return True
    return lowered == templates_dirname.lower()


def walk_vault(vault_root: Path, templates_dirname: str) -> dict[str, Path]:
    """Return {vault-relative POSIX path -> absolute path} for every
    extractable, non-excluded file under ``vault_root``."""
    tree: dict[str, Path] = {}
    if not vault_root.is_dir():
        _log.warning("walk_vault: vault_root %s does not exist", vault_root)
        return tree

    for root, dirnames, filenames in os.walk(vault_root):
        # Prune excluded dirs in place so os.walk doesn't descend into them.
        dirnames[:] = [
            d for d in dirnames if not _is_excluded_dir(d, templates_dirname)
        ]
        root_path = Path(root)
        for name in filenames:
            suffix = Path(name).suffix.lower()
            if suffix not in _EXTRACTABLE_SUFFIXES:
                continue
            abspath = root_path / name
            relpath = abspath.relative_to(vault_root).as_posix()
            tree[relpath] = abspath

    return tree


# ---------------------------------------------------------------------------
# Per-file operations
# ---------------------------------------------------------------------------

async def _add_note(
    session: AsyncSession,
    bot_user_id: uuid.UUID,
    relpath: str,
    abspath: Path,
    sha: str,
    tier: DataTier,
) -> None:
    cfg = get_settings()
    name = Path(relpath).name
    mime = _MIME_BY_SUFFIX.get(abspath.suffix.lower())
    data = abspath.read_bytes()

    file_id = uuid.uuid4()
    dest = save_upload(bot_user_id, file_id, name, data)
    try:
        s3_key = dest.relative_to(cfg.file_storage_dir).as_posix()
    except ValueError:
        s3_key = str(dest)

    session.add(File(
        id=file_id,
        user_id=bot_user_id,
        filename=name,
        mime_type=mime,
        size_bytes=len(data),
        s3_key=s3_key,
        sha256_hash=sha,
        detected_tier=tier.value,
        is_processed=False,
        scope="org",
        source="obsidian",
        source_path=relpath,
    ))
    await session.commit()

    await process_file(file_id)
    await audit_svc.log(
        action="vault_note_ingested",
        user_id=bot_user_id,
        details={"file_id": str(file_id), "source_path": relpath, "tier": tier.value},
    )


async def _update_note(
    session: AsyncSession,
    row: File,
    abspath: Path,
    sha: str,
    tier: DataTier,
) -> None:
    data = abspath.read_bytes()
    mime = _MIME_BY_SUFFIX.get(abspath.suffix.lower())
    # Same file_id + filename -> overwrites the existing blob in place.
    save_upload(row.user_id, row.id, row.filename, data)

    await session.execute(
        sa_update(File).where(File.id == row.id).values(
            sha256_hash=sha,
            detected_tier=tier.value,
            mime_type=mime,
            size_bytes=len(data),
            is_processed=False,
        )
    )
    await session.commit()

    await process_file(row.id)  # wipes old chunks first (idempotent)
    await audit_svc.log(
        action="vault_note_updated",
        user_id=row.user_id,
        details={"file_id": str(row.id), "source_path": row.source_path, "tier": tier.value},
    )


async def _remove_note(session: AsyncSession, row: File, *, action: str) -> None:
    delete_blob(row.user_id, row.id, row.filename)
    await session.execute(delete(FileChunk).where(FileChunk.file_id == row.id))
    await session.execute(delete(File).where(File.id == row.id))
    await session.commit()

    await audit_svc.log(
        action=action,
        user_id=row.user_id,
        details={"file_id": str(row.id), "source_path": row.source_path},
    )


# ---------------------------------------------------------------------------
# Reconcile
# ---------------------------------------------------------------------------

async def sync_vault(
    session_factory: async_sessionmaker[AsyncSession],
    bot_user_id: uuid.UUID,
    vault_root: Path,
    templates_dirname: str | None = None,
    dry_run: bool = False,
) -> SyncSummary:
    """Reconcile ``vault_root`` into the RAG corpus. See module docstring.

    ``dry_run=True`` walks, hashes, and (re)classifies exactly as a real run
    would, but performs no writes — the returned summary previews what a
    real run would do.
    """
    cfg = get_settings()
    templates_dirname = templates_dirname or cfg.vault_templates_dirname
    summary = SyncSummary()

    tree = walk_vault(vault_root, templates_dirname)

    async with session_factory() as session:
        existing = (
            await session.execute(select(File).where(File.source == "obsidian"))
        ).scalars().all()
        db_by_path: dict[str, File] = {row.source_path: row for row in existing if row.source_path}

        for relpath, abspath in tree.items():
            row = db_by_path.pop(relpath, None)
            try:
                sha = sha256_of_path(abspath)

                if row is not None and row.sha256_hash == sha and row.is_processed:
                    summary.skipped += 1
                    continue

                # Content is new or changed -> must (re)classify before ingesting.
                text = extract_text(abspath, _MIME_BY_SUFFIX.get(abspath.suffix.lower()))
                tier = detect_tier(text + " " + Path(relpath).name)

                if tier.rank >= DataTier.TIER_3_CONFIDENTIAL.rank:
                    if not dry_run:
                        if row is not None:
                            await _remove_note(session, row, action="vault_note_quarantined")
                        else:
                            await audit_svc.log(
                                action="vault_note_quarantined",
                                user_id=bot_user_id,
                                details={"source_path": relpath, "tier": tier.value},
                            )
                    summary.quarantined += 1
                    continue

                if row is None:
                    if not dry_run:
                        await _add_note(session, bot_user_id, relpath, abspath, sha, tier)
                    summary.added += 1
                else:
                    if not dry_run:
                        await _update_note(session, row, abspath, sha, tier)
                    summary.updated += 1

            except Exception as exc:  # noqa: BLE001 — one bad note must not abort the run
                _log.exception("sync_vault: failed on %s: %s", relpath, exc)
                summary.failed += 1
                summary.errors.append(f"{relpath}: {exc}")

        # Anything left in db_by_path was not seen in the tree -> deleted/renamed away.
        for row in db_by_path.values():
            try:
                if not dry_run:
                    await _remove_note(session, row, action="vault_note_deleted")
                summary.deleted += 1
            except Exception as exc:  # noqa: BLE001
                _log.exception("sync_vault: failed to remove %s: %s", row.source_path, exc)
                summary.failed += 1
                summary.errors.append(f"{row.source_path}: {exc}")

    _log.info(
        "sync_vault: added=%d updated=%d deleted=%d quarantined=%d skipped=%d failed=%d",
        summary.added, summary.updated, summary.deleted,
        summary.quarantined, summary.skipped, summary.failed,
    )
    return summary
