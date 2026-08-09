"""Seed a dev user and print a signed JWT for local E2E testing.

Run from inside the backend-api container:
    docker compose exec backend-api python scripts/seed_and_token.py
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import engine
from app.models.user import User
from app.routers.auth import _create_jwt

EMAIL = "dev@company.local"

_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def main() -> None:
    async with _session_factory() as session:
        result = await session.execute(select(User).where(User.google_email == EMAIL))
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                google_email=EMAIL,
                display_name="Dev User",
                role="L1",
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            print(f"Created user: {user.id}")
        else:
            print(f"Existing user: {user.id}")

    token = _create_jwt(user)
    print(f"USER_ID={user.id}")
    print(f"ACCESS_TOKEN={token}")


if __name__ == "__main__":
    asyncio.run(main())
