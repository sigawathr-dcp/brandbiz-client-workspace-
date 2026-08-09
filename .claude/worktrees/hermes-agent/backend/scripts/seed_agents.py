"""Seed True AI Hub agents into the agents table.

Creates one seed user per distinct author, then idempotently inserts each
agent record using app.services.agent.create_agent (gives audit rows for free).

Re-runnable: agents already present (matched by user_id + name) are skipped.

Run from inside the backend-api container:
    docker compose exec backend-api python scripts/seed_agents.py
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure /app (the backend root) is on sys.path when run as a standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import engine
from app.llm.router import LOCAL_MODEL_CODE
from app.models.agent import Agent
from app.models.user import User
from app.services import agent as agent_svc

_SESSION = async_sessionmaker(engine, expire_on_commit=False)

# Seed users keyed by display_name → (email, role)
_SEED_USERS: dict[str, tuple[str, str]] = {
    "Core Admin":         ("core-admin@truehub.seed",      "ADMIN"),
    "test_core_admin":    ("test-core-admin@truehub.seed", "ADMIN"),
    "ศิกวัฒฐ รุ่งเรือง": ("sikwat-r@truehub.seed",        "ADMIN"),
}

_DATA_FILE = Path(__file__).parent / "seed_data" / "agents.json"


async def _upsert_user(session, display_name: str) -> User:
    """Lookup or create a seed user by display_name."""
    email, role = _SEED_USERS[display_name]
    result = await session.execute(
        select(User).where(User.google_email == email)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            google_email=email,
            display_name=display_name,
            role=role,
            is_active=True,
            consent_acknowledged_at=datetime.now(timezone.utc),
        )
        session.add(user)
        await session.flush()
        print(f"  Created user: {display_name} <{email}>")
    else:
        print(f"  Existing user: {display_name} <{email}>")
    return user


async def _agent_exists(session, user_id, name: str) -> bool:
    result = await session.execute(
        select(Agent.id).where(
            Agent.user_id == user_id,
            Agent.name == name,
        )
    )
    return result.scalar_one_or_none() is not None


async def main() -> None:
    records = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    print(f"Loaded {len(records)} agent records from seed_data/agents.json")

    # Collect distinct authors
    authors = {r["author"] for r in records}
    unknown = authors - set(_SEED_USERS)
    if unknown:
        raise ValueError(f"Unknown author(s) in seed data: {unknown}")

    async with _SESSION() as session:
        async with session.begin():
            # Upsert all seed users
            print("\n--- Users ---")
            users: dict[str, User] = {}
            for display_name in sorted(_SEED_USERS):
                if display_name in authors:
                    users[display_name] = await _upsert_user(session, display_name)

        created = 0
        skipped = 0

        print("\n--- Agents ---")
        for rec in records:
            author = rec["author"]
            name = rec["name"]
            user = users[author]

            async with _SESSION() as session:
                if await _agent_exists(session, user.id, name):
                    print(f"  SKIP  {name!r}")
                    skipped += 1
                    continue

                caps = rec.get("capabilities") or {}
                # Ignore the export's per-agent provider/model — all agents run
                # on the local model since migration 0024_agents_local_model.
                await agent_svc.create_agent(
                    session=session,
                    user=user,
                    name=name,
                    provider="local",
                    model=LOCAL_MODEL_CODE,
                    description=rec.get("description"),
                    instructions=rec.get("instructions"),
                    capabilities=caps,
                    creativity_level=rec.get("creativity_level", 0),
                    visibility="public",
                    status="published",
                    category=rec.get("category"),
                )
                print(f"  OK    {name!r}")
                created += 1

    print(f"\nDone — {created} created, {skipped} skipped.")


if __name__ == "__main__":
    asyncio.run(main())
