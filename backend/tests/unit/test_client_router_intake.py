"""Unit tests for POST /client/intake/answer's insight off-by-one.

app/services/client_intake.py's IntakeStep.insight belongs to the step just
answered — what น้องภูมิ concluded from that answer — and must ride on the
response alongside the NEXT question, not get silently dropped or swapped
for the next step's insight. answer_intake() captures step_def BEFORE
incrementing profile.step specifically to get this right; these tests pin
that behavior so a future refactor can't reintroduce the off-by-one.

Heavy DB/crypto/audit machinery is mocked out — this exercises only
answer_intake()'s own logic, not persistence (which is exercised via the
real Postgres integration suite for the client workspace elsewhere).
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.client_intake import ClientProfile
from app.routers import client as client_router
from app.services.client_intake import INTAKE_SCRIPT


def _fake_profile(step: int) -> ClientProfile:
    profile = ClientProfile(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        step=step,
        fields_ciphertext=b"", fields_nonce=b"", fields_tag=b"", key_version=1,
    )
    profile.id = uuid.uuid4()
    return profile


def _fake_ctx(user_id: uuid.UUID, workspace_id: uuid.UUID) -> MagicMock:
    ctx = MagicMock()
    ctx.user.id = user_id
    ctx.workspace_id = workspace_id
    return ctx


@pytest.mark.asyncio
async def test_insight_belongs_to_the_step_just_answered():
    profile = _fake_profile(step=0)
    ctx = _fake_ctx(profile.user_id, profile.workspace_id)
    session = AsyncMock()

    with (
        patch.object(client_router, "_get_or_create_profile", new=AsyncMock(return_value=profile)),
        patch.object(client_router, "_decrypt_fields", return_value={}),
        patch.object(client_router, "_encrypt_fields", return_value=(b"", b"", b"", 1)),
        patch.object(client_router.audit_svc, "log", new=AsyncMock()),
    ):
        body = client_router.IntakeAnswerIn(option_index=0, free_text=None)
        result = await client_router.answer_intake(body, ctx, session)

    # Answering step 0 must return step 0's insight — not step 1's, even
    # though current_step now points at step 1 (profile.step was incremented
    # for the NEXT question before this function returned).
    assert result.insight == INTAKE_SCRIPT[0]["insight"]
    assert result.current_step is not None
    assert result.current_step.field == INTAKE_SCRIPT[1]["field"]
    assert result.completed is False


@pytest.mark.asyncio
async def test_final_answer_returns_last_steps_insight_and_completes():
    last_index = len(INTAKE_SCRIPT) - 1
    profile = _fake_profile(step=last_index)
    ctx = _fake_ctx(profile.user_id, profile.workspace_id)
    session = AsyncMock()

    with (
        patch.object(client_router, "_get_or_create_profile", new=AsyncMock(return_value=profile)),
        patch.object(client_router, "_decrypt_fields", return_value={}),
        patch.object(client_router, "_encrypt_fields", return_value=(b"", b"", b"", 1)),
        patch.object(client_router.audit_svc, "log", new=AsyncMock()),
    ):
        body = client_router.IntakeAnswerIn(option_index=0, free_text=None)
        result = await client_router.answer_intake(body, ctx, session)

    assert result.completed is True
    assert result.insight == INTAKE_SCRIPT[last_index]["insight"]
    assert result.completion_message
    assert result.current_step is None
