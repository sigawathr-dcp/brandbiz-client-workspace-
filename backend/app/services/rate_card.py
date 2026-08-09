"""
app/services/rate_card.py

Structural fix for the plan's budget correctness risk: the design pins a
skill saying "refuse any line without a rate-card row", which is a
prompt-level control a local model will violate. Here it's structural — the
model (app/services/plan.py::draft_plan) emits ONLY {code, qty} pairs, never
a THB amount, and price() below is the one place that turns a code into
money, by looking it up in rate_card_items. A code with no matching active
row becomes a "needs_expert" line instead of a fabricated number.
"""
from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rate_card import RateCardItem

CONTINGENCY_RATE = Decimal("0.10")


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def price(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    items: list[dict],
) -> dict:
    """items: [{"code": str, "qty": number}, ...] — as emitted by the model.

    Returns:
        {
            "lines": [{"code","label","section","unit","qty","unit_price","amount"}],
            "needs_expert": [{"code","qty"}],   # codes with no active rate-card row
            "subtotal": "0.00", "contingency": "0.00", "total": "0.00",
            "currency": "THB",
        }
    All money values are strings (Decimal is not JSON-serialisable; JSONB
    storage and the frontend both want a fixed-point string, not a float).
    """
    codes = {str(i.get("code", "")).strip() for i in items if i.get("code")}
    rows: dict[str, RateCardItem] = {}
    if codes:
        result = await session.execute(
            select(RateCardItem).where(
                RateCardItem.code.in_(codes),
                RateCardItem.active.is_(True),
                # Workspace-specific row wins over the shared/default one —
                # resolved below by preferring a non-NULL workspace_id match.
                or_(RateCardItem.workspace_id == workspace_id, RateCardItem.workspace_id.is_(None)),
            )
        )
        for row in result.scalars().all():
            existing = rows.get(row.code)
            if existing is None or (existing.workspace_id is None and row.workspace_id is not None):
                rows[row.code] = row

    lines: list[dict] = []
    needs_expert: list[dict] = []
    subtotal = Decimal("0")
    currency = "THB"

    for item in items:
        code = str(item.get("code", "")).strip()
        try:
            qty = Decimal(str(item.get("qty", 1)))
        except Exception:
            qty = Decimal("1")
        if qty <= 0:
            qty = Decimal("1")

        row = rows.get(code)
        if row is None:
            needs_expert.append({"code": code, "qty": str(qty)})
            continue

        amount = _q2(row.unit_price * qty)
        subtotal += amount
        currency = row.currency
        lines.append({
            "code": row.code,
            "label": row.label,
            "section": row.section,
            "unit": row.unit,
            "qty": str(qty),
            "unit_price": str(_q2(row.unit_price)),
            "amount": str(amount),
        })

    contingency = _q2(subtotal * CONTINGENCY_RATE)
    total = subtotal + contingency

    return {
        "lines": lines,
        "needs_expert": needs_expert,
        "subtotal": str(_q2(subtotal)),
        "contingency": str(contingency),
        "total": str(_q2(total)),
        "currency": currency,
    }
