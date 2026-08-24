"""Ingest the case-study library into the demo workspace (Phase 5, D21/D22).

`seed_client_demo.py` deliberately does not seed case studies ("needs real
files" — see its module docstring); this script is that follow-up step,
made scriptable instead of manual.

It reads `case-study_<slug>.md`, one per campaign, from a source directory
— built from the curated spreadsheet by `scripts/build_case_studies.py`,
which is what replaced the old out-of-repo generator — then for each file:
  1. writes the blob via the existing `app.services.ingestion.save_upload`
     (same path POST /files uses),
  2. inserts a `files` row with scope="library" and workspace_id=NULL
     (ADR 0002). The library scope is readable by EVERY tenant — it has to
     be: each LINE-minted client workspace is its own tenant (D24), so an
     org-scoped corpus stamped to the demo workspace was invisible to every
     real client and POST /client/cases matched nothing. It is also
     independent of CLIENT_INTERNAL_ACCESS_ENABLED, which must stay off for
     a public LINE entry point (line_plan.md, Risks #2),
  3. runs it through `app.services.ingestion.process_file` — chunk, embed,
     mark processed — unchanged, so this is exactly the pipeline a real
     upload goes through, and
  4. links it to the workspace's agent via `AgentFile`, resolved through
     `app.services.workspace.get_workspace_agent` (the same lookup
     POST /client/cases uses) rather than a hardcoded agent id — a
     hardcoded id silently breaks the moment the demo agent is re-seeded.
  5. writes its `case_studies` catalog row, so a freshly seeded case has
     somewhere for scripts/seed_case_tags.py to hang tags off. Production
     only ever writes that row lazily, on a case's first match.

Idempotent: a library file already present (matched by filename +
scope="library") is left untouched — not re-uploaded, not re-embedded, not
re-linked. The workspace argument only decides WHICH agent the corpus is
attached to (the demo workspace's template agent, which every LINE
workspace's agent is cloned from).

`--refresh` widens that to "untouched unless its CONTENT changed": a file
whose bytes on disk no longer match `files.sha256_hash` is re-ingested in
place, under the same file_id — agent_files, case_studies and every
historical case_matches row point at that id — and its `case_studies`
catalog row is re-parsed. Without the flag a corpus rebuild appears to
succeed while the database keeps serving the previous text.

Usage — run from the repo root on the host, then inside the container:
    python backend/scripts/build_case_studies.py --write --tags
    docker compose cp backend/data/case_studies backend-api:/data/seed/case_studies
    docker compose exec backend-api sh -c \
        "cd /app && PYTHONPATH=/app python scripts/seed_case_studies.py --refresh"

Optional args: `python scripts/seed_case_studies.py [source_dir] [workspace_slug] [--refresh]`
(defaults: /data/seed/case_studies, brandbiz-demo).
"""
from __future__ import annotations

import asyncio
import hashlib
import sys
import uuid
from pathlib import Path

from sqlalchemy import delete, select

from app.config import get_settings
from app.models.agent import AgentFile
from app.models.client_intake import CaseStudy
from app.models.file import LIBRARY_SCOPE, File, FileChunk
from app.models.user import User
from app.models.workspace import Workspace
from app.services import ingestion
from app.services.case_card import parse_case_card
from app.services.workspace import get_workspace_agent

DEFAULT_SOURCE_DIR = "/data/seed/case_studies"
DEFAULT_WORKSPACE_SLUG = "brandbiz-demo"
SEED_ADMIN_EMAIL = "demo-seeder@brandbiz.seed"  # owner of record — see seed_client_demo.py


