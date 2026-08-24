"""Mint N client-workspace invites and print ready-to-use /try/<token> links.

Batch version of the single invite seed_client_demo.py prints at the end of a
seed run — for handing out test links to a group (e.g. 30 testers at an event)
without re-running the whole demo seeder.

Raw tokens are shown ONCE (client_invites stores only the SHA-256 hash, see
app/models/client_invite.py), so capture the output; it cannot be recovered.

Run from inside the backend-api container:
    docker compose exec backend-api python scripts/mint_invites.py --count 30
    docker compose exec backend-api python scripts/mint_invites.py \
        --count 30 --base-url https://demo.example.com --expires-hours 168 \
        --out /tmp/invites.csv
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import engine
from app.models.user import User
from app.models.workspace import Workspace
from app.services import workspace as workspace_svc

_SESSION = async_sessionmaker(engine, expire_on_commit=False)

DEFAULT_SLUG = "brandbiz-demo"
DEFAULT_BASE_URL = "http://localhost:3100"
SEED_ADMIN_EMAIL = "demo-seeder@brandbiz.seed"


async def _resolve_admin(session) -> User:
    """Prefer the seeder account so these invites are attributable to the same
    identity seed_client_demo.py uses; fall back to any active admin."""
    user = (await session.execute(
        select(User).where(User.google_email == SEED_ADMIN_EMAIL)
    )).scalar_one_or_none()
    if user is not None:
        return user
    user = (await session.execute(
        select(User).where(User.role == "ADMIN", User.is_active.is_(True)).order_by(User.created_at)
    )).scalars().first()
    if user is None:
        raise SystemExit(
            "No admin user found. Run scripts/seed_client_demo.py first (it creates "
            f"{SEED_ADMIN_EMAIL})."
        )
    return user


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=30, help="how many invites to mint (default 30)")
    parser.add_argument("--slug", default=DEFAULT_SLUG, help=f"workspace slug (default {DEFAULT_SLUG})")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help=f"frontend origin the links point at (default {DEFAULT_BASE_URL})")
    parser.add_argument("--expires-hours", type=int, default=24 * 14,
                        help="invite lifetime in hours (default 336 = 14 days)")
    parser.add_argument("--label-prefix", default="Tester",
                        help="contact_name prefix stamped on each invite (default 'Tester')")
    parser.add_argument("--out", default=None, help="also write a CSV (n,contact_name,url,expires_at) here")
    args = parser.parse_args()

    if args.count < 1:
        raise SystemExit("--count must be >= 1")
    base = args.base_url.rstrip("/")

    async with _SESSION() as session:
        workspace = (await session.execute(
            select(Workspace).where(Workspace.slug == args.slug)
        )).scalar_one_or_none()
        if workspace is None:
            raise SystemExit(f"No workspace with slug {args.slug!r}. Run scripts/seed_client_demo.py first.")
        if workspace.archived_at is not None:
            raise SystemExit(f"Workspace {args.slug!r} is archived — create_invite() would 404.")
        admin = await _resolve_admin(session)

        print(f"Workspace: {workspace.name} ({workspace.id})")
        print(f"Minted by: {admin.google_email} ({admin.id})")
        print(f"Minting {args.count} invite(s), expiring in {args.expires_hours}h\n")

        rows = []
        for n in range(1, args.count + 1):
            contact = f"{args.label_prefix} {n:02d}"
            invite, raw = await workspace_svc.create_invite(
                session,
                workspace_id=workspace.id,
                created_by=admin.id,
                expires_in_hours=args.expires_hours,
                contact_name=contact,
            )
            url = f"{base}/try/{raw}"
            rows.append((n, contact, url, invite.expires_at.isoformat()))
            print(f"{n:02d}  {url}")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        lines = ["n,contact_name,url,expires_at"]
        lines += [f"{n},{contact},{url},{exp}" for n, contact, url, exp in rows]
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\nWrote {len(rows)} row(s) to {out}")

    print("\nEach link is single-use: /try/<token> redeems into one seat and marks the invite spent.")
    print("Raw tokens are not stored — this output is the only copy.")


if __name__ == "__main__":
    asyncio.run(main())
