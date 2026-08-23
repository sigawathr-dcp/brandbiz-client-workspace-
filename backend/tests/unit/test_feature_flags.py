"""D21/D22 — CLIENT_SURFACE_ENABLED kill switch.

The client-seat routers (/client/*, /public/*, /admin/clients/*) are not
gated by require_internal, so the surface carries its own off switch:
Depends(require_client_surface), attached at include_router() level in
main.py.

It used to be 22 hand-written `_require_enabled()` calls inside the
handlers, and three had been missed on the /admin/clients GET routes —
list_workspaces, list_invites, get_workspace_agent_config — so with the
switch off an admin could still read workspace contact details, invite
rows, and agent config while every write route correctly 503'd. The fix was
structural: one router-level dependency that no handler can forget.

TestEveryClientSurfaceRouteIsGated below is the regression net for that. It
walks the real app's route table, so a route added tomorrow is covered
without anyone remembering to update this file.

The D23 companion flag (client_internal_access_enabled) is covered by
test_require_internal.py and test_workspace_visibility.py — run all three:

    pytest tests/unit/test_feature_flags.py \
           tests/unit/test_require_internal.py \
           tests/unit/test_workspace_visibility.py -q
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from app.config import settings
from app.deps import require_client_surface

# Every path prefix .env.example promises the switch "hard-disables".
GATED_PREFIXES = ("/client", "/public", "/admin/clients")


@pytest.fixture
def surface_off(monkeypatch):
    monkeypatch.setattr(settings, "client_surface_enabled", False)


@pytest.fixture
def surface_on(monkeypatch):
    monkeypatch.setattr(settings, "client_surface_enabled", True)


class TestTheGateItself:
    @pytest.mark.asyncio
    async def test_raises_503_when_off(self, surface_off):
        with pytest.raises(HTTPException) as exc:
            await require_client_surface()
        assert exc.value.status_code == 503
        assert exc.value.detail == "Client workspaces are disabled"

    @pytest.mark.asyncio
    async def test_passes_when_on(self, surface_on):
        assert await require_client_surface() is None


class TestEveryClientSurfaceRouteIsGated:
    """The structural guarantee that replaced the 22 manual calls.

    A route can only appear under one of GATED_PREFIXES by being included
    from client.py / client_public.py / client_admin.py, and main.py attaches
    the gate at include_router() level — so this passes for free unless
    someone registers a client-surface router without the dependency. That
    is exactly the mistake worth catching, since it is invisible in review.
    """

    @staticmethod
    def _gated_routes():
        from app.main import app

        return [
            r
            for r in app.routes
            if isinstance(r, APIRoute) and r.path.startswith(GATED_PREFIXES)
        ]

    def test_the_route_table_is_not_empty(self):
        """Guards the test itself: an import change that silently drops the
        routers would otherwise make every assertion below vacuously true."""
        routes = self._gated_routes()
        assert len(routes) > 20, f"only {len(routes)} client-surface routes found"

    def test_all_gated(self):
        ungated = [
            f"{sorted(r.methods)} {r.path}"
            for r in self._gated_routes()
            if not any(d.dependency is require_client_surface for d in r.dependencies)
        ]
        assert not ungated, (
            "these client-surface routes are missing the CLIENT_SURFACE_ENABLED "
            "gate — attach Depends(require_client_surface) at include_router() "
            f"level in main.py:\n  " + "\n  ".join(ungated)
        )

    def test_the_three_previously_missed_admin_routes(self):
        """Named explicitly because these were the actual bug: all three are
        GETs whose sibling write routes were gated, which is why the gap
        survived review."""
        wanted = {
            ("GET", "/admin/clients"),
            ("GET", "/admin/clients/{workspace_id}/invites"),
            ("GET", "/admin/clients/{workspace_id}/agent"),
        }
        gated = {
            (m, r.path)
            for r in self._gated_routes()
            for m in r.methods
            if any(d.dependency is require_client_surface for d in r.dependencies)
        }
        assert wanted <= gated, f"still ungated: {wanted - gated}"


class TestGateRunsBeforeAuth:
    """With the switch off the surface must be dark to everyone, not merely
    read-only — so the gate has to sit ahead of each router's own auth
    dependencies. include_router() prepends router-level dependencies, so
    asserting position 0 pins that ordering.
    """

    def test_gate_is_the_first_dependency(self):
        for r in TestEveryClientSurfaceRouteIsGated._gated_routes():
            assert r.dependencies[0].dependency is require_client_surface, (
                f"{sorted(r.methods)} {r.path}: gate is not the first dependency, "
                "so auth (or the rate limiter) runs before the kill switch"
            )


class TestNoHandlerKeepsItsOwnCopy:
    """The manual calls are gone. If one comes back, the flag ends up
    enforced in two places that can disagree — delete it and rely on the
    router-level dependency instead."""

    def test_require_enabled_helpers_are_gone(self):
        import inspect

        from app.routers import client, client_admin, client_public

        for mod in (client, client_admin, client_public):
            src = inspect.getsource(mod)
            assert "_require_enabled" not in src, (
                f"{mod.__name__} reintroduced a per-handler flag check"
            )
            # The inline form client_public.py used before the refactor.
            assert "if not settings.client_surface_enabled" not in src, (
                f"{mod.__name__} reintroduced an inline flag check"
            )


class TestDefaultsMatchTheDocumentedContract:
    """.env.example advertises surface=true / internal=false as the shipped
    defaults; config.py must agree, since the container has no .env file and
    falls back to these code defaults."""

    def test_code_defaults(self):
        from app.config import Settings

        # Instantiated fresh so a monkeypatched singleton can't mask a
        # changed default. Required secrets come from conftest's os.environ.
        fresh = Settings()
        assert fresh.client_surface_enabled is True
        assert fresh.client_internal_access_enabled is False
