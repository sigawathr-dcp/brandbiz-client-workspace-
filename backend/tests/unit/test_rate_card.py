"""Unit tests for app/services/rate_card.py::price() — the structural fix
for the plan's budget correctness risk.

The one property that matters most: a code with no matching active
rate-card row must NEVER produce a fabricated amount — it goes to
needs_expert instead. The model (app/services/plan.py::draft_plan) only
ever emits {code, qty}; this module is the only place a THB number appears.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.services.rate_card import price


def _mock_item(*, code, label, unit_price, workspace_id=None, unit="job", currency="THB", active=True):
    item = MagicMock()
    item.code = code
    item.label = label
    item.unit = unit
    item.unit_price = Decimal(unit_price)
    item.currency = currency
    item.active = active
    item.workspace_id = workspace_id
    item.section = "1.1"
    return item


def _session_returning(items: list) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    result.scalars.return_value = scalars
    session.execute = AsyncMock(return_value=result)
    return session


class TestKnownCodes:
    async def test_priced_line_uses_rate_card_amount_not_model_value(self):
        ws = uuid.uuid4()
        session = _session_returning([_mock_item(code="A1", label="Workshop", unit_price="1000.00")])

        result = await price(session, ws, [{"code": "A1", "qty": 2}])

        assert result["needs_expert"] == []
        assert len(result["lines"]) == 1
        line = result["lines"][0]
        assert line["code"] == "A1"
        assert line["amount"] == "2000.00"  # 1000 * 2, computed here — never from the model

    async def test_subtotal_contingency_and_total_are_consistent(self):
        ws = uuid.uuid4()
        session = _session_returning([_mock_item(code="A1", label="Workshop", unit_price="1000.00")])

        result = await price(session, ws, [{"code": "A1", "qty": 1}])

        assert result["subtotal"] == "1000.00"
        assert result["contingency"] == "100.00"  # 10% of subtotal
        assert result["total"] == "1100.00"

    async def test_default_quantity_is_one_when_qty_missing(self):
        ws = uuid.uuid4()
        session = _session_returning([_mock_item(code="A1", label="Workshop", unit_price="500.00")])

        result = await price(session, ws, [{"code": "A1"}])

        assert result["lines"][0]["amount"] == "500.00"

    async def test_zero_or_negative_qty_falls_back_to_one(self):
        ws = uuid.uuid4()
        session = _session_returning([_mock_item(code="A1", label="Workshop", unit_price="500.00")])

        result = await price(session, ws, [{"code": "A1", "qty": -3}])

        assert result["lines"][0]["amount"] == "500.00"

    async def test_workspace_specific_row_wins_over_shared_default(self):
        ws = uuid.uuid4()
        shared = _mock_item(code="A1", label="Workshop (default)", unit_price="1000.00", workspace_id=None)
        override = _mock_item(code="A1", label="Workshop (client rate)", unit_price="1500.00", workspace_id=ws)
        session = _session_returning([shared, override])

        result = await price(session, ws, [{"code": "A1", "qty": 1}])

        assert result["lines"][0]["amount"] == "1500.00"
        assert result["lines"][0]["label"] == "Workshop (client rate)"


class TestUnknownCodes:
    async def test_unmatched_code_goes_to_needs_expert_not_a_fabricated_price(self):
        ws = uuid.uuid4()
        session = _session_returning([])  # nothing in the rate card matches

        result = await price(session, ws, [{"code": "GHOST-999", "qty": 3}])

        assert result["lines"] == []
        assert result["needs_expert"] == [{"code": "GHOST-999", "qty": "3"}]
        assert result["subtotal"] == "0.00"
        assert result["total"] == "0.00"

    async def test_mixed_known_and_unknown_codes(self):
        ws = uuid.uuid4()
        session = _session_returning([_mock_item(code="A1", label="Workshop", unit_price="1000.00")])

        result = await price(session, ws, [{"code": "A1", "qty": 1}, {"code": "UNKNOWN", "qty": 2}])

        assert len(result["lines"]) == 1
        assert result["needs_expert"] == [{"code": "UNKNOWN", "qty": "2"}]
        # the unknown code contributes nothing to the total
        assert result["subtotal"] == "1000.00"

    async def test_empty_items_list_prices_to_zero(self):
        ws = uuid.uuid4()
        session = _session_returning([])

        result = await price(session, ws, [])

        assert result["lines"] == []
        assert result["needs_expert"] == []
        assert result["total"] == "0.00"
