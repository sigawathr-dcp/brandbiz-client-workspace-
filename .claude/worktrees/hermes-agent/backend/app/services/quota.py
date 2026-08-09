"""
app/services/quota.py

Monthly quota enforcement — the only module that writes to the ``quotas`` table.

Key properties
--------------
* Auto-creates the current-month quota row on first call using ``quota_defaults``.
* Atomic UPDATE prevents double-spend: Postgres row-level locking serialises
  concurrent increments even across separate ``AsyncSession`` instances.
* Quota is consumed ONLY for external API calls.  Callers (the orchestrator)
  are responsible for skipping this service when the model is local.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quota import Quota, QuotaDefault
from app.models.user import User


async def consume(
    session: AsyncSession,
    user: User,
    tokens_input: int,
    tokens_output: int,
    cost_usd: Decimal,
) -> Quota:
    """Atomically record token + cost usage for the user's current monthly period.

    Idempotency: if no quota row exists for this month, one is created from
    ``quota_defaults`` before the increment.  Concurrent first-callers race
    safely on ``UNIQUE(user_id, period_start)`` via ON CONFLICT DO NOTHING.

    The UPDATE atomically increments ``tokens_used`` and ``cost_used_usd``;
    Postgres row-level locking guarantees no lost updates under concurrency.
    """
    period_start = date.today().replace(day=1)
    total = tokens_input + tokens_output

    # Look up the role default (needed when the row must be created)
    default_limit: int = (await session.execute(
        select(QuotaDefault.monthly_token_limit).where(QuotaDefault.role == user.role)
    )).scalar_one()

    # Ensure the row exists; concurrent callers serialise on the UNIQUE constraint
    await session.execute(
        pg_insert(Quota)
        .values(
            user_id=user.id,
            period_start=period_start,
            tokens_limit=default_limit,
            tokens_used=0,
            cost_used_usd=Decimal("0"),
        )
        .on_conflict_do_nothing(index_elements=["user_id", "period_start"])
    )

    # Atomic increment — UPDATE row lock prevents double-spend
    await session.execute(
        update(Quota)
        .where(Quota.user_id == user.id, Quota.period_start == period_start)
        .values(
            tokens_used=Quota.tokens_used + total,
            cost_used_usd=Quota.cost_used_usd + cost_usd,
        )
    )
    await session.commit()

    # Re-select post-commit to return the authoritative row state
    return (await session.execute(
        select(Quota).where(
            Quota.user_id == user.id,
            Quota.period_start == period_start,
        )
    )).scalar_one()
