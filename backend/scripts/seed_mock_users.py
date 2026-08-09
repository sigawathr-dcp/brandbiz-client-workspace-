"""Seed mock username/password accounts for local login (one per role).

Run from inside the backend-api container:
    docker compose exec backend-api python -m scripts.seed_mock_users

Only useful while GOOGLE_OAUTH_CLIENT_ID is unset — POST /auth/login rejects
password logins once real Google OAuth is configured.
"""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import engine
from app.models.user import User
from app.services.password import hash_password

MOCK_PASSWORD = "Passw0rd!"  # noqa: S105 — mock/demo credential, not a real secret

MOCK_USERS = [
    {"username": "l1.associate", "email": "l1.associate@company.local", "role": "L1"},
    {"username": "l2.analyst", "email": "l2.analyst@company.local", "role": "L2"},
    {"username": "l3.senior", "email": "l3.senior@company.local", "role": "L3"},
    {"username": "l4.lead", "email": "l4.lead@company.local", "role": "L4"},
    {"username": "l5.manager", "email": "l5.manager@company.local", "role": "L5"},
    {"username": "l6.director", "email": "l6.director@company.local", "role": "L6"},
    {"username": "admin", "email": "admin@company.local", "role": "ADMIN"},
]

_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def main() -> None:
    password_hash = hash_password(MOCK_PASSWORD)

    async with _session_factory() as session:
        for spec in MOCK_USERS:
            result = await session.execute(
                select(User).where(User.username == spec["username"])
            )
            user = result.scalar_one_or_none()

            if user is None:
                user = User(
                    username=spec["username"],
                    google_email=spec["email"],
                    display_name=spec["username"],
                    role=spec["role"],
                    password_hash=password_hash,
                )
                session.add(user)
                print(f"Created {spec['username']} ({spec['role']})")
            else:
                user.password_hash = password_hash
                user.role = spec["role"]
                print(f"Updated {spec['username']} ({spec['role']})")

        await session.commit()

    print(f"\nAll mock accounts share password: {MOCK_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
