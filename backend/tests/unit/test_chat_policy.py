"""Orchestration-level test for the downgrade → audit → SSE path (Task 2.2).

Fidelity note:
    This test uses a mocked AsyncSession (no real Postgres), which means it
    proves control flow and data shapes but not actual SQL execution or partition
    routing. A true DB-backed E2E test is deferred until an integration harness
    exists (planned alongside Task 2.4).

Thai national ID acceptance case (integration acceptance criterion):
    Sending model=claude-sonnet-4 with a Thai national ID in the message must:
    - succeed (no exception)
    - result in model_code=qwen2.5-14b-local (downgraded)
    - write an audit row with action="tier_blocked",
      details["model_used"]="qwen2.5-14b-local",
      details["model_requested"]="claude-sonnet-4"
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

import app.services.classifier as classifier_module
from app.llm.router import DEFAULT_MODEL_CODE
from app.models.classification import DataTier
from app.models.user import User
from app.services.chat_policy import PreparedChat, prepare_chat
from app.services.classifier import _compile_rules


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_user(role: str = "L3") -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.role = role
    # D21/D22: internal user (unchanged pre-Client-Workspaces behavior).
    # Explicit — an un-set MagicMock attribute is truthy/not-None and would
    # spuriously trip PolicyEngine's workspace-budget branch.
    user.workspace_id = None
    return user


def _thai_id_row():
    return SimpleNamespace(
        name="Thai National ID",
        pattern_type="regex",
        pattern=r"\d-\d{4}-\d{5}-\d{2}-\d",
        detected_tier="TIER_3_CONFIDENTIAL",
    )


@pytest.fixture(autouse=True)
def seed_classifier():
    """Load the Thai-ID rule into the in-process classifier cache."""
    classifier_module._RULES = _compile_rules([_thai_id_row()])
    yield
    classifier_module._RULES = []


@pytest.fixture(autouse=True)
def no_skills(monkeypatch):
    """Skip the skills DB lookup for tests that don't exercise skills.

    prepare_chat() unconditionally calls skill_svc.get_enabled_skills() to
    build the auto-match candidate list; none of these hand-built session
    mocks have a spare session.execute() side effect for that extra query,
    so it's stubbed out here rather than padding every side_effect list.
    """
    monkeypatch.setattr(
        "app.services.chat_policy.skill_svc.get_enabled_skills",
        AsyncMock(return_value=[]),
    )


def _active_model_result(code: str) -> MagicMock:
    model = MagicMock()
    model.is_active = True
    model.code = code
    r = MagicMock()
    r.scalar_one_or_none.return_value = model
    return r


def _empty_msgs() -> MagicMock:
    """One empty Message-window result."""
    result = MagicMock()
    result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
    return result


def _empty_history_session(model_code: str = "claude-sonnet-4") -> AsyncMock:
    """
    Session mock that satisfies:
    - load_history_messages: TWO Message-list executes (empty) — the free-form
      window the model is shown and the unfiltered window the §7.6 tier scan
      reads. conversation_id=None here, so no Conversation SELECT.
    - the new-conversation auto-title UPDATE
    - _get_model: returns active model for `model_code`
    The session is reused so we track all add() calls.
    """
    conv = MagicMock()
    conv.id = uuid.uuid4()

    # _get_model → active external model
    model_result = _active_model_result(model_code)

    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[_empty_msgs(), _empty_msgs(), MagicMock(), model_result]
    )
    # flush() resolves the Conversation insert — give the conv a real id
    async def _flush():
        # After flush, the Conversation added via session.add() needs an id.
        # We patch it by inspecting the add calls below in the test.
        pass
    session.flush = AsyncMock(side_effect=_flush)
    session.commit = AsyncMock()
    session.add = MagicMock()  # synchronous — collects all added ORM objects
    return session, conv.id


# ---------------------------------------------------------------------------
# Core acceptance test: Thai ID with claude-sonnet-4 → downgrade → tier_blocked audit
# ---------------------------------------------------------------------------

class TestThaiIDDowngrade:
    async def test_downgrade_writes_tier_blocked_audit(self, _silence_audit_celery):
        """
        Sending a message containing a Thai national ID (TIER_3) with
        model=claude-sonnet-4 must:
        - return PreparedChat with model_code=local and downgrade_to_local=True
        - enqueue a tier_blocked audit event (via Celery, no direct DB write)
        - also enqueue a pii_detected event for TIER_3 content
        """
        user = _make_user("L3")
        session, _conv_id = _empty_history_session("claude-sonnet-4")

        # Valid Thai ID that passes the mod-11 checksum
        thai_id_content = "My ID is 1-2345-67890-12-1, please help."

        prepared = await prepare_chat(
            session=session,
            user=user,
            conversation_id=None,
            user_content=thai_id_content,
            requested_model="claude-sonnet-4",
        )

        # Policy decision
        assert prepared.model_code == DEFAULT_MODEL_CODE
        assert prepared.downgrade_to_local is True

        # audit.log() is now a direct async call (no Celery broker).
        # _silence_audit_celery is an AsyncMock; inspect via .call_args_list[i].kwargs.
        calls = [c.kwargs for c in _silence_audit_celery.call_args_list]
        actions = [c["action"] for c in calls]
        assert "pii_detected" in actions, f"Expected pii_detected, got {actions}"
        assert "tier_blocked" in actions, f"Expected tier_blocked, got {actions}"

        tier_blocked = next(c for c in calls if c["action"] == "tier_blocked")
        assert tier_blocked["details"]["model_used"] == DEFAULT_MODEL_CODE
        assert tier_blocked["details"]["model_requested"] == "claude-sonnet-4"
        assert tier_blocked["user_id"] == user.id

        # Session still committed — for the conversation row created in load_history
        session.commit.assert_called_once()

    async def test_downgrade_reasons_contain_tier_blocks_external(self):
        user = _make_user("L3")
        session, _ = _empty_history_session("claude-sonnet-4")
        session.add = MagicMock()

        prepared = await prepare_chat(
            session=session,
            user=user,
            conversation_id=None,
            user_content="My ID is 1-2345-67890-12-1",
            requested_model="claude-sonnet-4",
        )
        assert "tier_blocks_external" in prepared.reasons


# ---------------------------------------------------------------------------
# Auto-model → always local (no DB calls for policy needed)
# ---------------------------------------------------------------------------

class TestAutoModel:
    async def test_auto_model_stays_local(self):
        """model='auto' resolves to DEFAULT_MODEL_CODE before decide()."""
        user = _make_user("L1")

        conv_result = MagicMock()
        conv_result.scalar_one_or_none.return_value = None
        msg_result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = []
        msg_result.scalars.return_value = scalars

        session = AsyncMock()
        # Two history windows (chat + unfiltered), then the auto-title UPDATE.
        session.execute = AsyncMock(side_effect=[conv_result, msg_result, MagicMock()])
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.add = MagicMock()

        prepared = await prepare_chat(
            session=session,
            user=user,
            conversation_id=None,
            user_content="Hello!",
            requested_model="auto",
        )
        assert prepared.model_code == DEFAULT_MODEL_CODE
        assert prepared.downgrade_to_local is False


# ---------------------------------------------------------------------------
# Deny path: Tier4 + low role → HTTPException(403)
# ---------------------------------------------------------------------------

class TestDenyPath:
    async def test_tier4_low_role_raises_403(self):
        from fastapi import HTTPException

        # Seed a Tier-4 keyword rule
        tier4_row = SimpleNamespace(
            name="Project Apollo",
            pattern_type="keyword",
            pattern="Project Apollo",
            detected_tier="TIER_4_RESTRICTED",
        )
        classifier_module._RULES = _compile_rules([tier4_row])

        user = _make_user("L3")  # not L5+, so Tier4 denies even local

        conv_result = MagicMock()
        conv_result.scalar_one_or_none.return_value = None
        msg_result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = []
        msg_result.scalars.return_value = scalars

        session = AsyncMock()
        # Two history windows (chat + unfiltered), then the auto-title UPDATE.
        session.execute = AsyncMock(side_effect=[conv_result, msg_result, MagicMock()])
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.add = MagicMock()

        with pytest.raises(HTTPException) as exc:
            await prepare_chat(
                session=session,
                user=user,
                conversation_id=None,
                user_content="Project Apollo M&A target list",
                requested_model=DEFAULT_MODEL_CODE,
            )
        assert exc.value.status_code == 403
        assert exc.value.detail["error"] == "policy_denied"
        assert "tier_4_requires_L5" in exc.value.detail["reasons"]


# ---------------------------------------------------------------------------
# SSE downgrade notice is emitted before content
# ---------------------------------------------------------------------------

class TestSSEDowngradeNotice:
    async def test_downgrade_notice_precedes_content(self):
        """The orchestrator emits a notice/downgrade_to_local event before LLM content."""
        import asyncio

        from app.agents.orchestrator import run_chat_stream

        # Fake streaming LLM client
        async def _fake_stream(messages, **_):
            from app.llm.base import ChatChunk
            yield ChatChunk(content="Hello", prompt_tokens=5, completion_tokens=3)

        fake_client = MagicMock()
        fake_client.stream_chat = _fake_stream

        # Minimal session for the orchestrator (no DB calls — history pre-loaded)
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        user_id = uuid.uuid4()
        conv_id = uuid.uuid4()

        events: list[dict] = []
        with patch("app.agents.orchestrator.get_router") as mock_router:
            mock_router.return_value.get.return_value = fake_client
            async for line in run_chat_stream(
                session=session,
                user_id=user_id,
                user=MagicMock(),
                resolved_conversation_id=conv_id,
                user_content="My ID is 1-2345-67890-12-1",
                model_code=DEFAULT_MODEL_CODE,
                history=[],
                downgrade_to_local=True,
                reasons=["tier_blocks_external"],
            ):
                payload = json.loads(line.removeprefix("data: ").strip())
                events.append(payload)

        types_in_order = [e["type"] for e in events]
        assert "notice" in types_in_order
        assert "content" in types_in_order
        notice_idx = types_in_order.index("notice")
        content_idx = types_in_order.index("content")
        assert notice_idx < content_idx, "notice must precede content"

        notice = events[notice_idx]
        assert notice["event"] == "downgrade_to_local"
        assert notice["reason"] == "tier_blocks_external"


# ---------------------------------------------------------------------------
# n8n_route detection: prepare_chat sets the flag when URL is set + keyword matches
# ---------------------------------------------------------------------------

def _allowed_decision(model_code: str = DEFAULT_MODEL_CODE):
    """Build a minimal mock PolicyDecision that is allowed / no downgrade."""
    from app.services.policy_engine import PolicyDecision
    return PolicyDecision(
        allowed=True,
        model_code=model_code,
        downgrade_to_local=False,
        reasons=[],
    )


def _session_for_n8n_route() -> AsyncMock:
    """Minimal session for n8n_route detection tests.

    Satisfies:
    - load_history_messages: TWO Message list executes (new conv — no
      Conversation lookup). One window is the free-form turns the model is
      shown, the other every turn, for the §7.6 tier scan.
    - prepare_chat sa_update for title: returns a generic mock
    All other DB activity is patched at a higher level.
    """
    msg_result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = []
    msg_result.scalars.return_value = scalars

    update_result = MagicMock()  # sa_update title — return value unused

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[msg_result, msg_result, update_result])
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


class TestN8nRouteDetection:
    """Verify that prepare_chat sets PreparedChat.n8n_route correctly.

    PolicyEngine.decide(), rag_search.retrieve(), and classify_intent() are all
    patched so only the n8n_route detection logic is exercised.
    """

    async def _run_prepare(
        self,
        user_content: str,
        n8n_webhook_url: str,
        alert_matches: bool,
    ) -> "PreparedChat":
        user = _make_user("L3")
        session = _session_for_n8n_route()
        with patch("app.services.chat_policy.PolicyEngine") as mock_pe, \
             patch("app.services.chat_policy.rag_search") as mock_rag, \
             patch("app.services.chat_policy.classify_intent", new_callable=AsyncMock, return_value=DEFAULT_MODEL_CODE), \
             patch("app.services.chat_policy.settings") as mock_settings, \
             patch("app.services.chat_policy.alert") as mock_alert:
            mock_pe.return_value.decide = AsyncMock(return_value=_allowed_decision())
            mock_rag.retrieve = AsyncMock(return_value=[])
            mock_rag.build_context_block.return_value = ""
            mock_rag.citations.return_value = []
            mock_settings.n8n_webhook_url = n8n_webhook_url
            mock_alert.matches_alert.return_value = alert_matches

            return await prepare_chat(
                session=session,
                user=user,
                conversation_id=None,
                user_content=user_content,
                requested_model="auto",
            )

    async def test_n8n_route_set_when_keyword_matches_and_url_configured(self):
        """n8n_route=True when URL is set and message matches a keyword."""
        prepared = await self._run_prepare(
            user_content="the server is down",
            n8n_webhook_url="https://n8n.test/webhook/alert",
            alert_matches=True,
        )
        assert prepared.n8n_route is True

    async def test_n8n_route_false_when_url_blank(self):
        """n8n_route=False when N8N_WEBHOOK_URL is empty — feature disabled."""
        prepared = await self._run_prepare(
            user_content="the server is down",
            n8n_webhook_url="",
            alert_matches=True,  # would match but URL blank
        )
        assert prepared.n8n_route is False

    async def test_n8n_route_false_when_no_keyword_match(self):
        """n8n_route=False when message has no matching keyword."""
        prepared = await self._run_prepare(
            user_content="hello, how are you?",
            n8n_webhook_url="https://n8n.test/webhook/alert",
            alert_matches=False,
        )
        assert prepared.n8n_route is False
