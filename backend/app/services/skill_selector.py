"""
app/services/skill_selector.py

Skill selection for a chat turn: merges three sources of "this skill should
apply now" —
  - forced: the user typed a leading /skill-name in their message
  - pinned: the active Agent has this skill pinned (always-on)
  - matched: the local LLM judged the skill's description relevant to the
    message (best-effort; same graceful-fallback shape as app/tools/intent.py)

Only the local model is used for matching (DEFAULT_MODEL_CODE) — it is always
policy-allowed and free, so this adds no external call, quota, or policy
concern (§7.2 untouched; the main chat call still goes through
PolicyEngine.decide() separately).
"""
from __future__ import annotations

import json
import re
import uuid

from app.models.skill import Skill

MAX_SKILLS = 5

_SLUG_TOKEN_RE = re.compile(r"^/([a-z0-9][a-z0-9-]*)\b\s*")

_SELECT_SYSTEM = (
    "You are a skill router. Given a user message and a list of available "
    "skills (name: description), reply with ONLY a JSON array of the names "
    "of skills that are clearly relevant to the message. If none apply, "
    "reply with an empty array []. Do not explain."
)


def extract_forced_slug(user_content: str) -> tuple[str | None, str]:
    """Detect a leading /slug token in the message.

    Returns (slug, content_with_token_stripped). If no slash-command is
    present, returns (None, user_content) unchanged.
    """
    stripped = user_content.lstrip()
    match = _SLUG_TOKEN_RE.match(stripped)
    if not match:
        return None, user_content
    return match.group(1), _SLUG_TOKEN_RE.sub("", stripped, count=1)


async def match_skills_by_description(
    user_content: str, candidates: list[Skill], max_n: int = MAX_SKILLS
) -> list[Skill]:
    """Ask the local LLM which candidate skills' descriptions match the
    message. Returns [] on any failure — never blocks the chat turn.
    """
    if not candidates or max_n <= 0:
        return []

    from app.llm.base import ChatMessage
    from app.llm.router import DEFAULT_MODEL_CODE, get_router

    listing = "\n".join(
        f"- {s.name}: {s.description or '(no description)'}" for s in candidates
    )
    prompt = f"Skills:\n{listing}\n\nMessage: {user_content}"

    try:
        client = get_router().get(DEFAULT_MODEL_CODE)
        raw = ""
        async for chunk in client.stream_chat(
            [
                ChatMessage(role="system", content=_SELECT_SYSTEM),
                ChatMessage(role="user", content=prompt),
            ],
            options={"num_predict": 200},
            keep_alive="5m",
        ):
            if chunk.content:
                raw += chunk.content
                if len(raw) > 2000:  # safety cap: bail if model is unexpectedly verbose
                    break

        raw = raw.strip()
        # Defensive extraction: the model may wrap the array in prose/fences.
        start, end = raw.find("["), raw.rfind("]")
        if start == -1 or end == -1 or end < start:
            return []
        names = json.loads(raw[start:end + 1])
        if not isinstance(names, list):
            return []

        by_name = {s.name: s for s in candidates}
        selected = [by_name[n] for n in names if isinstance(n, str) and n in by_name]
        return selected[:max_n]
    except Exception:
        return []


async def select_skills(
    user_content: str,
    candidates: list[Skill],
    forced_slugs: list[str],
    pinned_ids: list[uuid.UUID],
    max_n: int = MAX_SKILLS,
) -> list[Skill]:
    """Merge forced (/slug) + pinned (agent) + auto-matched skills.

    forced_slugs and pinned_ids are always kept regardless of max_n;
    auto-match fills the remaining slots up to max_n total.
    """
    by_name = {s.name: s for s in candidates}
    by_id = {s.id: s for s in candidates}

    selected: dict[uuid.UUID, Skill] = {}
    for slug in forced_slugs:
        skill = by_name.get(slug)
        if skill is not None:
            selected[skill.id] = skill
    for skill_id in pinned_ids:
        skill = by_id.get(skill_id)
        if skill is not None:
            selected[skill.id] = skill

    remaining = [s for s in candidates if s.id not in selected]
    remaining_slots = max(0, max_n - len(selected))
    if remaining and remaining_slots > 0:
        matched = await match_skills_by_description(
            user_content, remaining, max_n=remaining_slots
        )
        for skill in matched:
            selected[skill.id] = skill

    return list(selected.values())
