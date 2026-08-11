"""Unit tests for GET /client/bootstrap replaying a prior research run /
case match — the fix for the client-workspace "Your journey" chapters
(NavRail.tsx) staying locked after a page reload even though the market
scan and case match already completed and are sitting in the database.

Heavy DB/crypto/audit machinery is mocked out, same style as
test_client_router_intake.py — this exercises _bootstrap_research_and_cases()
directly (the new replay logic) rather than the full bootstrap() endpoint,
which would otherwise need workspace_svc/skill_svc/agent_svc/plan_svc all
mocked just to reach the two queries under test.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.client_intake import CaseMatch, ClientProfile, ResearchRun
from app.routers import client as client_router


def _fake_profile() -> ClientProfile:
    profile = ClientProfile(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        step=8,
        fields_ciphertext=b"", fields_nonce=b"", fields_tag=b"", key_version=1,
    )
    profile.id = uuid.uuid4()
    return profile


def _fake_ctx(profile: ClientProfile) -> MagicMock:
    ctx = MagicMock()
    ctx.user.id = profile.user_id
    ctx.workspace_id = profile.workspace_id
    return ctx


def _fake_run(status: str) -> ResearchRun:
    run = ResearchRun(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        query="q",
        status=status,
    )
    run.id = uuid.uuid4()
    run.findings = [{"text": "finding one"}]
    run.citations = [{"index": 1, "source": "example.com"}]
    return run


def _fake_match_row(score: float) -> CaseMatch:
    row = CaseMatch(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        file_id=uuid.uuid4(),
        filename="case.md",
        score=score,
        rationale="looks similar",
    )
    return row


def _no_audit_row() -> MagicMock:
    """A session.execute result for the case_matched audit-log fallback
    query, standing in for 'no such audit row exists'."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    return result


def _execute_results(*results: MagicMock) -> AsyncMock:
    """A session.execute stand-in that returns each of `results` in order,
    one per call. The helper issues two queries (ResearchRun, then
    CaseMatch) when CaseMatch rows exist, or three (plus the case_matched
    audit-log fallback) when it doesn't — see
    test_zero_match_run_falls_back_to_audit_log_done_with_empty_matches."""
    return AsyncMock(side_effect=list(results))


@pytest.mark.asyncio
async def test_done_research_and_cases_replay_with_cards():
    profile = _fake_profile()
    ctx = _fake_ctx(profile)
    run = _fake_run("done")
    row = _fake_match_row(0.9)

    research_result = MagicMock()
    research_result.scalar_one_or_none.return_value = run
    cases_result = MagicMock()
    cases_result.scalars.return_value.all.return_value = [row]

    session = AsyncMock()
    session.execute = _execute_results(research_result, cases_result)

    fake_card = MagicMock(title="A great case", client="Acme", category="Launch",
                           source_url=None, summary="summary", image_url=None)

    with patch.object(
        client_router.case_match_svc, "cards_for_file_ids",
        new=AsyncMock(return_value={row.file_id: fake_card}),
    ):
        research_status, research_out, cases_status, cases_out = (
            await client_router._bootstrap_research_and_cases(session, ctx, profile)
        )

    assert research_status == "done"
    assert research_out == {"id": str(run.id), "findings": run.findings, "citations": run.citations}

    assert cases_status == "done"
    assert cases_out["matches"] == [
        {
            "file_id": str(row.file_id),
            "filename": row.filename,
            "score": round(row.score, 2),
            "rationale": row.rationale,
            "title": "A great case",
            "client": "Acme",
            "category": "Launch",
            "source_url": None,
            "summary": "summary",
            "image_url": None,
        }
    ]


@pytest.mark.asyncio
async def test_pending_research_run_reported_as_error_not_a_forever_spinner():
    """A run stuck at status='pending' means the browser closed mid-scan —
    there's no background worker to ever finish it, so bootstrap must not
    hand the frontend a status it will spin on forever."""
    profile = _fake_profile()
    ctx = _fake_ctx(profile)
    run = _fake_run("pending")

    research_result = MagicMock()
    research_result.scalar_one_or_none.return_value = run
    cases_result = MagicMock()
    cases_result.scalars.return_value.all.return_value = []

    session = AsyncMock()
    session.execute = _execute_results(research_result, cases_result, _no_audit_row())

    research_status, research_out, cases_status, cases_out = (
        await client_router._bootstrap_research_and_cases(session, ctx, profile)
    )

    assert research_status == "error"
    assert research_out is None  # only 'done' runs populate the payload
    assert cases_status == "idle"
    assert cases_out is None


@pytest.mark.asyncio
async def test_failed_research_run_reported_as_error():
    profile = _fake_profile()
    ctx = _fake_ctx(profile)
    run = _fake_run("failed")

    research_result = MagicMock()
    research_result.scalar_one_or_none.return_value = run
    cases_result = MagicMock()
    cases_result.scalars.return_value.all.return_value = []

    session = AsyncMock()
    session.execute = _execute_results(research_result, cases_result, _no_audit_row())

    research_status, research_out, _, _ = await client_router._bootstrap_research_and_cases(
        session, ctx, profile
    )

    assert research_status == "error"
    assert research_out is None


@pytest.mark.asyncio
async def test_no_prior_run_or_match_is_idle():
    profile = _fake_profile()
    ctx = _fake_ctx(profile)

    research_result = MagicMock()
    research_result.scalar_one_or_none.return_value = None
    cases_result = MagicMock()
    cases_result.scalars.return_value.all.return_value = []

    session = AsyncMock()
    session.execute = _execute_results(research_result, cases_result, _no_audit_row())

    research_status, research_out, cases_status, cases_out = (
        await client_router._bootstrap_research_and_cases(session, ctx, profile)
    )

    assert (research_status, research_out) == ("idle", None)
    assert (cases_status, cases_out) == ("idle", None)


@pytest.mark.asyncio
async def test_zero_match_run_falls_back_to_audit_log_done_with_empty_matches():
    """A case-match run that found nothing inserts zero CaseMatch rows —
    row-existence alone can't tell that apart from 'never ran'. A workspace
    with no case library attached hits this on every single run, and
    without the audit-log fallback the chapter would read 'Matching now…'
    forever after a reload instead of 'Cases matched' with zero results."""
    profile = _fake_profile()
    ctx = _fake_ctx(profile)

    research_result = MagicMock()
    research_result.scalar_one_or_none.return_value = None
    cases_result = MagicMock()
    cases_result.scalars.return_value.all.return_value = []
    audit_result = MagicMock()
    audit_result.scalar_one_or_none.return_value = uuid.uuid4()  # a case_matched row exists

    session = AsyncMock()
    session.execute = _execute_results(research_result, cases_result, audit_result)

    _, _, cases_status, cases_out = await client_router._bootstrap_research_and_cases(
        session, ctx, profile
    )

    assert cases_status == "done"
    assert cases_out == {"matches": []}


def test_cases_out_handles_missing_card():
    """A CaseMatch row whose file no longer resolves to a card (file
    deleted from the library after matching) must still render — just
    without the optional card fields, not raise."""
    row = _fake_match_row(0.5)
    out = client_router._cases_out([(row, None)])
    assert out["matches"][0]["title"] is None
    assert out["matches"][0]["file_id"] == str(row.file_id)
