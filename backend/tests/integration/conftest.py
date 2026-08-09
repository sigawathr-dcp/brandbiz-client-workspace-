"""
Integration test conftest — spins up a real Postgres via pytest-docker.

Usage:
    python -m pytest backend/tests/integration/ -q   # Docker must be running
"""
import asyncio
import os
import socket
import sys
from pathlib import Path

# ── Remove unit-test stubs so real asyncpg/redis drivers are importable ──────
for _stub in ("asyncpg", "redis", "redis.asyncio", "app.db"):
    sys.modules.pop(_stub, None)

# ── Env vars required before any app Settings() is constructed ───────────────
os.environ.setdefault("POSTGRES_PASSWORD", "test")
# 32-byte AES-256 key (base64 of 32 null bytes) — valid for AESGCM in tests
os.environ.setdefault("ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

HERE = Path(__file__).parent

_PG_PORT = 5433
_PG_USER = "test"
_PG_PASS = "test"
_PG_DB   = "test_brandbiz"

# ── ENUM DDL (Alembic 0001_baseline normally creates these) ──────────────────
_ENUM_DDL = [
    """DO $$ BEGIN
        CREATE TYPE role_level AS ENUM ('L1','L2','L3','L4','L5','L6','ADMIN');
    EXCEPTION WHEN duplicate_object THEN NULL; END $$""",
    """DO $$ BEGIN
        CREATE TYPE model_provider AS ENUM
            ('local','anthropic','openai','google','perplexity');
    EXCEPTION WHEN duplicate_object THEN NULL; END $$""",
    """DO $$ BEGIN
        CREATE TYPE data_tier AS ENUM
            ('TIER_1_PUBLIC','TIER_2_INTERNAL','TIER_3_CONFIDENTIAL','TIER_4_RESTRICTED');
    EXCEPTION WHEN duplicate_object THEN NULL; END $$""",
    """DO $$ BEGIN
        CREATE TYPE message_role AS ENUM ('user','assistant','system','tool');
    EXCEPTION WHEN duplicate_object THEN NULL; END $$""",
    """DO $$ BEGIN
        CREATE TYPE audit_action AS ENUM (
            'login','logout','message_sent','message_received',
            'model_blocked','pii_detected','tier_blocked','quota_exceeded',
            'reveal_requested','reveal_approved','reveal_denied','reveal_viewed',
            'admin_user_created','admin_role_changed','admin_quota_changed',
            'admin_permission_changed','file_uploaded','rag_query',
            'consent_acknowledged',
            'vault_note_ingested','vault_note_updated','vault_note_deleted',
            'vault_note_quarantined',
            'vault_connection_updated','vault_sync_triggered',
            'vault_sync_completed','vault_sync_failed',
            'client_invited','client_redeemed','intake_answered','research_run',
            'case_matched','plan_created','plan_updated','plan_shared',
            'plan_exported','lead_submitted'
        );
    EXCEPTION WHEN duplicate_object THEN NULL; END $$""",
    """DO $$ BEGIN
        CREATE TYPE reveal_status AS ENUM
            ('pending','approved','denied','expired','completed');
    EXCEPTION WHEN duplicate_object THEN NULL; END $$""",
]

_SEED_SQL = """
    INSERT INTO quota_defaults (role, monthly_token_limit) VALUES
        ('L1', 50000), ('L2', 200000), ('L3', 500000),
        ('L4', 1000000), ('L5', 2000000),
        ('L6', 9223372036854775807), ('ADMIN', 9223372036854775807)
    ON CONFLICT (role) DO NOTHING
"""


async def _create_schema(url: str) -> None:
    """Create the pgvector extension, ENUMs, all tables, and seed
    quota_defaults once."""
    from app.models import Base  # imported here to keep module-level clean

    engine = create_async_engine(url, echo=False)
    async with engine.begin() as conn:
        # file_chunks.embedding is a pgvector VECTOR(1024) column
        # (app/models/file.py) — the pgvector/pgvector:pg16 image ships the
        # extension but doesn't enable it per-database automatically, so
        # Base.metadata.create_all's CREATE TABLE file_chunks fails with
        # "type vector does not exist" without this.
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        for ddl in _ENUM_DDL:
            await conn.execute(text(ddl))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(_SEED_SQL))
    await engine.dispose()


# ── pytest-docker fixtures ────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def docker_compose_file() -> str:
    return str(HERE / "docker-compose.yml")


@pytest.fixture(scope="session")
def docker_compose_project_name() -> str:
    return "brandbiz-inttest"


@pytest.fixture(scope="session")
def pg_url(docker_ip, docker_services) -> str:  # type: ignore[no-untyped-def]
    """Wait until Postgres is accepting connections, then return the async URL."""
    def _ready() -> bool:
        try:
            with socket.create_connection((docker_ip, _PG_PORT), timeout=1.0):
                return True
        except OSError:
            return False

    docker_services.wait_until_responsive(timeout=30.0, pause=0.5, check=_ready)
    return (
        f"postgresql+asyncpg://{_PG_USER}:{_PG_PASS}"
        f"@{docker_ip}:{_PG_PORT}/{_PG_DB}"
    )


@pytest.fixture(scope="session")
def db_engine_sync(pg_url: str) -> str:
    """Create schema (sync wrapper around async setup) — runs once per session."""
    asyncio.run(_create_schema(pg_url))
    return pg_url


# ── Per-test helpers ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def async_engine(db_engine_sync: str):
    engine = create_async_engine(db_engine_sync, echo=False)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine) -> AsyncSession:
    """Function-scoped session; rolls back after each test."""
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()
