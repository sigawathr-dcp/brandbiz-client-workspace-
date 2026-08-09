"""
Unit tests for Task 2.8 admin metrics helper functions and Pydantic schemas.

No real DB required — these tests check schema validation and the
_month_start() helper only.  Endpoint-level tests are integration tests.
"""
from __future__ import annotations

from datetime import date, timezone

import pytest

from app.routers.admin import (
    AuditLogEntry,
    AuditLogListResponse,
    DashboardMetrics,
    MetricsVerifyResponse,
    ModelUsageItem,
    TopUserItem,
    _month_start,
)


def test_month_start_first_day_of_current_month():
    ms = _month_start()
    today = date.today()
    assert ms.year == today.year
    assert ms.month == today.month
    assert ms.day == 1
    assert ms.tzinfo is timezone.utc


def test_month_start_is_idempotent():
    assert _month_start() == _month_start()


def test_dashboard_metrics_round_trip():
    m = DashboardMetrics(
        active_users=42,
        total_messages_month=1500,
        external_cost_month_usd=3.1415,
        pii_blocks_month=7,
        pending_reveals=2,
        period_start="2026-06-01",
    )
    assert m.active_users == 42
    assert m.external_cost_month_usd == pytest.approx(3.1415)
    assert m.period_start == "2026-06-01"

    data = m.model_dump()
    assert data["pending_reveals"] == 2

    m2 = DashboardMetrics.model_validate_json(m.model_dump_json())
    assert m2 == m


def test_model_usage_item():
    item = ModelUsageItem(
        model_code="claude-sonnet-4",
        tokens_input=10000,
        tokens_output=3000,
        cost_usd=0.0185,
        message_count=25,
    )
    assert item.model_code == "claude-sonnet-4"
    assert item.cost_usd == pytest.approx(0.0185)
    assert item.message_count == 25


def test_top_user_item_no_display_name():
    u = TopUserItem(
        user_id="00000000-0000-0000-0000-000000000001",
        email="alice@test.local",
        display_name=None,
        cost_usd=0.0,
        message_count=0,
    )
    assert u.display_name is None
    assert u.cost_usd == 0.0


def test_metrics_verify_matches_when_equal():
    m = DashboardMetrics(
        active_users=5,
        total_messages_month=100,
        external_cost_month_usd=1.0,
        pii_blocks_month=3,
        pending_reveals=0,
        period_start="2026-06-01",
    )
    result = MetricsVerifyResponse(cached=m, fresh=m, matches=True, deltas={})
    assert result.matches is True
    assert result.deltas == {}


def test_metrics_verify_reports_delta():
    cached = DashboardMetrics(
        active_users=5,
        total_messages_month=100,
        external_cost_month_usd=1.0,
        pii_blocks_month=3,
        pending_reveals=0,
        period_start="2026-06-01",
    )
    fresh = DashboardMetrics(
        active_users=5,
        total_messages_month=105,
        external_cost_month_usd=1.0,
        pii_blocks_month=3,
        pending_reveals=0,
        period_start="2026-06-01",
    )
    result = MetricsVerifyResponse(
        cached=cached,
        fresh=fresh,
        matches=False,
        deltas={"total_messages_month": 5.0},
    )
    assert result.matches is False
    assert result.deltas["total_messages_month"] == 5.0


def test_audit_log_entry_from_dict():
    import uuid
    from datetime import datetime
    from ipaddress import IPv4Address

    entry = AuditLogEntry(
        id=1,
        created_at=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        actor_id=None,
        action="pii_detected",
        resource_type="message",
        resource_id=None,
        details={"matched": "thai_id"},
        ip_address="127.0.0.1",
        user_agent=None,
    )
    assert entry.action == "pii_detected"
    assert entry.details == {"matched": "thai_id"}


def test_audit_log_entry_coerces_ipv4address():
    """INET column returns IPv4Address from SQLAlchemy — must coerce to str."""
    import uuid
    from datetime import datetime
    from ipaddress import IPv4Address

    entry = AuditLogEntry(
        id=2,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        user_id=None,
        actor_id=None,
        action="login",
        resource_type=None,
        resource_id=None,
        details=None,
        ip_address=IPv4Address("192.168.1.1"),
        user_agent=None,
    )
    assert entry.ip_address == "192.168.1.1"
    assert isinstance(entry.ip_address, str)


def test_audit_log_list_response():
    resp = AuditLogListResponse(items=[], total=0)
    assert resp.total == 0
    assert resp.items == []
