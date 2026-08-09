from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
_session_factory = async_sessionmaker(engine, expire_on_commit=False)

# Public alias used by the FastAPI lifespan handler and any startup code that
# needs a session outside of a request context.
session_factory = _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        yield session
