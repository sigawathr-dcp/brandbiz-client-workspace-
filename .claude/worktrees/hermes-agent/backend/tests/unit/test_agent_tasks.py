"""
Unit tests for app/services/agent_tasks.py (Task 3.12 -- Cowork-style
background tasks).

Covers:
- submit_task: 403 via prepare_chat policy deny
- submit_task: 503 when Hermes isn't configured (HERMES_API_KEY blank)
- submit_task: success path -- creates a 'queued' row, audits, schedules a
  background task (mirrors tests/unit/test_studio.py's BackgroundTasks pattern)
- _run_task: success path -- row moves to 'succeeded' with an encrypted result
- _run_task: failure path -- row moves to 'failed' with error_text, and the
  worker itself never raises (BackgroundTasks has no error channel)
"""
from __future__ import annotations

import base64
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def set_encryption_key(monkeypatch):
    """Provide a valid 32-byte base64 ENCRYPTION_KEY for crypto.encrypt calls."""
    monkeypatch.setenv("ENCRYPTION_KEY", base64.b64encode(b"A" * 32).decode())
    import app.crypto as crypto_mod
    crypto_mod._key = None
    yield
    crypto_mod._key = None


def _make_user(role: str = "L5") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    return user


def _make_session() -> AsyncMock:
    """Request-scoped session stand-in for submit_task (add/commit/refresh)."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    async def _refresh(obj):
        if not getattr(obj, "id", None):
            obj.id = uuid.uuid4()

    session.refresh = _refresh
    return session


def _make_worker_session() -> AsyncMock:
    """Background-worker session stand-in (its own async context manager),
    matching tests/unit/test_studio.py's pattern for _run_*_generation."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


def _make_prepared(*, model_code: str = "hermes-agent", downgrade: bool = False):
    p = MagicMock()
    p.resolved_conversation_id = uuid.uuid4()
    p.model_code = model_code
    p.history = []
    p.downgrade_to_local = downgrade
    p.reasons = ["tier_blocks_external"] if downgrade else []
    return p


def _hermes_configured_router():
    """get_router() stand-in whose .get(HERMES_MODEL_CODE) succeeds."""
    router = MagicMock()
    router.get.return_value = MagicMock()
    return router