async def refresh_file(
    session, row: File, path: Path, owner_id, workspace_id, storage_root: Path
) -> None:
    """Re-ingest changed content under the SAME file_id.

    Chunks are deleted rather than updated because chunk boundaries move
    when the document changes; leaving the old ones would keep stale text
    retrievable alongside the new. `sha256_hash` is cleared so
    ingestion.process_file recomputes it (it only fills the field when it is
    None), which is also what makes corpus_manifest.csv's drift check honest
    after a rebuild.
    """
    data = path.read_bytes()
    dest = ingestion.save_upload(owner_id, row.id, path.name, data)
    try:
        s3_key = dest.relative_to(storage_root).as_posix()
    except ValueError:
        s3_key = str(dest)

    await session.execute(delete(FileChunk).where(FileChunk.file_id == row.id))
    row.s3_key = s3_key
    row.size_bytes = len(data)
    row.sha256_hash = None
    row.is_processed = False
    session.add(row)
    await session.commit()

    await ingestion.process_file(row.id)
    await upsert_catalog(session, row.id, workspace_id, data)


async def upsert_catalog(session, file_id, workspace_id, data: bytes) -> bool:
    """Create or refresh the `case_studies` catalog row for one file.

    Production writes this row lazily, on a case's first match
    (routers/client.py), and never updates it afterwards — so without this
    a newly seeded case has no catalog row for scripts/seed_case_tags.py to
    hang tags off, and a rebuilt case keeps serving its old title and
    category forever. `content_sha256` is what makes the staleness the model
    docstring describes actually detectable.

    Returns True when a row was created.
    """
    card = parse_case_card(data.decode("utf-8"))
    study = (
        await session.execute(select(CaseStudy).where(CaseStudy.file_id == file_id))
    ).scalar_one_or_none()
    created = study is None
    if study is None:
        study = CaseStudy(workspace_id=workspace_id, file_id=file_id)
    study.title = card.title
    study.client_name = card.client
    study.category = card.category
    study.source_url = card.source_url
    study.summary = card.summary
    # Only overwrite the thumbnail when the document names one: image_url is
    # otherwise recovered offline by backfill_case_images.py and is not
    # something the markdown knows about.
    if card.image_url:
        study.image_url = card.image_url
    study.content_sha256 = hashlib.sha256(data).hexdigest()
    session.add(study)
    await session.commit()
    return created


async def upsert_catalog_if_missing(session, file_id, workspace_id, path: Path) -> bool:
    """Create the catalog row only when there is none. Returns True if it
    created one. Never overwrites: an existing row may carry an image_url
    recovered offline that the markdown does not know about."""
    exists = (
        await session.execute(select(CaseStudy.id).where(CaseStudy.file_id == file_id))
    ).scalar_one_or_none()
    if exists is not None:
        return False
    return await upsert_catalog(session, file_id, workspace_id, path.read_bytes())


