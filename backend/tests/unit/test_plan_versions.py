"""Unit tests for plan_svc.get_version() / decrypt_version_body() (Task
5.12 — the version rail's "read an old version" affordance).

DB redesign: plan_versions gained UNIQUE(plan_id, version_no) (renamed
from `version`), so get_version() is now a genuine scalar_one_or_none()
lookup instead of the old "no unique constraint, take the newest match"
workaround — see app/services/plan.py::get_version. title is NOT NULL now
(no more "fell back to the parent Plan's title" case — every version
snapshots its own).

Same fixture pattern as test_plan_revise.py: the default unit-test
ENCRYPTION_KEY in tests/unit/conftest.py decodes to 28 bytes, not a valid
AES-GCM key length, so a valid 32-byte key is installed for this module and
decrypt_version_body() is exercised against a real crypto.encrypt() round
trip rather than a mock.
"""
from __future__ import annotations

import base64
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app import crypto
from app.services import plan as plan_svc


@pytest.fixture(autouse=True)
def set_encryption_key(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", base64.b64encode(b"A" * 32).decode())
    import app.crypto as crypto_mod
    crypto_mod._key = None
    yield
    crypto_mod._key = None


def _version_row(*, plan_id, version_no, title, body):
    ct, nonce, tag, kv = crypto.encrypt(json.dumps(body))
    v = MagicMock()
    v.plan_id = plan_id
    v.version_no = version_no
    v.title = title
    v.body_ciphertext = ct
    v.body_nonce = nonce
    v.body_tag = tag
    v.key_version = kv
    return v


@pytest.mark.asyncio
async def test_get_version_returns_the_matching_row_and_its_body_decrypts():
    user = MagicMock()
    user.id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    plan = MagicMock(id=plan_id)

    v1 = _version_row(
        plan_id=plan_id, version_no=1, title="v1 title",
        body={"core_idea": "v1 idea", "analogous_case": "", "adapted_plan": []},
    )

    result = MagicMock()
    result.scalar_one_or_none.return_value = v1
    session = AsyncMock()
    session.execute.return_value = result

    with patch.object(plan_svc, "get_plan", new=AsyncMock(return_value=plan)):
        found = await plan_svc.get_version(session, user, workspace_id, plan_id, 1)

    assert found is v1
    body = plan_svc.decrypt_version_body(found)
    assert body["core_idea"] == "v1 idea"


@pytest.mark.asyncio
async def test_get_version_404s_when_no_row_matches():
    user = MagicMock()
    user.id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    plan = MagicMock(id=plan_id)

    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session = AsyncMock()
    session.execute.return_value = result

    with patch.object(plan_svc, "get_plan", new=AsyncMock(return_value=plan)):
        with pytest.raises(HTTPException) as exc_info:
            await plan_svc.get_version(session, user, workspace_id, plan_id, 99)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_version_404s_for_a_plan_the_caller_does_not_own():
    # get_plan() is the ownership check — get_version() must call it before
    # touching PlanVersion at all, same contract as revise_plan().
    user = MagicMock()
    user.id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    plan_id = uuid.uuid4()

    session = AsyncMock()

    with patch.object(
        plan_svc,
        "get_plan",
        new=AsyncMock(side_effect=HTTPException(status_code=404, detail="Plan not found")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await plan_svc.get_version(session, user, workspace_id, plan_id, 1)

    assert exc_info.value.status_code == 404
    session.execute.assert_not_called()


def test_decrypt_version_body_round_trips():
    v = _version_row(
        plan_id=uuid.uuid4(), version_no=2, title="v2 title",
        body={"core_idea": "idea", "analogous_case": "case", "adapted_plan": [{"period": "Wk 1", "text": "x"}]},
    )
    body = plan_svc.decrypt_version_body(v)
    assert body == {"core_idea": "idea", "analogous_case": "case", "adapted_plan": [{"period": "Wk 1", "text": "x"}]}
