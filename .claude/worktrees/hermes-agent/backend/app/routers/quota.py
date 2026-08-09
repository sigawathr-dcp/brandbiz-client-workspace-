from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models.quota import Quota, QuotaDefault
from app.models.user import User

router = APIRouter(prefix="/quota", tags=["quota"])


class QuotaStatus(BaseModel):
    tokens_used: int
    tokens_limit: int
    cost_used_usd: str   # string to avoid float precision issues
    period_start: str


@router.get("/me", response_model=QuotaStatus)
async def my_quota(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> QuotaStatus:
    """Return the authenticated user's quota for the current month.

    Creates the quota row on first call (same upsert logic as quota service).
    """
    period_start = date.today().replace(day=1)

    default_limit: int = (await session.execute(
        select(QuotaDefault.monthly_token_limit).where(QuotaDefault.role == user.role)
    )).scalar_one()

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
    await session.flush()

    row = (await session.execute(
        select(Quota).where(
            Quota.user_id == user.id,
            Quota.period_start == period_start,
        )
    )).scalar_one()

    return QuotaStatus(
        tokens_used=row.tokens_used,
        tokens_limit=row.tokens_limit,
        cost_used_usd=str(row.cost_used_usd),
        period_start=period_start.isoformat(),
    )
