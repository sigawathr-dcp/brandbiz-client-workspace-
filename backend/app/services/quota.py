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
from app.models.workspace import Workspace


async def resolve_monthly_token_limit(session: AsyncSession, user: User) -> int:
    """Single source of truth for a user's monthly token ceiling.

    Precedence: workspaces.monthly_token_limit (client seats, when the
    workspace sets one) -> quota_defaults[user.role]. This used to be
    copy-pasted three times — here, in PolicyEngine._get_or_create_current_
    quota, and (with the wrong precedence — role only, ignoring the
    workspace override) in GET /quota/me. All three used ON CONFLICT DO
    NOTHING when first-creating the month's Quota row, so whichever one ran
    first for a given user silently won; a client seat that hit
    GET /quota/me before its first chat got the L1 role default (50k)
    permanently pinned instead of its workspace's limit (D23).
    """
    default_limit: int | None = None
    if user.workspace_id is not None:
        default_limit = (await session.execute(
            select(Workspace.monthly_token_limit).where(Workspace.id == user.workspace_id)
        )).scalar_one_or_none()
    if default_limit is None:
        default_limit = (await session.execute(
            select(QuotaDefault.monthly_token_limit).where(QuotaDefault.role == user.role)
        )).scalar_one()
    return default_limit


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

    # Look up the default (needed when the row must be created).
    default_limit = await resolve_monthly_token_limit(session, user)

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

    # D21/D22: debit the pooled workspace budget alongside the per-seat one.
    # Same atomic-UPDATE pattern; a NULL token_budget_limit workspace still
    # accumulates token_budget_used (harmless — PolicyEngine only compares
    # against the limit when it is set).
    if user.workspace_id is not None:
        await session.execute(
            update(Workspace)
            .where(Workspace.id == user.workspace_id)
            .values(token_budget_used=Workspace.token_budget_used + total)
        )

    await session.commit()

    # Re-select post-commit to return the authoritative row state
    return (await session.execute(
        select(Quota).where(
            Quota.user_id == user.id,
            Quota.period_start == period_start,
        )
    )).scalar_one()
