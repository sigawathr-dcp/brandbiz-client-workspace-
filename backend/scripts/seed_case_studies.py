"""Ingest the case-study library into the demo workspace (Phase 5, D21/D22).

`seed_client_demo.py` deliberately does not seed case studies ("needs real
files" — see its module docstring); this script is that follow-up step,
made scriptable instead of manual.

It regenerates as `case-study_<slug>.md`, one per campaign, from
`Brandbiz_Data/works.json` via `Brandbiz_Data/make_case_studies.py` (run
that first — see "Usage" below), then for each file:
  1. writes the blob via the existing `app.services.ingestion.save_upload`
     (same path POST /files uses),
  2. inserts a `files` row with scope="org" and workspace_id stamped to the
     demo workspace — required under D21/D22:
     `workspace_visibility_filter` uses `column IS NOT DISTINCT FROM`, so a
     client seat never sees workspace_id=NULL (internal-shared) rows,
  3. runs it through `app.services.ingestion.process_file` — chunk, embed,
     mark processed — unchanged, so this is exactly the pipeline a real
     upload goes through, and
  4. links it to the workspace's agent via `AgentFile`, resolved through
     `app.services.workspace.get_workspace_agent` (the same lookup
     POST /client/cases uses) rather than a hardcoded agent id — a
     hardcoded id silently breaks the moment the demo agent is re-seeded.

Idempotent: a file already present for this workspace (matched by
filename + workspace_id) is left untouched — not re-uploaded, not
re-embedded, not re-linked.

Usage — run from the repo root on the host, then inside the container:
    python ../Brandbiz_Data/make_case_studies.py
    docker cp ../Brandbiz_Data/case_studies \\
        brandbiz-client-workspace-backend-api-1:/data/seed/case_studies
    docker compose exec backend-api sh -c \\
        "cd /app && PYTHONPATH=/app python scripts/seed_case_studies.py"

Optional args: `python scripts/seed_case_studies.py [source_dir] [workspace_slug]`
(defaults: /data/seed/case_studies, brandbiz-demo).
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.models.agent import AgentFile
from app.models.file import File, FileChunk
from app.models.user import User
from app.models.workspace import Workspace
from app.services import ingestion
from app.services.workspace import get_workspace_agent

DEFAULT_SOURCE_DIR = "/data/seed/case_studies"
DEFAULT_WORKSPACE_SLUG = "brandbiz-demo"
SEED_ADMIN_EMAIL = "demo-seeder@brandbiz.seed"  # owner of record — see seed_client_demo.py


async def main() -> None:
    source_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(DEFAULT_SOURCE_DIR)
    workspace_slug = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_WORKSPACE_SLUG

    files = sorted(source_dir.glob("case-study_*.md"))
    if not files:
        print(f"No case-study_*.md files found under {source_dir} — nothing to do.")
        print("Run Brandbiz_Data/make_case_studies.py and docker cp the output first (see module docstring).")
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

        existing_filenames = set(
            (
                await session.execute(
                    select(File.filename).where(
                        File.filename.like("case-study_%"),
                        File.workspace_id == workspace.id,
                    )
                )
            ).scalars().all()
        )

        storage_root = Path(get_settings().file_storage_dir)
        created = 0
        skipped = 0

        for path in files:
            filename = path.name
            if filename in existing_filenames:
                skipped += 1
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
                scope="org",
                workspace_id=workspace.id,
                source="upload",
            )
            session.add(db_file)
            await session.commit()

            await ingestion.process_file(file_id)
            created += 1

        # Attach every case-study file for this workspace to its agent —
        # not just the ones just created, so a partially-linked prior run
        # (e.g. interrupted before step 4) gets finished too.
        all_case_file_ids = (
            await session.execute(
                select(File.id).where(
                    File.filename.like("case-study_%"),
                    File.workspace_id == workspace.id,
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
                    File.workspace_id == workspace.id,
                    FileChunk.embedding.is_(None),
                )
            )
        ).scalars().all()

        print(f"files created: {created}")
        print(f"files skipped (already present): {skipped}")
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