# ---------------------------------------------------------------------------
# submit_task — guard rails
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_task_403_on_policy_deny():
    from app.services import agent_tasks

    user = _make_user()
    session = _make_session()
    background = BackgroundTasks()

    with (
        patch("app.services.agent_tasks.get_router", return_value=_hermes_configured_router()),
        patch(
            "app.services.chat_policy.prepare_chat",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=403, detail={"error": "policy_denied"}),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await agent_tasks.submit_task(session, user, prompt="do something", background=background)

    assert exc_info.value.status_code == 403
    session.add.assert_not_called()
    assert len(background.tasks) == 0


@pytest.mark.asyncio
async def test_submit_task_503_when_hermes_not_configured():
    from app.services import agent_tasks

    user = _make_user()
    session = _make_session()
    background = BackgroundTasks()

    unconfigured_router = MagicMock()
    unconfigured_router.get.side_effect = KeyError("hermes-agent")

    with patch("app.services.agent_tasks.get_router", return_value=unconfigured_router):
        with pytest.raises(HTTPException) as exc_info:
            await agent_tasks.submit_task(session, user, prompt="do something", background=background)

    assert exc_info.value.status_code == 503
    session.add.assert_not_called()


# ---------------------------------------------------------------------------
# submit_task — allow path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_task_creates_queued_row_and_schedules_background():
    from app.services import agent_tasks

    user = _make_user()
    session = _make_session()
    background = BackgroundTasks()
    prepared = _make_prepared()

    with (
        patch("app.services.agent_tasks.get_router", return_value=_hermes_configured_router()),
        patch("app.services.chat_policy.prepare_chat", new_callable=AsyncMock, return_value=prepared),
        patch("app.services.agent_tasks.audit_svc.log", new_callable=AsyncMock) as mock_audit,
    ):
        task = await agent_tasks.submit_task(
            session, user, prompt="research the competition", background=background
        )

    assert task.status == "queued"
    assert task.user_id == user.id
    assert task.conversation_id == prepared.resolved_conversation_id
    assert task.downgrade_to_local is False
    assert task.title == "research the competition"
    # Prompt is stored only as ciphertext (§7.1) — never plaintext.
    assert task.prompt_ciphertext != b"research the competition"
    assert agent_tasks.decrypt_prompt(task) == "research the competition"

    session.add.assert_called_once()
    session.commit.assert_awaited()
    mock_audit.assert_awaited_once()
    assert mock_audit.call_args.kwargs["action"] == "agent_task_submitted"

    # Background worker scheduled, not yet run.
    assert len(background.tasks) == 1


@pytest.mark.asyncio
async def test_submit_task_downgrade_to_local_recorded_on_row():
    """Tier 3/4 prompts downgrade to local — Hermes never sees them — and the
    task row records that fact for the UI to surface."""
    from app.services import agent_tasks

    user = _make_user()
    session = _make_session()
    background = BackgroundTasks()
    prepared = _make_prepared(model_code="gemma4:26b", downgrade=True)

    with (
        patch("app.services.agent_tasks.get_router", return_value=_hermes_configured_router()),
        patch("app.services.chat_policy.prepare_chat", new_callable=AsyncMock, return_value=prepared),
        patch("app.services.agent_tasks.audit_svc.log", new_callable=AsyncMock),
    ):
        task = await agent_tasks.submit_task(
            session, user, prompt="เลขบัตรประชาชน 1234567890123", background=background
        )

    assert task.downgrade_to_local is True


# ---------------------------------------------------------------------------
# _run_task — success path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_task_success_marks_succeeded_with_encrypted_result():
    from app.services import agent_tasks

    task_id = uuid.uuid4()
    user_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    fake_user = _make_user()

    worker_session = _make_worker_session()
    collect_result = {
        "output": "Here is the competitive research summary.",
        "model_used": "hermes-agent",
        "tokens_input": 120,
        "tokens_output": 340,
        "latency_ms": 9000,
    }

    with (
        patch("app.services.agent_tasks.session_factory", return_value=worker_session),
        patch("app.services.agent_tasks._reload_user", new_callable=AsyncMock, return_value=fake_user),
        patch("app.services.agent_tasks._run_collect", new_callable=AsyncMock, return_value=collect_result),
        patch("app.services.agent_tasks.audit_svc.log", new_callable=AsyncMock) as mock_audit,
    ):
        await agent_tasks._run_task(
            task_id=task_id,
            user_id=user_id,
            resolved_conversation_id=conv_id,
            prompt="research the competition",
            model_code="hermes-agent",
            history=[],
            downgrade_to_local=False,
            reasons=[],
        )

    # Two UPDATEs: "running" transition, then the terminal "succeeded" update.
    assert worker_session.execute.await_count == 2
    final_update = worker_session.execute.await_args_list[-1].args[0]
    compiled = str(final_update.compile(compile_kwargs={"literal_binds": False}))
    assert "agent_task" in compiled

    audit_actions = [c.kwargs["action"] for c in mock_audit.await_args_list]
    assert audit_actions == ["agent_task_running", "agent_task_succeeded"]


# ---------------------------------------------------------------------------
# _run_task — failure path (must never raise out of BackgroundTasks)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_task_failure_marks_failed_and_never_raises():
    from app.services import agent_tasks

    task_id = uuid.uuid4()
    user_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    fake_user = _make_user()

    worker_session = _make_worker_session()

    with (
        patch("app.services.agent_tasks.session_factory", return_value=worker_session),
        patch("app.services.agent_tasks._reload_user", new_callable=AsyncMock, return_value=fake_user),
        patch(
            "app.services.agent_tasks._run_collect",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Hermes unreachable: timeout"),
        ),
        patch("app.services.agent_tasks.audit_svc.log", new_callable=AsyncMock) as mock_audit,
    ):
        # Must complete cleanly -- no exception propagates.
        await agent_tasks._run_task(
            task_id=task_id,
            user_id=user_id,
            resolved_conversation_id=conv_id,
            prompt="research the competition",
            model_code="hermes-agent",
            history=[],
            downgrade_to_local=False,
            reasons=[],
        )

    audit_actions = [c.kwargs["action"] for c in mock_audit.await_args_list]
    assert audit_actions == ["agent_task_running", "agent_task_failed"]
    failed_details = mock_audit.await_args_list[-1].kwargs["details"]
    assert "Hermes unreachable" in failed_details["error"]


# ---------------------------------------------------------------------------
# _run_task — live progress snapshots (Task 3.12 follow-on)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_task_flushes_progress_during_run_and_clears_it_on_success():
    """The on_event callback passed to run_chat_collect_streamed must trigger
    at least one progress write while running, and the terminal update must
    clear progress_* (result_* becomes the durable record instead)."""
    from app.services import agent_tasks

    task_id = uuid.uuid4()
    user_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    fake_user = _make_user()

    worker_session = _make_worker_session()
    collect_result = {
        "output": "Here is the competitive research summary.",
        "model_used": "hermes-agent",
        "tokens_input": 120,
        "tokens_output": 340,
        "latency_ms": 9000,
    }

    async def fake_run_collect(fn, **kwargs):
        # Simulate run_chat_collect_streamed emitting a few events, forcing
        # the throttle open each time so every call actually flushes.
        on_event = kwargs["on_event"]
        await on_event({"type": "start"})
        await on_event({"type": "content", "delta": "partial answer..."})
        return collect_result

    with (
        patch("app.services.agent_tasks.session_factory", return_value=worker_session),
        patch("app.services.agent_tasks._reload_user", new_callable=AsyncMock, return_value=fake_user),
        patch("app.services.agent_tasks._run_collect", side_effect=fake_run_collect),
        patch("app.services.agent_tasks.audit_svc.log", new_callable=AsyncMock),
        patch("app.services.agent_tasks._PROGRESS_FLUSH_INTERVAL_S", 0.0),
    ):
        await agent_tasks._run_task(
            task_id=task_id,
            user_id=user_id,
            resolved_conversation_id=conv_id,
            prompt="research the competition",
            model_code="hermes-agent",
            history=[],
            downgrade_to_local=False,
            reasons=[],
        )

    # At least one progress flush happened, plus the "running" transition and
    # the terminal "succeeded" update -- more than the bare 2-update minimum.
    assert worker_session.execute.await_count >= 3

    terminal_update = worker_session.execute.await_args_list[-1].args[0]
    compiled = terminal_update.compile(compile_kwargs={"literal_binds": False})
    # The terminal write clears progress -- assert the clearing column is present.
    assert "progress_ciphertext" in str(compiled)
