"""
Integration test: assert SQLAlchemy model enum matches Postgres audit_action enum.

Why this matters: SQLAlchemy's PgEnum validates labels on READ. If the model
is missing a label that exists in the DB (added by a later migration), every
SELECT on audit_log raises LookupError → HTTP 500 → Audit Log shows 0 entries.

This test fails fast whenever a migration adds a new audit_action value but
the model is not updated in sync, so the bug can never ship silently again.

Run:
    pytest backend/tests/integration/test_audit_enum_sync.py -v
"""
from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit import _audit_action_pg

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://brandbiz:12345@localhost:5432/brandbiz",
)


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_audit_action_enum_in_sync_with_db(db_session: AsyncSession) -> None:
    """Model _audit_action_pg.enums must be a superset of (ideally equal to) the DB enum."""
    result = await db_session.execute(
        text(
            "SELECT e.enumlabel "
            "FROM pg_enum e "
            "JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname = 'audit_action' "
            "ORDER BY e.enumsortorder"
        )
    )
    db_labels: set[str] = {row[0] for row in result.fetchall()}
    model_labels: set[str] = set(_audit_action_pg.enums)

    missing_from_model = db_labels - model_labels
    assert not missing_from_model, (
        f"These audit_action labels exist in Postgres but are missing from "
        f"_audit_action_pg in app/models/audit.py — add them to fix the "
        f"LookupError that makes the Audit Log viewer crash (HTTP 500):\n"
        f"  {sorted(missing_from_model)}"
    )
