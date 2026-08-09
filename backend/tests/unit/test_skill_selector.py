"""
Unit tests for app/services/skill_selector.py.

Covers:
- extract_forced_slug: detects a leading /slug token, strips it, no-ops otherwise
- match_skills_by_description: parses a JSON array reply from the local model,
  defensively handles malformed/wrapped output, falls back to [] on any failure
  (same graceful-degradation shape as app/tools/intent.classify_intent)
- select_skills: forced + pinned always kept; auto-match fills remaining slots
  up to max_n; auto-match is skipped entirely when no candidates remain
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.skill_selector import (
    extract_forced_slug,
    match_skills_by_description,
    select_skills,
)


def _make_skill(name: str, description: str = "desc") -> MagicMock:
    skill = MagicMock()
    skill.id = uuid.uuid4()
    skill.name = name
    skill.description = description
    return skill


def _fake_client(reply_text: str) -> MagicMock:
    from app.llm.base import ChatChunk

    async def _stream(messages, **_opts):
        yield ChatChunk(content=reply_text, prompt_tokens=1, completion_tokens=1)

    client = MagicMock()
    client.stream_chat = _stream
    return client


# ---------------------------------------------------------------------------
# extract_forced_slug
# ---------------------------------------------------------------------------

class TestExtractForcedSlug:
    def test_detects_leading_slash_command(self):
        slug, rest = extract_forced_slug("/weekly-report give me the numbers")
        assert slug == "weekly-report"
        assert rest == "give me the numbers"

    def test_no_slash_returns_none(self):
        slug, rest = extract_forced_slug("just a normal message")
        assert slug is None
        assert rest == "just a normal message"

    def test_slash_mid_sentence_not_matched(self):
        slug, rest = extract_forced_slug("check the a/b test results")
        assert slug is None

    def test_bare_slug_with_no_trailing_text(self):
        slug, rest = extract_forced_slug("/morning")
        assert slug == "morning"
        assert rest == ""

    def test_leading_whitespace_tolerated(self):
        slug, rest = extract_forced_slug("   /morning please")
        assert slug == "morning"
        assert rest == "please"


# ---------------------------------------------------------------------------
# match_skills_by_description
# ---------------------------------------------------------------------------

class TestMatchSkillsByDescription:
    async def test_empty_candidates_returns_empty_without_calling_llm(self):
        result = await match_skills_by_description("hello", [])
        assert result == []

    async def test_zero_max_n_returns_empty_without_calling_llm(self):
        skills = [_make_skill("a")]
        result = await match_skills_by_description("hello", skills, max_n=0)
        assert result == []

    async def test_parses_json_array_reply(self):
        skills = [_make_skill("weekly-report"), _make_skill("morning")]
        router = MagicMock()
        router.get.return_value = _fake_client('["weekly-report"]')
        with patch("app.llm.router.get_router", return_value=router):
            result = await match_skills_by_description("give me the report", skills)
        assert [s.name for s in result] == ["weekly-report"]

    async def test_reply_wrapped_in_prose_still_parses(self):
        skills = [_make_skill("morning")]
        router = MagicMock()
        router.get.return_value = _fake_client('Sure, here you go: ["morning"] thanks!')
        with patch("app.llm.router.get_router", return_value=router):
            result = await match_skills_by_description("what's my day look like", skills)
        assert [s.name for s in result] == ["morning"]

    async def test_empty_array_reply_returns_empty(self):
        skills = [_make_skill("morning")]
        router = MagicMock()
        router.get.return_value = _fake_client("[]")
        with patch("app.llm.router.get_router", return_value=router):
            result = await match_skills_by_description("unrelated message", skills)
        assert result == []

    async def test_malformed_reply_falls_back_to_empty(self):
        skills = [_make_skill("morning")]
        router = MagicMock()
        router.get.return_value = _fake_client("not json at all")
        with patch("app.llm.router.get_router", return_value=router):
            result = await match_skills_by_description("anything", skills)
        assert result == []

    async def test_llm_exception_falls_back_to_empty(self):
        skills = [_make_skill("morning")]
        router = MagicMock()
        router.get.side_effect = KeyError("no client registered")
        with patch("app.llm.router.get_router", return_value=router):
            result = await match_skills_by_description("anything", skills)
        assert result == []

    async def test_unknown_name_in_reply_is_ignored(self):
        skills = [_make_skill("morning")]
        router = MagicMock()
        router.get.return_value = _fake_client('["nonexistent-skill", "morning"]')
        with patch("app.llm.router.get_router", return_value=router):
            result = await match_skills_by_description("anything", skills)
        assert [s.name for s in result] == ["morning"]

    async def test_respects_max_n_cap(self):
        skills = [_make_skill(f"skill-{i}") for i in range(5)]
        names = [s.name for s in skills]
        router = MagicMock()
        router.get.return_value = _fake_client(str(names).replace("'", '"'))
        with patch("app.llm.router.get_router", return_value=router):
            result = await match_skills_by_description("anything", skills, max_n=2)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# select_skills
# ---------------------------------------------------------------------------

class TestSelectSkills:
    async def test_forced_always_included(self):
        forced = _make_skill("deploy")
        candidates = [forced]
        with patch(
            "app.services.skill_selector.match_skills_by_description",
            new_callable=AsyncMock, return_value=[],
        ):
            result = await select_skills("go", candidates, ["deploy"], [])
        assert result == [forced]

    async def test_pinned_always_included(self):
        pinned = _make_skill("persona")
        candidates = [pinned]
        with patch(
            "app.services.skill_selector.match_skills_by_description",
            new_callable=AsyncMock, return_value=[],
        ):
            result = await select_skills("hi", candidates, [], [pinned.id])
        assert result == [pinned]

    async def test_matched_fills_remaining_slots(self):
        forced = _make_skill("deploy")
        matched = _make_skill("morning")
        candidates = [forced, matched]
        with patch(
            "app.services.skill_selector.match_skills_by_description",
            new_callable=AsyncMock, return_value=[matched],
        ) as mock_match:
            result = await select_skills("go /deploy", candidates, ["deploy"], [])
        assert {s.name for s in result} == {"deploy", "morning"}
        mock_match.assert_awaited_once()
        # the matcher is only shown the remaining (non-forced) candidates
        assert mock_match.await_args.args[1] == [matched]

    async def test_auto_match_skipped_when_no_remaining_candidates(self):
        forced = _make_skill("deploy")
        candidates = [forced]
        with patch(
            "app.services.skill_selector.match_skills_by_description",
            new_callable=AsyncMock,
        ) as mock_match:
            await select_skills("go", candidates, ["deploy"], [])
        mock_match.assert_not_called()

    async def test_dedupes_forced_and_pinned_overlap(self):
        skill = _make_skill("morning")
        with patch(
            "app.services.skill_selector.match_skills_by_description",
            new_callable=AsyncMock, return_value=[],
        ):
            result = await select_skills("hi", [skill], ["morning"], [skill.id])
        assert result == [skill]

    async def test_forced_and_pinned_kept_beyond_max_n(self):
        forced = [_make_skill(f"forced-{i}") for i in range(5)]
        with patch(
            "app.services.skill_selector.match_skills_by_description",
            new_callable=AsyncMock, return_value=[],
        ) as mock_match:
            result = await select_skills(
                "go", forced, [s.name for s in forced], [], max_n=3
            )
        # forced skills are always kept even beyond max_n (max_n only bounds auto-match)
        assert len(result) == 5
        mock_match.assert_not_called()

    async def test_unknown_forced_slug_is_ignored(self):
        candidates = [_make_skill("morning")]
        with patch(
            "app.services.skill_selector.match_skills_by_description",
            new_callable=AsyncMock, return_value=[],
        ):
            result = await select_skills("hi", candidates, ["does-not-exist"], [])
        assert result == []