async def main() -> None:
    positional = [a for a in sys.argv[1:] if not a.startswith("-")]
    refresh = "--refresh" in sys.argv[1:]
    source_dir = Path(positional[0]) if positional else Path(DEFAULT_SOURCE_DIR)
    workspace_slug = positional[1] if len(positional) > 1 else DEFAULT_WORKSPACE_SLUG

    files = sorted(source_dir.glob("case-study_*.md"))
    if not files:
        print(f"No case-study_*.md files found under {source_dir} — nothing to do.")
        print("Run scripts/build_case_studies.py --write first (see module docstring).")
        return

    from app.db import session_factory

    async with session_factory() as session:
        workspace = (
            await session.execute(select(Workspace).where(Workspace.slug == workspace_slug))
        ).scalar_one_or_none()
        if workspace is None:
            print(f"Workspace '{workspace_slug}' not found — run seed_client_demo.py first.")
            return

        agent = await get_workspace_agent(session, workspace.id)
        if agent is None:
            print(f"No published agent scoped to workspace '{workspace_slug}' — run seed_client_demo.py first.")
            return

        owner = (
            await session.execute(select(User).where(User.google_email == SEED_ADMIN_EMAIL))
        ).scalar_one_or_none()
        if owner is None:
            print(f"Seed admin '{SEED_ADMIN_EMAIL}' not found — run seed_client_demo.py first.")
            return

        existing_rows = (
            await session.execute(
                select(File).where(
                    File.filename.like("case-study_%"),
                    File.scope == LIBRARY_SCOPE,
                )
            )
        ).scalars().all()
        existing_by_filename = {f.filename: f for f in existing_rows}
        existing_filenames = set(existing_by_filename)

        storage_root = Path(get_settings().file_storage_dir)
        created = 0
        skipped = 0
        refreshed = 0
        cataloged = 0

        for path in files:
            filename = path.name
            if filename in existing_filenames:
                row = existing_by_filename[filename]
                new_sha = hashlib.sha256(path.read_bytes()).hexdigest()
                if not refresh or row.sha256_hash == new_sha:
                    # Unchanged content, but a case seeded before cataloguing
                    # moved here still has no catalog row and would be
                    # invisible to seed_case_tags.py. Fill that gap without
                    # touching a row that already exists.
                    if await upsert_catalog_if_missing(session, row.id, None, path):
                        cataloged += 1
                    skipped += 1
                    continue
                # Content changed on disk (a corpus rebuild). Replace the blob
                # and re-chunk IN PLACE, keeping the same file_id: the id is
                # referenced by agent_files, case_studies and every historical
                # case_matches row, so re-uploading as a new file would orphan
                # a client's past match history and silently double the corpus.
                await refresh_file(
                    session, row, path, owner.id, None, storage_root
                )
                refreshed += 1
                continue

            data = path.read_bytes()
            file_id = uuid.uuid4()
            dest = ingestion.save_upload(owner.id, file_id, filename, data)
            try:
                s3_key = dest.relative_to(storage_root).as_posix()
            except ValueError:
                s3_key = str(dest)

            db_file = File(
                id=file_id,
                user_id=owner.id,
                filename=filename,
                mime_type="text/markdown",
                size_bytes=len(data),
                s3_key=s3_key,
                is_processed=False,
                scope=LIBRARY_SCOPE,
                workspace_id=None,
                source="upload",
            )
            session.add(db_file)
            await session.commit()

            await ingestion.process_file(file_id)
            await upsert_catalog(session, file_id, None, data)
            created += 1

        # Attach every library case-study file to the workspace's agent —
        # not just the ones just created, so a partially-linked prior run
        # (e.g. interrupted before step 4) gets finished too.
        all_case_file_ids = (
            await session.execute(
                select(File.id).where(
                    File.filename.like("case-study_%"),
                    File.scope == LIBRARY_SCOPE,
                )
            )
        ).scalars().all()
        attached_ids = set(
            (
                await session.execute(
                    select(AgentFile.file_id).where(AgentFile.agent_id == agent.id)
                )
            ).scalars().all()
        )
        new_links = [
            AgentFile(agent_id=agent.id, file_id=fid)
            for fid in all_case_file_ids
            if fid not in attached_ids
        ]
        session.add_all(new_links)
        await session.commit()
        linked = len(new_links)

        null_embeddings = (
            await session.execute(
                select(FileChunk.id)
                .join(File, FileChunk.file_id == File.id)
                .where(
                    File.filename.like("case-study_%"),
                    File.scope == LIBRARY_SCOPE,
                    FileChunk.embedding.is_(None),
                )
            )
        ).scalars().all()

        print(f"files created: {created}")
        print(f"files refreshed (content changed): {refreshed}")
        print(f"catalog rows added for existing files: {cataloged}")
        print(f"files skipped (already present, unchanged): {skipped}")
        print(f"agent links added: {linked}")
        print(f"chunks with null embedding: {len(null_embeddings)}")

        if null_embeddings:
            print(
                "ERROR: embed server appears to be unreachable — chunks were stored "
                "without embeddings and will never surface in /client/cases. "
                "Fix the embed server and re-run (idempotent)."
            )
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
