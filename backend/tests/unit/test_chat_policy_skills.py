"""
Unit tests for the skill-selection integration inside
app/services/chat_policy.py::prepare_chat.

Covers:
- a skill pinned to the active agent is always injected into system_prompt,
  appended after the agent's own instructions, and a skill_invoked audit row
  is written
- a /slug in the message forces that skill in, even with no agent active
- when no skill is selected, system_prompt is untouched and no skill_invoked
  audit row is written
- skill selection never bypasses PolicyEngine.decide() (§7.2): a downgrade
  decision still applies with a skill active
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.router import LOCAL_MODEL_CODE
from app.services.chat_policy import prepare_chat


def _make_user(role: str = "L3") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    # D21/D22: internal user (unchanged pre-Client-Workspaces behavior).
    user.workspace_id = None
    return user


def _make_agent(instructions: str = "You are helpful.") -> MagicMock:
    agent = MagicMock()
    agent.id = uuid.uuid4()
    agent.instructions = instructions
    agent.creativity_level = 50
    agent.capabilities = {}
    agent.model = "claude-sonnet-4"
    return agent


def _make_skill(name: str, instructions: str) -> MagicMock:
    skill = MagicMock()
    skill.id = uuid.uuid4()
    skill.name = name
    skill.description = f"{name} description"
    skill.instructions = instructions
    skill.enabled = True
    return skill


def _allowed_decision(model_code: str = LOCAL_MODEL_CODE, downgrade: bool = False):
    from app.services.policy_engine import PolicyDecision
    return PolicyDecision(
        allowed=True, model_code=model_code, downgrade_to_local=downgrade, reasons=[],
    )


def _new_conversation_session() -> AsyncMock:
    """Session mock for conversation_id=None: two execute()s for the empty
    message-history windows (the free-form one the model is shown and the
    unfiltered one the §7.6 tier scan reads — see
    chat_policy.load_history_messages), one for the title/agent_id sa_update.
    All other DB activity (agent/skill lookups) is patched at the
    service-function level below, so this fixed triple is never exceeded.
    """
    msg_result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = []
    msg_result.scalars.return_value = scalars

    update_result = MagicMock()

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[msg_result, msg_result, update_result])
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


async def _run_prepare(
    *,
    user_content: str,
    agent_id=None,
    agent=None,
    pinned_skill_ids=None,
    candidates=None,
    matched=None,
    decision=None,
):
    user = _make_user()
    session = _new_conversation_session()

    with patch("app.services.chat_policy.PolicyEngine") as mock_pe, \
         patch("app.services.chat_policy.rag_search") as mock_rag, \
         patch("app.services.chat_policy.classify_intent", new_callable=AsyncMock, return_value=LOCAL_MODEL_CODE), \
         patch("app.services.chat_policy.settings") as mock_settings, \
         patch("app.services.chat_policy.alert") as mock_alert, \
         patch("app.services.chat_policy.agent_svc.get_agent", new_callable=AsyncMock, return_value=agent), \
         patch("app.services.chat_policy.agent_svc.get_agent_file_ids", new_callable=AsyncMock, return_value=[]), \
         patch("app.services.chat_policy.skill_svc.get_agent_skill_ids", new_callable=AsyncMock, return_value=pinned_skill_ids or []), \
         patch("app.services.chat_policy.skill_svc.get_enabled_skills", new_callable=AsyncMock, return_value=candidates or []), \
         patch("app.services.skill_selector.match_skills_by_description", new_callable=AsyncMock, return_value=matched or []), \
         patch("app.services.chat_policy.audit_svc.log", new_callable=AsyncMock) as audit_log:
        mock_pe.return_value.decide = AsyncMock(return_value=decision or _allowed_decision())
        mock_rag.retrieve = AsyncMock(return_value=[])
        mock_rag.build_context_block.return_value = ""
        mock_rag.citations.return_value = []
        mock_settings.n8n_webhook_url = ""
        mock_alert.matches_alert.return_value = False

        prepared = await prepare_chat(
            session=session,
            user=user,
            conversation_id=None,
            user_content=user_content,
            requested_model="auto",
            agent_id=agent_id,
        )
    return prepared, audit_log


class TestPinnedSkill:
    async def test_pinned_skill_injected_after_agent_instructions(self):
        agent = _make_agent("You are helpful.")
        skill = _make_skill("persona", "Always respond in a formal tone.")

        prepared, _ = await _run_prepare(
            user_content="hello",
            agent_id=agent.id,
            agent=agent,
            pinned_skill_ids=[skill.id],
            candidates=[skill],
            matched=[],
        )

        assert "You are helpful." in prepared.system_prompt
        assert "# Skill: persona" in prepared.system_prompt
        assert "Always respond in a formal tone." in prepared.system_prompt
        assert prepared.system_prompt.index("You are helpful.") < prepared.system_prompt.index("# Skill: persona")

    async def test_pinned_skill_audits_skill_invoked(self):
        agent = _make_agent()
        skill = _make_skill("persona", "Always respond in a formal tone.")

        _, audit_log = await _run_prepare(
            user_content="hello",
            agent_id=agent.id,
            agent=agent,
            pinned_skill_ids=[skill.id],
            candidates=[skill],
            matched=[],
        )

        calls = [c.kwargs for c in audit_log.call_args_list]
        invoked = next((c for c in calls if c["action"] == "skill_invoked"), None)
        assert invoked is not None
        assert invoked["details"]["skills"] == ["persona"]
        assert invoked["details"]["pinned"] == [str(skill.id)]
        assert invoked["details"]["forced"] == []


class TestForcedSlug:
    async def test_forced_slug_injected_without_agent(self):
        skill = _make_skill("weekly-report", "Summarize the week.")

        prepared, audit_log = await _run_prepare(
            user_content="/weekly-report give me the numbers",
            candidates=[skill],
            matched=[],
        )

        assert "# Skill: weekly-report" in prepared.system_prompt
        assert "Summarize the week." in prepared.system_prompt
        calls = [c.kwargs for c in audit_log.call_args_list]
        invoked = next((c for c in calls if c["action"] == "skill_invoked"), None)
        assert invoked is not None
        assert invoked["details"]["forced"] == ["weekly-report"]
        assert invoked["details"]["pinned"] == []


class TestNoSkillSelected:
    async def test_no_candidates_leaves_system_prompt_empty(self):
        prepared, audit_log = await _run_prepare(user_content="hello", candidates=[])

        assert prepared.system_prompt == ""
        actions = [c.kwargs["action"] for c in audit_log.call_args_list]
        assert "skill_invoked" not in actions

    async def test_unmatched_candidate_not_injected(self):
        skill = _make_skill("morning", "Render the morning brief.")

        prepared, audit_log = await _run_prepare(
            user_content="hello", candidates=[skill], matched=[],
        )

        assert prepared.system_prompt == ""
        actions = [c.kwargs["action"] for c in audit_log.call_args_list]
        assert "skill_invoked" not in actions


class TestPolicyStillGates:
    async def test_downgrade_decision_still_applies_with_skill_active(self):
        """§7.2: skill selection must never bypass PolicyEngine.decide()."""
        skill = _make_skill("weekly-report", "Summarize the week.")
        downgrade_decision = _allowed_decision(model_code=LOCAL_MODEL_CODE, downgrade=True)

        prepared, _ = await _run_prepare(
            user_content="/weekly-report numbers please",
            candidates=[skill],
            matched=[],
            decision=downgrade_decision,
        )

        assert prepared.model_code == LOCAL_MODEL_CODE
        assert prepared.downgrade_to_local is True
        # the skill still applies — downgrade and skill injection are orthogonal
        assert "# Skill: weekly-report" in prepared.system_prompt
