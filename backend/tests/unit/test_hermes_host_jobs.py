"""Unit tests for app/services/hermes_host_jobs.py (Task 3.14 — one-click
native Hermes setup via a host helper). Sessions are mocked — no DB."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.services import hermes_host_jobs


@pytest.fixture(autouse=True)
def reset_heartbeat():
    hermes_host_jobs._helper_last_seen = None
    yield
    hermes_host_jobs._helper_last_seen = None


def _make_session(scalar_result=None) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_result
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    return session


def _make_admin() -> MagicMock:
    admin = MagicMock()
    admin.id = uuid.uuid4()
    return admin


# ---------------------------------------------------------------------------
# Helper liveness
# ---------------------------------------------------------------------------

def test_helper_online_false_until_seen_then_expires():
    assert hermes_host_jobs.helper_online() is False
    hermes_host_jobs.mark_helper_seen()
    assert hermes_host_jobs.helper_online() is True
    hermes_host_jobs._helper_last_seen = datetime.now(timezone.utc) - timedelta(seconds=60)
    assert hermes_host_jobs.helper_online() is False


# ---------------------------------------------------------------------------
# create_job
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_job_409_when_one_active():
    session = _make_session(scalar_result=MagicMock())  # an active job exists
    with pytest.raises(HTTPException) as exc:
        await hermes_host_jobs.create_job(session, _make_admin())
    assert exc.value.status_code == 409
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_create_job_queues_and_commits():
    session = _make_session(scalar_result=None)
    admin = _make_admin()
    job = await hermes_host_jobs.create_job(session, admin)
    assert job.status == "queued"
    assert job.kind == "setup"
    assert job.created_by == admin.id
    session.add.assert_called_once_with(job)
    session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# claim_pending
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_claim_pending_empty_still_heartbeats():
    session = _make_session(scalar_result=None)
    assert await hermes_host_jobs.claim_pending(session) is None
    assert hermes_host_jobs.helper_online() is True   # empty poll counts as alive
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_claim_pending_transitions_to_running():
    queued = MagicMock()
    queued.status = "queued"
    queued.claimed_at = None
    session = _make_session(scalar_result=queued)
    job = await hermes_host_jobs.claim_pending(session)
    assert job is queued
    assert job.status == "running"
    assert job.claimed_at is not None
    session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def _running_job() -> MagicMock:
    job = MagicMock()
    job.status = "running"
    job.log_text = None
    job.finished_at = None
    return job


@pytest.mark.asyncio
async def test_report_rejects_unknown_status():
    session = _make_session()
    with pytest.raises(HTTPException) as exc:
        await hermes_host_jobs.report(session, uuid.uuid4(), status="exploded", log=None)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_report_404_unknown_job_and_409_after_terminal():
    session = _make_session(scalar_result=None)
    with pytest.raises(HTTPException) as exc:
        await hermes_host_jobs.report(session, uuid.uuid4(), status=None, log="hi")
    assert exc.value.status_code == 404

    done = MagicMock()
    done.status = "succeeded"
    session = _make_session(scalar_result=done)
    with pytest.raises(HTTPException) as exc:
        await hermes_host_jobs.report(session, uuid.uuid4(), status=None, log="late line")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_report_appends_log_and_finishes():
    job = _running_job()
    session = _make_session(scalar_result=job)
    await hermes_host_jobs.report(session, uuid.uuid4(), status=None, log="line one")
    assert job.log_text == "line one"
    assert job.finished_at is None

    session = _make_session(scalar_result=job)
    await hermes_host_jobs.report(session, uuid.uuid4(), status="succeeded", log="done")
    assert job.log_text == "line one\ndone"
    assert job.status == "succeeded"
    assert job.finished_at is not None


@pytest.mark.asyncio
async def test_report_log_is_capped_keeping_tail():
    job = _running_job()
    job.log_text = "x" * hermes_host_jobs._LOG_CAP_CHARS
    session = _make_session(scalar_result=job)
    await hermes_host_jobs.report(session, uuid.uuid4(), status=None, log="THE-TAIL")
    assert len(job.log_text) == hermes_host_jobs._LOG_CAP_CHARS
    assert job.log_text.endswith("THE-TAIL")


# ---------------------------------------------------------------------------
# mint_helper_key
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mint_helper_key_creates_account_and_returns_gw_key():
    session = _make_session(scalar_result=None)  # no existing helper user
    raw = await hermes_host_jobs.mint_helper_key(session)
    assert raw.startswith("gw_")
    # one User + one ApiKey added
    added_types = [type(c.args[0]).__name__ for c in session.add.call_args_list]
    assert added_types == ["User", "ApiKey"]
    session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# render_helper_script
# ---------------------------------------------------------------------------

def test_render_helper_script_fills_placeholders_and_is_trigger_only():
    script = hermes_host_jobs.render_helper_script("gw_test123", "http://gw.example:8000")
    assert "gw_test123" in script
    assert "http://gw.example:8000" in script
    assert "__HELPER_KEY__" not in script
    assert "__GATEWAY_URL__" not in script
    # one-time installer registers the logon task…
    assert "Register-ScheduledTask" in script
    assert "-AtLogOn" in script
    # …and the run loop only ever executes the hardcoded setup routine —
    # nothing from the job payload is invoked, only written as files.
    assert "Invoke-SetupJob" in script
    assert "Invoke-Expression" not in script
    assert "hermes gateway run" in script
    assert "/hermes/host-jobs/pending" in script


# ---------------------------------------------------------------------------
# render_helper_installer_cmd — self-extracting .cmd wrapper
# ---------------------------------------------------------------------------

def test_cmd_stub_line_count_matches_constant():
    """The Select-Object -Skip N in the stub must equal the stub's own line
    count, or the extracted payload would be off by a line. Must be
    Select-Object, not Get-Content -Skip — the latter is PowerShell 7+ only
    and doesn't exist in Windows PowerShell 5.1 (what `powershell.exe` runs
    on a stock Windows machine, live-verified against 5.1.26100)."""
    assert hermes_host_jobs._CMD_STUB.count("\r\n") == hermes_host_jobs._CMD_STUB_LINES
    assert f"-Skip {hermes_host_jobs._CMD_STUB_LINES}" in hermes_host_jobs._CMD_STUB
    assert "Get-Content -Skip" not in hermes_host_jobs._CMD_STUB
    assert "Select-Object -Skip" in hermes_host_jobs._CMD_STUB


def test_cmd_wrapper_is_crlf_throughout_and_exits_before_payload():
    cmd = hermes_host_jobs.render_helper_installer_cmd("gw_test123")
    # No bare \n — every line ending must be \r\n (cmd.exe requirement).
    assert "\n" not in cmd.replace("\r\n", "")
    assert cmd.startswith("@echo off\r\n")
    # cmd.exe must stop before ever parsing the PS1 payload as batch commands.
    stub_text, _, _ = cmd.partition("exit /b\r\n")
    assert "exit /b\r\n" in cmd
    assert "param([switch]$Run)" not in stub_text  # PS1 payload not reached pre-exit


def test_cmd_wrapper_extracts_byte_identical_payload():
    """Simulates what `Get-Content | Select-Object -Skip N` does on Windows:
    split into lines, drop the first N. Compared line-by-line (not via a
    rejoined string) so
    the assertion doesn't depend on a synthetic trailing-newline convention
    that's really Set-Content's implementation detail on the real host."""
    api_key, gw = "gw_roundtrip", "http://gw.example:8000"
    cmd = hermes_host_jobs.render_helper_installer_cmd(api_key, gw)
    cmd_lines = cmd.split("\r\n")
    extracted_lines = cmd_lines[hermes_host_jobs._CMD_STUB_LINES:]
    if extracted_lines and extracted_lines[-1] == "":
        extracted_lines = extracted_lines[:-1]  # split() artifact of the trailing \r\n, not a real line

    expected_lines = hermes_host_jobs.render_helper_script(api_key, gw).split("\n")
    if expected_lines and expected_lines[-1] == "":
        expected_lines = expected_lines[:-1]

    assert extracted_lines == expected_lines


def test_cmd_wrapper_no_placeholders_and_forces_download_attachment():
    cmd = hermes_host_jobs.render_helper_installer_cmd("gw_test123", "http://gw.example:8000")
    assert "__HELPER_KEY__" not in cmd
    assert "__GATEWAY_URL__" not in cmd
    assert "gw_test123" in cmd
    assert "http://gw.example:8000" in cmd
