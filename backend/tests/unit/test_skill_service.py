"""
Unit tests for app/services/skill.py.

Covers:
- validate_slug: accepts kebab-case, rejects invalid slugs
- parse_skill_markdown: frontmatter extraction, missing frontmatter fallback
- create_skill / create_skill_from_markdown: persists, audits skill_created
- get_skill: own skill visible, other user's public skill visible, personal not
- list_skills: scope=all vs scope=mine
- update_skill: owner succeeds (incl. enabled toggle), non-owner gets 404
- delete_skill: owner succeeds, non-owner gets 404
- attach_skill / detach_skill / get_agent_skill_ids: agent-pin helpers
- build_skill_system_block: formats selected skills into a labelled block
- draft_skill: "Create with AI" conversational drafting (local model only)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.skill import (
    build_skill_system_block,
    parse_skill_markdown,
    validate_slug,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_user(role: str = "L3", workspace_id: uuid.UUID | None = None) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    # Explicit default (staff): a bare MagicMock would auto-vivify
    # workspace_id to a truthy child Mock, which is_client_seat() would
    # read as a client seat — see D23 in app/services/workspace.py.
    user.workspace_id = workspace_id
    return user


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    async def _refresh(obj):
        if not getattr(obj, "id", None):
            obj.id = uuid.uuid4()
        obj.created_at = datetime.now(timezone.utc)
        obj.updated_at = datetime.now(timezone.utc)

    session.refresh = _refresh
    session.execute = AsyncMock()
    return session


def _make_skill(
    user_id: uuid.UUID,
    name: str = "weekly-report",
    visibility: str = "personal",
    enabled: bool = True,
    instructions: str = "Summarize wins, blockers, next steps.",
) -> MagicMock:
    skill = MagicMock()
    skill.id = uuid.uuid4()
    skill.user_id = user_id
    skill.name = name
    skill.description = "Generate weekly status reports."
    skill.instructions = instructions
    skill.source_markdown = None
    skill.enabled = enabled
    skill.visibility = visibility
    skill.category = None
    skill.created_at = datetime.now(timezone.utc)
    skill.updated_at = datetime.now(timezone.utc)
    return skill


# ---------------------------------------------------------------------------
# validate_slug
# ---------------------------------------------------------------------------

class TestValidateSlug:
    def test_accepts_kebab_case(self):
        assert validate_slug("weekly-status-report") == "weekly-status-report"

    def test_accepts_single_word(self):
        assert validate_slug("morning") == "morning"

    def test_accepts_leading_digit(self):
        assert validate_slug("3d-render") == "3d-render"

    def test_rejects_empty(self):
        with pytest.raises(HTTPException) as exc:
            validate_slug("")
        assert exc.value.status_code == 400

    def test_rejects_uppercase(self):
        with pytest.raises(HTTPException):
            validate_slug("WeeklyReport")

    def test_rejects_spaces(self):
        with pytest.raises(HTTPException):
            validate_slug("weekly report")

    def test_rejects_leading_hyphen(self):
        with pytest.raises(HTTPException):
            validate_slug("-weekly")

    def test_rejects_underscore(self):
        with pytest.raises(HTTPException):
            validate_slug("weekly_report")

    def test_rejects_too_long(self):
        with pytest.raises(HTTPException):
            validate_slug("a" * 65)


# ---------------------------------------------------------------------------
# parse_skill_markdown
# ---------------------------------------------------------------------------

class TestParseSkillMarkdown:
    def test_parses_name_and_description_from_frontmatter(self):
        raw = (
            "---\n"
            "name: weekly-status-report\n"
            "description: Generate weekly status reports. Use when asked for updates.\n"
            "---\n\n"
            "Summarize recent work in three sections: wins, blockers, next steps."
        )
        name, description, body = parse_skill_markdown(raw)
        assert name == "weekly-status-report"
        assert description == "Generate weekly status reports. Use when asked for updates."
        assert body == "Summarize recent work in three sections: wins, blockers, next steps."

    def test_strips_quotes_from_frontmatter_values(self):
        raw = '---\nname: "morning"\ndescription: \'The morning brief\'\n---\nBody text'
        name, description, body = parse_skill_markdown(raw)
        assert name == "morning"
        assert description == "The morning brief"

    def test_no_frontmatter_returns_raw_as_body(self):
        raw = "Just plain instructions, no frontmatter fences."
        name, description, body = parse_skill_markdown(raw)
        assert name is None
        assert description is None
        assert body == raw

    def test_unclosed_frontmatter_fence_falls_back_to_raw(self):
        raw = "---\nname: broken\nno closing fence here"
        name, description, body = parse_skill_markdown(raw)
        assert name is None
        assert body == raw.strip()

    def test_ignores_unknown_frontmatter_keys(self):
        raw = "---\nname: x\nallowed-tools: Read Grep\n---\nBody"
        name, description, body = parse_skill_markdown(raw)
        assert name == "x"
        assert description is None
        assert body == "Body"


# ---------------------------------------------------------------------------
# create_skill / create_skill_from_markdown
# ---------------------------------------------------------------------------

class TestCreateSkill:
    async def test_create_persists_and_audits(self):
        from app.services import skill as skill_svc

        user = _make_user()
        session = _make_session()
        # _check_unique_name: no existing skill with that name
        no_existing = MagicMock()
        no_existing.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=no_existing)

        with patch("app.services.skill.audit_svc.log", AsyncMock()) as audit_log:
            result = await skill_svc.create_skill(
                session=session,
                user=user,
                name="weekly-status-report",
                description="Generate weekly status reports.",
                instructions="Summarize wins, blockers, next steps.",
            )

        assert session.add.called
        assert session.commit.called
        assert result.name == "weekly-status-report"
        assert result.user_id == user.id
        audit_log.assert_called_once()
        assert audit_log.call_args.kwargs.get("action") == "skill_created"

    async def test_rejects_invalid_slug(self):
        from app.services import skill as skill_svc

        user = _make_user()
        session = _make_session()

        with pytest.raises(HTTPException) as exc:
            await skill_svc.create_skill(session=session, user=user, name="Not A Slug")
        assert exc.value.status_code == 400

    async def test_rejects_duplicate_name_for_same_user(self):
        from app.services import skill as skill_svc

        user = _make_user()
        session = _make_session()
        existing = MagicMock()
        existing.scalar_one_or_none = MagicMock(return_value=MagicMock())
        session.execute = AsyncMock(return_value=existing)

        with pytest.raises(HTTPException) as exc:
            await skill_svc.create_skill(session=session, user=user, name="morning")
        assert exc.value.status_code == 400

    async def test_create_from_markdown_uses_frontmatter(self):
        from app.services import skill as skill_svc

        user = _make_user()
        session = _make_session()
        no_existing = MagicMock()
        no_existing.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=no_existing)

        raw = (
            "---\nname: morning\ndescription: The morning brief\n---\n"
            "Render the user's morning brief."
        )
        with patch("app.services.skill.audit_svc.log", AsyncMock()):
            result = await skill_svc.create_skill_from_markdown(
                session=session, user=user, raw_markdown=raw,
            )

        assert result.name == "morning"
        assert result.description == "The morning brief"
        assert result.instructions == "Render the user's morning brief."
        assert result.source_markdown == raw

    async def test_create_from_markdown_without_name_raises(self):
        from app.services import skill as skill_svc

        user = _make_user()
        session = _make_session()

        with pytest.raises(HTTPException) as exc:
            await skill_svc.create_skill_from_markdown(
                session=session, user=user, raw_markdown="No frontmatter here.",
            )
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# get_skill / accessibility
# ---------------------------------------------------------------------------

class TestGetSkill:
    async def test_owner_can_access_own_skill(self):
        from app.services import skill as skill_svc

        user = _make_user()
        skill = _make_skill(user_id=user.id, visibility="personal")
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=skill)
        session.execute = AsyncMock(return_value=mock_result)

        result = await skill_svc.get_skill(session, skill.id, user.id)
        assert result is skill

    async def test_public_skill_accessible_to_others(self):
        from app.services import skill as skill_svc

        owner = _make_user()
        other = _make_user()
        skill = _make_skill(user_id=owner.id, visibility="public")
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=skill)
        session.execute = AsyncMock(return_value=mock_result)

        result = await skill_svc.get_skill(session, skill.id, other.id)
        assert result is skill

    async def test_personal_skill_not_accessible_to_others(self):
        from app.services import skill as skill_svc

        other = _make_user()
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=mock_result)

        result = await skill_svc.get_skill(session, uuid.uuid4(), other.id)
        assert result is None


# ---------------------------------------------------------------------------
# update_skill
# ---------------------------------------------------------------------------

class TestUpdateSkill:
    async def test_owner_can_update(self):
        from app.services import skill as skill_svc

        user = _make_user()
        skill = _make_skill(user_id=user.id, name="old-name")
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=skill)
        session.execute = AsyncMock(return_value=mock_result)

        with patch("app.services.skill.audit_svc.log", AsyncMock()) as audit_log:
            result = await skill_svc.update_skill(
                session, user, skill.id, description="New description"
            )

        assert result.description == "New description"
        assert audit_log.called
        assert audit_log.call_args.kwargs.get("action") == "skill_updated"

    async def test_owner_can_toggle_enabled(self):
        from app.services import skill as skill_svc

        user = _make_user()
        skill = _make_skill(user_id=user.id, enabled=True)
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=skill)
        session.execute = AsyncMock(return_value=mock_result)

        with patch("app.services.skill.audit_svc.log", AsyncMock()):
            result = await skill_svc.update_skill(session, user, skill.id, enabled=False)

        assert result.enabled is False

    async def test_non_owner_gets_404(self):
        from app.services import skill as skill_svc

        user = _make_user()
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc:
            await skill_svc.update_skill(session, user, uuid.uuid4(), description="Hacked")
        assert exc.value.status_code == 404

    async def test_invalid_visibility_raises(self):
        from app.services import skill as skill_svc

        user = _make_user()
        skill = _make_skill(user_id=user.id)
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=skill)
        session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc:
            await skill_svc.update_skill(session, user, skill.id, visibility="secret")
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# delete_skill
# ---------------------------------------------------------------------------

class TestDeleteSkill:
    async def test_owner_can_delete(self):
        from app.services import skill as skill_svc

        user = _make_user()
        skill = _make_skill(user_id=user.id)
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=skill)
        session.execute = AsyncMock(return_value=mock_result)

        with patch("app.services.skill.audit_svc.log", AsyncMock()) as audit_log:
            await skill_svc.delete_skill(session, user, skill.id)

        assert session.commit.called
        assert audit_log.call_args.kwargs.get("action") == "skill_deleted"

    async def test_non_owner_gets_404(self):
        from app.services import skill as skill_svc

        user = _make_user()
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc:
            await skill_svc.delete_skill(session, user, uuid.uuid4())
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Agent-pin helpers
# ---------------------------------------------------------------------------

class TestAgentPinHelpers:
    async def test_attach_skill_inserts_when_agent_and_skill_accessible(self):
        from app.services import skill as skill_svc

        user = _make_user()
        agent_id = uuid.uuid4()
        skill = _make_skill(user_id=user.id)
        session = _make_session()

        agent_found = MagicMock()
        agent_found.scalar_one_or_none = MagicMock(return_value=MagicMock())
        no_existing_pin = MagicMock()
        no_existing_pin.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(side_effect=[agent_found, no_existing_pin])

        with patch("app.services.skill.get_skill", AsyncMock(return_value=skill)):
            await skill_svc.attach_skill(session, user, agent_id, skill.id)

        assert session.add.called
        assert session.commit.called

    async def test_attach_skill_agent_not_found_raises_404(self):
        from app.services import skill as skill_svc

        user = _make_user()
        session = _make_session()
        agent_missing = MagicMock()
        agent_missing.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=agent_missing)

        with pytest.raises(HTTPException) as exc:
            await skill_svc.attach_skill(session, user, uuid.uuid4(), uuid.uuid4())
        assert exc.value.status_code == 404

    async def test_get_agent_skill_ids_returns_pinned_ids(self):
        from app.services import skill as skill_svc

        agent_id = uuid.uuid4()
        skill_id = uuid.uuid4()
        session = _make_session()
        rows_result = MagicMock()
        rows_result.all = MagicMock(return_value=[(skill_id,)])
        session.execute = AsyncMock(return_value=rows_result)

        result = await skill_svc.get_agent_skill_ids(session, agent_id)
        assert result == [skill_id]


# ---------------------------------------------------------------------------
# build_skill_system_block
# ---------------------------------------------------------------------------

class TestBuildSkillSystemBlock:
    def test_formats_single_skill(self):
        skill = _make_skill(uuid.uuid4(), name="morning", instructions="Render the brief.")
        block = build_skill_system_block([skill])
        assert block == "# Skill: morning\nRender the brief."

    def test_joins_multiple_skills_with_blank_line(self):
        s1 = _make_skill(uuid.uuid4(), name="a", instructions="Do A.")
        s2 = _make_skill(uuid.uuid4(), name="b", instructions="Do B.")
        block = build_skill_system_block([s1, s2])
        assert block == "# Skill: a\nDo A.\n\n# Skill: b\nDo B."

    def test_empty_list_returns_empty_string(self):
        assert build_skill_system_block([]) == ""

    def test_skips_skills_with_no_instructions(self):
        s1 = _make_skill(uuid.uuid4(), name="a", instructions="")
        s1.instructions = None
        s2 = _make_skill(uuid.uuid4(), name="b", instructions="Do B.")
        block = build_skill_system_block([s1, s2])
        assert block == "# Skill: b\nDo B."


# ---------------------------------------------------------------------------
# draft_skill — "Create with AI"
# ---------------------------------------------------------------------------

def _fake_client(reply_text: str) -> MagicMock:
    from app.llm.base import ChatChunk

    async def _stream(messages, **_opts):
        yield ChatChunk(content=reply_text, prompt_tokens=1, completion_tokens=1)

    client = MagicMock()
    client.stream_chat = _stream
    return client


class TestDraftSkill:
    async def test_valid_json_reply_marks_done_with_normalized_draft(self):
        from app.services import skill as skill_svc

        reply = (
            '{"name": "Weekly-Status-Report", '
            '"description": "Generate weekly status reports. Use when asked for updates.", '
            '"instructions": "Summarize wins, blockers, next steps."}'
        )
        router = MagicMock()
        router.get.return_value = _fake_client(reply)
        with patch("app.llm.router.get_router", return_value=router):
            result = await skill_svc.draft_skill(
                [{"role": "user", "content": "I want a weekly report skill"}]
            )

        assert result["done"] is True
        assert result["message"] is None
        assert result["draft"]["name"] == "weekly-status-report"
        assert result["draft"]["description"].startswith("Generate weekly status reports")
        assert result["draft"]["instructions"] == "Summarize wins, blockers, next steps."

    async def test_plain_text_reply_treated_as_clarifying_question(self):
        from app.services import skill as skill_svc

        reply = "What should trigger this skill?"
        router = MagicMock()
        router.get.return_value = _fake_client(reply)
        with patch("app.llm.router.get_router", return_value=router):
            result = await skill_svc.draft_skill([{"role": "user", "content": "help me"}])

        assert result["done"] is False
        assert result["message"] == reply
        assert result["draft"] is None

    async def test_json_wrapped_in_prose_still_parses(self):
        from app.services import skill as skill_svc

        reply = (
            'Sure, here it is: {"name": "morning", "description": "Morning brief. '
            'Use when asked.", "instructions": "Render a brief."} hope that helps!'
        )
        router = MagicMock()
        router.get.return_value = _fake_client(reply)
        with patch("app.llm.router.get_router", return_value=router):
            result = await skill_svc.draft_skill([{"role": "user", "content": "morning brief"}])

        assert result["done"] is True
        assert result["draft"]["name"] == "morning"

    async def test_incomplete_json_asks_to_continue_not_raw_json(self):
        from app.services import skill as skill_svc

        reply = '{"name": "morning", "description": "Morning brief"}'  # missing instructions
        router = MagicMock()
        router.get.return_value = _fake_client(reply)
        with patch("app.llm.router.get_router", return_value=router):
            result = await skill_svc.draft_skill([{"role": "user", "content": "morning brief"}])

        assert result["done"] is False
        assert result["draft"] is None
        assert "{" not in result["message"]  # never leaks raw JSON as a chat bubble

    async def test_non_slug_name_is_normalized(self):
        from app.services import skill as skill_svc

        reply = (
            '{"name": "Weekly Status Report!!", "description": "Use when asked.", '
            '"instructions": "Do the thing."}'
        )
        router = MagicMock()
        router.get.return_value = _fake_client(reply)
        with patch("app.llm.router.get_router", return_value=router):
            result = await skill_svc.draft_skill([{"role": "user", "content": "x"}])

        assert result["done"] is True
        assert result["draft"]["name"] == "weekly-status-report"

    async def test_local_model_exception_falls_back_gracefully(self):
        from app.services import skill as skill_svc

        router = MagicMock()
        router.get.side_effect = KeyError("no client registered")
        with patch("app.llm.router.get_router", return_value=router):
            result = await skill_svc.draft_skill([{"role": "user", "content": "help"}])

        assert result["done"] is False
        assert result["draft"] is None
        assert result["message"]  # a friendly fallback string, never an exception leaking through

    async def test_malformed_json_falls_back_to_reply_text(self):
        from app.services import skill as skill_svc

        reply = "{not valid json at all"
        router = MagicMock()
        router.get.return_value = _fake_client(reply)
        with patch("app.llm.router.get_router", return_value=router):
            result = await skill_svc.draft_skill([{"role": "user", "content": "x"}])

        assert result["done"] is False
        assert result["draft"] is None
