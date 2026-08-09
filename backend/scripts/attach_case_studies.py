"""Make the uploaded case-study files visible to client seats (Phase 5).

The 30 `case-study_*.md` files were uploaded through the normal internal
upload UI, which leaves them org-scoped with workspace_id = NULL — the
internal corpus. `workspace_visibility_filter` (IS NOT DISTINCT FROM)
therefore hides them from every client seat, so `/client/cases` always
returns zero matches (the gap noted in run_case_match's docstring).

This script finishes the manual step called out in PLAN.md 5.x /
seed_client_demo.py's reminder:
  1. move the case-study files into the demo workspace, and
  2. attach them to the demo agent (agent_files), so case matching
     searches exactly the case library and nothing else.

Idempotent — re-running is a no-op. Run from inside the container:
    docker compose exec backend-api sh -c \
        "cd /app && PYTHONPATH=/app python scripts/attach_case_studies.py"
"""
import asyncio
import uuid

from sqlalchemy import select, update

from app.models.agent import AgentFile
from app.models.file import File
from app.models.workspace import Workspace

DEMO_WORKSPACE_SLUG = "brandbiz-demo"
DEMO_AGENT_ID = uuid.UUID("86fe9258-b65a-40ea-880f-805036969f12")
CASE_FILE_PREFIX = "case-study"


async def main() -> None:
    from app.db import session_factory

    async with session_factory() as session:
        ws_id = (
            await session.execute(
                select(Workspace.id).where(Workspace.slug == DEMO_WORKSPACE_SLUG)
            )
        ).scalar_one_or_none()
        if ws_id is None:
            print(f"Workspace '{DEMO_WORKSPACE_SLUG}' not found — run seed_client_demo.py first.")
            return

        moved = await session.execute(
            update(File)
            .where(File.filename.like(f"{CASE_FILE_PREFIX}%"), File.scope == "org")
            .values(workspace_id=ws_id)
        )
        print(f"files moved into workspace {ws_id}: {moved.rowcount}")

        case_file_ids = (
            await session.execute(
                select(File.id).where(File.filename.like(f"{CASE_FILE_PREFIX}%"))
            )
        ).scalars().all()
        attached_ids = set(
            (
                await session.execute(
                    select(AgentFile.file_id).where(AgentFile.agent_id == DEMO_AGENT_ID)
                )
            ).scalars().all()
        )
        new_links = [
            AgentFile(agent_id=DEMO_AGENT_ID, file_id=fid)
            for fid in case_file_ids
            if fid not in attached_ids
        ]
        session.add_all(new_links)
        await session.commit()
        print(f"files newly attached to agent {DEMO_AGENT_ID}: {len(new_links)}")


if __name__ == "__main__":
    asyncio.run(main())
