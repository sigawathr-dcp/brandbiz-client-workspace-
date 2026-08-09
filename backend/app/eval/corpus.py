"""
app/eval/corpus.py

DB-side corpus inspection for the case-match eval harness: is the case
library an agent has attached actually healthy enough to evaluate
against, and how do we map between the identifier the golden set uses
(filename — stable across reseeds) and the identifier the DB uses
(file_id — regenerated on every re-upload)?

Everything that touches the database lives here so app/eval/goldens.py
and app/eval/metrics.py can stay pure and unit-testable without one.
"""
from __future__ import annotations

import csv
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import File, FileChunk


@dataclass(frozen=True)
class CorpusFile:
    file_id: uuid.UUID
    filename: str
    sha256_hash: str | None
    is_processed: bool
    chunk_count: int
    embedded_chunk_count: int


@dataclass(frozen=True)
class CorpusReport:
    files: list[CorpusFile]
    duplicate_filenames: dict[str, list[uuid.UUID]]
    unprocessed: list[CorpusFile]
    zero_chunk: list[CorpusFile]
    unembedded_chunk_files: list[CorpusFile]  # has chunks, but not all embedded

    def is_healthy(self) -> bool:
        return not (
            self.duplicate_filenames
            or self.unprocessed
            or self.zero_chunk
            or self.unembedded_chunk_files
        )

    def problems(self) -> list[str]:
        """Human-readable preflight failures, in the order the export/run
        scripts should abort on: identity ambiguity first, then
        ingestion-pipeline gaps."""
        msgs = []
        for fn, ids in sorted(self.duplicate_filenames.items()):
            msgs.append(f"duplicate filename {fn!r}: file_ids {[str(i) for i in ids]}")
        for f in self.unprocessed:
            msgs.append(f"{f.filename}: is_processed=False")
        for f in self.zero_chunk:
            msgs.append(f"{f.filename}: zero chunks (file was never ingested)")
        for f in self.unembedded_chunk_files:
            msgs.append(
                f"{f.filename}: has unembedded chunks "
                f"({f.embedded_chunk_count}/{f.chunk_count}) — run scripts/reembed_pending.py"
            )
        return msgs


async def load_corpus(session: AsyncSession, file_ids: list[uuid.UUID]) -> CorpusReport:
    """Inspect exactly the given file ids — typically an agent's attached
    knowledge files (app.services.agent.get_agent_file_ids) — for
    eval-readiness. Does not apply any scope/tenant filter itself; the
    caller is responsible for resolving the right file_ids first (the same
    ones production retrieval would be narrowed to)."""
    if not file_ids:
        return CorpusReport(
            files=[], duplicate_filenames={}, unprocessed=[], zero_chunk=[], unembedded_chunk_files=[]
        )

    file_rows = (
        await session.execute(select(File).where(File.id.in_(file_ids)))
    ).scalars().all()

    chunk_rows = (
        await session.execute(
            select(
                FileChunk.file_id,
                func.count(FileChunk.id),
                func.count(FileChunk.embedding),  # COUNT(col) skips NULLs
            )
            .where(FileChunk.file_id.in_(file_ids))
            .group_by(FileChunk.file_id)
        )
    ).all()
    chunk_stats = {row[0]: (row[1], row[2]) for row in chunk_rows}

    files: list[CorpusFile] = []
    by_filename: dict[str, list[uuid.UUID]] = {}
    unprocessed: list[CorpusFile] = []
    zero_chunk: list[CorpusFile] = []
    unembedded: list[CorpusFile] = []

    for row in file_rows:
        chunk_count, embedded_count = chunk_stats.get(row.id, (0, 0))
        cf = CorpusFile(
            file_id=row.id,
            filename=row.filename,
            sha256_hash=row.sha256_hash,
            is_processed=row.is_processed,
            chunk_count=chunk_count,
            embedded_chunk_count=embedded_count,
        )
        files.append(cf)
        by_filename.setdefault(row.filename, []).append(row.id)
        if not row.is_processed:
            unprocessed.append(cf)
        if chunk_count == 0:
            zero_chunk.append(cf)
        elif embedded_count < chunk_count:
            unembedded.append(cf)

    duplicates = {fn: ids for fn, ids in by_filename.items() if len(ids) > 1}

    return CorpusReport(
        files=files,
        duplicate_filenames=duplicates,
        unprocessed=unprocessed,
        zero_chunk=zero_chunk,
        unembedded_chunk_files=unembedded,
    )


def resolve_filenames(report: CorpusReport) -> dict[str, uuid.UUID]:
    """filename -> file_id, for translating golden-set labels (filename-
    keyed) into the file_ids retrieval actually returns. Raises if the
    corpus has any duplicate filename — labels.csv could not be applied
    unambiguously in that case, and a silent "first match wins" would
    make the harness measure the wrong file some fraction of the time."""
    if report.duplicate_filenames:
        raise ValueError(
            f"cannot resolve filenames uniquely — duplicates present: "
            f"{sorted(report.duplicate_filenames)}"
        )
    return {f.filename: f.file_id for f in report.files}


# ---------------------------------------------------------------------------
# corpus_manifest.csv — staleness guard (sha256 drift vs. what was labeled)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ManifestEntry:
    filename: str
    sha256: str
    title: str | None
    client: str | None
    category: str | None
    chunk_count: int


def load_manifest(path: Path | str) -> dict[str, ManifestEntry]:
    path = Path(path)
    if not path.exists():
        return {}
    entries: dict[str, ManifestEntry] = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            entries[row["filename"]] = ManifestEntry(
                filename=row["filename"],
                sha256=row["sha256"],
                title=row.get("title") or None,
                client=row.get("client") or None,
                category=row.get("category") or None,
                chunk_count=int(row["chunk_count"]) if row.get("chunk_count") else 0,
            )
    return entries


def write_manifest(path: Path | str, entries: list[ManifestEntry]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "sha256", "title", "client", "category", "chunk_count"])
        for e in sorted(entries, key=lambda e: e.filename):
            writer.writerow([e.filename, e.sha256, e.title or "", e.client or "", e.category or "", e.chunk_count])


def sha_drift(report: CorpusReport, manifest: dict[str, ManifestEntry]) -> list[str]:
    """Filenames present in both the live corpus and the (committed)
    manifest whose content hash has changed since the manifest — and
    therefore the labels — were produced. A non-empty result means "labels
    may be stale", not "labels are wrong"; the report just needs to say so."""
    drifted = []
    for f in report.files:
        entry = manifest.get(f.filename)
        if entry is not None and f.sha256_hash is not None and entry.sha256 != f.sha256_hash:
            drifted.append(f.filename)
    return sorted(drifted)
