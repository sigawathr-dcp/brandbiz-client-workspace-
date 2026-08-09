"""Unit tests for app/services/rate_limit.py — Phase 7 hardening.

The one property that matters: once a client IP hits `limit` requests
inside `window_seconds`, the very next call raises 429 — and a different
IP, or the same IP under a different key_prefix, is unaffected.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.rate_limit import rate_limit


def _mock_request(ip: str = "1.2.3.4") -> MagicMock:
    request = MagicMock()
    request.headers = {}
    request.client.host = ip
    return request


class TestRateLimit:
    @pytest.mark.asyncio
    async def test_allows_up_to_the_limit(self):
        dep = rate_limit("test_allow", limit=3, window_seconds=60)
        request = _mock_request("10.0.0.1")
        for _ in range(3):
            await dep(request)  # must not raise

    @pytest.mark.asyncio
    async def test_denies_the_request_over_the_limit(self):
        dep = rate_limit("test_deny", limit=2, window_seconds=60)
        request = _mock_request("10.0.0.2")
        await dep(request)
        await dep(request)
        with pytest.raises(HTTPException) as exc:
            await dep(request)
        assert exc.value.status_code == 429

    @pytest.mark.asyncio
    async def test_different_ips_have_independent_buckets(self):
        dep = rate_limit("test_ip_isolation", limit=1, window_seconds=60)
        await dep(_mock_request("10.0.0.3"))
        await dep(_mock_request("10.0.0.4"))  # different IP — must not raise

    @pytest.mark.asyncio
    async def test_different_key_prefixes_have_independent_buckets(self):
        """/public/redeem and /public/plans/{token} must not share a
        bucket — a burst on one endpoint shouldn't lock out the other."""
        dep_a = rate_limit("test_prefix_a", limit=1, window_seconds=60)
        dep_b = rate_limit("test_prefix_b", limit=1, window_seconds=60)
        request = _mock_request("10.0.0.5")
        await dep_a(request)
        await dep_b(request)  # different prefix, same IP — must not raise

    @pytest.mark.asyncio
    async def test_x_forwarded_for_is_used_when_present(self):
        dep = rate_limit("test_xff", limit=1, window_seconds=60)
        request = _mock_request("10.0.0.6")
        request.headers = {"X-Forwarded-For": "203.0.113.9, 10.0.0.6"}
        await dep(request)
        # A second request claiming the same forwarded IP is denied...
        request2 = _mock_request("10.0.0.7")
        request2.headers = {"X-Forwarded-For": "203.0.113.9"}
        with pytest.raises(HTTPException):
            await dep(request2)
