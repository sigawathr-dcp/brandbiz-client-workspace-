"""Unit tests for app/services/hermes_setup.py — no real network traffic."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.config import settings
from app.services import hermes_setup


# ---------------------------------------------------------------------------
# probe()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_probe_unconfigured_short_circuits(monkeypatch):
    """Blank HERMES_API_KEY → configured=False and no HTTP call at all."""
    monkeypatch.setattr(settings, "hermes_api_key", "")
    with patch("app.services.hermes_setup.httpx.AsyncClient") as client_cls:
        status = await hermes_setup.probe()
    assert status.configured is False
    assert status.reachable is False
    client_cls.assert_not_called()


def _client_returning(response=None, error=None) -> MagicMock:
    """An httpx.AsyncClient async-context-manager double."""
    client = MagicMock()
    client.get = AsyncMock(return_value=response, side_effect=error)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@pytest.mark.asyncio
async def test_probe_reachable(monkeypatch):
    monkeypatch.setattr(settings, "hermes_api_key", "k")
    monkeypatch.setattr(settings, "hermes_api_url", "http://host.docker.internal:8642/v1")
    resp = MagicMock(status_code=200)
    with patch(
        "app.services.hermes_setup.httpx.AsyncClient",
        return_value=_client_returning(response=resp),
    ) as client_cls:
        status = await hermes_setup.probe()
    assert status == hermes_setup.HermesStatus(configured=True, reachable=True)
    # Bearer auth against {url}/models
    client = client_cls.return_value.__aenter__.return_value
    args, kwargs = client.get.call_args
    assert args[0] == "http://host.docker.internal:8642/v1/models"
    assert kwargs["headers"]["Authorization"] == "Bearer k"


@pytest.mark.asyncio
async def test_probe_connection_error_is_offline_not_raise(monkeypatch):
    monkeypatch.setattr(settings, "hermes_api_key", "k")
    with patch(
        "app.services.hermes_setup.httpx.AsyncClient",
        return_value=_client_returning(error=httpx.ConnectError("refused")),
    ):
        status = await hermes_setup.probe()
    assert status == hermes_setup.HermesStatus(configured=True, reachable=False)


@pytest.mark.asyncio
async def test_probe_non_200_is_offline(monkeypatch):
    monkeypatch.setattr(settings, "hermes_api_key", "k")
    resp = MagicMock(status_code=401)
    with patch(
        "app.services.hermes_setup.httpx.AsyncClient",
        return_value=_client_returning(response=resp),
    ):
        status = await hermes_setup.probe()
    assert status == hermes_setup.HermesStatus(configured=True, reachable=False)


# ---------------------------------------------------------------------------
# render_setup_script()
# ---------------------------------------------------------------------------

def test_render_setup_script_fills_all_placeholders(monkeypatch):
    monkeypatch.setattr(settings, "hermes_api_key", "sekret-token")
    monkeypatch.setattr(settings, "hermes_ollama_url", "http://10.0.0.5:11434/v1")
    monkeypatch.setattr(settings, "hermes_ollama_model", "hermes3:70b")

    script = hermes_setup.render_setup_script()

    assert "API_SERVER_KEY=sekret-token" in script
    assert "base_url: http://10.0.0.5:11434/v1" in script
    assert "model: hermes3:70b" in script
    assert "__API_KEY__" not in script
    assert "__OLLAMA_URL__" not in script
    assert "__OLLAMA_MODEL__" not in script


def test_render_setup_script_mirrors_hermes_init_contract(monkeypatch):
    """The script must keep hermes-init's semantics: API server on 0.0.0.0:8642,
    never overwrite an existing config, and end by starting the gateway."""
    monkeypatch.setattr(settings, "hermes_api_key", "k")
    script = hermes_setup.render_setup_script()

    assert "API_SERVER_ENABLED=true" in script
    assert "API_SERVER_HOST=0.0.0.0" in script
    assert "API_SERVER_PORT=8642" in script
    assert script.count("-not (Test-Path") == 2  # config.yaml and .env guards
    assert "hermes gateway run" in script
