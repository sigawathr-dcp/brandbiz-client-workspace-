"""D14 (PLAN.md Decisions Log) — drop messages.content_* older than 30 days.

Calls app.services.retention.purge_expired_messages(), the same function a
future scheduled job would call. This repo has no running Celery worker
(see backend/app/workers/, empty besides __init__.py), so until one exists,
run this daily from cron / Windows Task Scheduler:

    docker compose exec backend-api python scripts/purge_expired_messages.py
    docker compose exec backend-api python scripts/purge_expired_messages.py --dry-run
    docker compose exec backend-api python scripts/purge_expired_messages.py --retention-days 30
"""

import argparse
import asyncio


async def main(retention_days: int, dry_run: bool) -> None:
    from app.db import session_factory
    from app.services import retention

    async with session_factory() as session:
        if dry_run:
            pending = await retention.count_pending_purge(session, retention_days=retention_days)
            print(f"{pending} message(s) would be purged (retention_days={retention_days}). Dry run — nothing changed.")
            return

        purged = await retention.purge_expired_messages(session, retention_days=retention_days)
        print(f"Purged content for {purged} message(s) older than {retention_days} days.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retention-days", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true", help="Report the count without purging")
    args = parser.parse_args()
    asyncio.run(main(args.retention_days, args.dry_run))
