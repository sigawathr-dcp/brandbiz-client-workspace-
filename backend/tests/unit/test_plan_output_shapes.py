"""Unit tests for plan_svc.budget_out()/provenance_out() — the adapters
that reassemble the old JSON-shaped API contract
({"lines": [...], "subtotal": ...} / {"rate_card_codes": [...], ...}) from
the normalized PlanBudgetLine/PlanSource rows (DB redesign).

Supersedes the pre-redesign test_client_router_plan_version.py, which
pinned the ROUTER's own "v.title or plan.title" fallback for a version
saved before migration 0049. That fallback doesn't exist anymore because
the problem it patched over is now solved structurally: PlanVersion.title
is NOT NULL (backfilled at migration 0056, see its docstring), so every
version — old or new — snapshots its own real title. What's still true,
and still worth pinning, is provenance_out()'s "no source rows recorded
for this version -> return None, never fabricate" behavior (a version
saved before 0049 legitimately has none) — that's what these tests cover.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import plan as plan_svc


def _version(**overrides) -> MagicMock:
    v = MagicMock()
    v.id = uuid.uuid4()
    v.subtotal_amount = None
    v.contingency_amount = None
    v.total_amount = None
    v.currency = None
    for k, val in overrides.items():
        setattr(v, k, val)
    return v


def _result(rows: list) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


@pytest.mark.asyncio
async def test_provenance_out_returns_none_when_no_sources_recorded():
    # A version saved before migration 0049 has no PlanSource rows at all
    # — the Versions rail must render "wasn't recorded for this version",
    # never a fabricated/empty-but-present provenance object.
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_result([]))

    out = await plan_svc.provenance_out(session, _version())

    assert out is None


@pytest.mark.asyncio
async def test_provenance_out_reassembles_the_old_json_shape():
    session = AsyncMock()
    research_run_id = uuid.uuid4()
    file_id = uuid.uuid4()
    rows = [
        MagicMock(kind="rate_card", ref_id=None, label_snapshot="R1", score_snapshot=None),
        MagicMock(kind="case_study", ref_id=file_id, label_snapshot="case-study.md", score_snapshot=0.87),
        MagicMock(kind="research_citation", ref_id=research_run_id, label_snapshot="example.com"),
    ]
    session.execute = AsyncMock(return_value=_result(rows))

    out = await plan_svc.provenance_out(session, _version())

    assert out["rate_card_codes"] == ["R1"]
    assert out["case_files"] == [{"file_id": str(file_id), "filename": "case-study.md", "score": 0.87}]
    assert out["research_run_id"] == str(research_run_id)
    assert out["research_sources"] == [{"source": "example.com"}]


@pytest.mark.asyncio
async def test_budget_out_returns_none_when_no_lines_and_no_totals():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_result([]))

    out = await plan_svc.budget_out(session, _version())

    assert out is None


@pytest.mark.asyncio
async def test_budget_out_splits_priced_lines_from_needs_expert():
    session = AsyncMock()
    from decimal import Decimal

    priced = MagicMock(
        needs_expert=False, code="R1", label="Positioning workshop", section="1.1", unit="flat",
        qty=Decimal("1"), unit_price=Decimal("1000.00"), amount=Decimal("1000.00"),
    )
    unpriced = MagicMock(needs_expert=True, code="R9", qty=Decimal("2"))
    session.execute = AsyncMock(return_value=_result([priced, unpriced]))

    out = await plan_svc.budget_out(
        session, _version(subtotal_amount=Decimal("1000.00"), contingency_amount=Decimal("100.00"),
                          total_amount=Decimal("1100.00"), currency="THB"),
    )

    assert out["lines"] == [{
        "code": "R1", "label": "Positioning workshop", "section": "1.1", "unit": "flat",
        "qty": "1", "unit_price": "1000.00", "amount": "1000.00",
    }]
    assert out["needs_expert"] == [{"code": "R9", "qty": "2"}]
    assert out["subtotal"] == "1000.00"
    assert out["total"] == "1100.00"
    assert out["currency"] == "THB"
