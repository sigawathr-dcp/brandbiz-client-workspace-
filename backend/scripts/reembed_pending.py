"""Re-run ingestion for files whose chunks are missing embeddings.

Useful after the embed server (LLM_EMBED_URL) was unreachable during upload:
ingestion stores chunks with embedding=NULL, which makes them invisible to
RAG retrieval until re-embedded. ``process_file`` is idempotent, so this
simply re-triggers it for every affected file.

Run from inside the backend-api container:
    docker compose exec backend-api python scripts/reembed_pending.py
"""

import asyncio

from sqlalchemy import distinct, select

from app.models.file import File, FileChunk
from app.services.ingestion import process_file


async def main() -> None:
    from app.db import session_factory

    async with session_factory() as session:
        stmt = (
            select(distinct(FileChunk.file_id), File.filename)
            .join(File, FileChunk.file_id == File.id)
            .where(FileChunk.embedding.is_(None))
        )
        rows = (await session.execute(stmt)).all()

    if not rows:
        print("No files with missing embeddings — nothing to do.")
        return

    print(f"{len(rows)} file(s) need re-embedding:")
    for file_id, filename in rows:
        print(f"  - {filename} ({file_id})")

    for file_id, filename in rows:
        print(f"re-ingesting {filename} ...")
        await process_file(file_id)

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
