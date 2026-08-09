import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False: alembic_command.upgrade() runs from
    # app/main.py's startup on every boot (incl. every --reload restart), in
    # the same process as the FastAPI app. fileConfig()'s default
    # (disable_existing_loggers=True) silently disables every logger not
    # declared in alembic.ini's [loggers] section — including
    # uvicorn.access/uvicorn.error and every app.* logger — for the rest of
    # that process's life. This was observed directly: no per-request log
    # line (access logs or app warnings) ever reached stdout/stderr, only
    # the handful of loggers alembic.ini itself declares (root, sqlalchemy,
    # alembic). Standard footgun when fileConfig() is invoked
    # programmatically rather than from the standalone `alembic` CLI.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Build URL from env vars — overrides the %(VAR)s placeholder in alembic.ini.
# When ORM models are added (Task 1.3+), replace None with Base.metadata.
_url = (
    "postgresql+asyncpg://"
    f"{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
    f"@{os.environ['POSTGRES_HOST']}:{os.environ.get('POSTGRES_PORT', '5432')}"
    f"/{os.environ['POSTGRES_DB']}"
)
config.set_main_option("sqlalchemy.url", _url)

target_metadata = None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
