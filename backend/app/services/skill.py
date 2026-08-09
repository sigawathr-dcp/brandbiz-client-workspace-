"""
app/services/skill.py

CRUD + access helpers for Skills, plus SKILL.md frontmatter parsing and
Agent-pin helpers. Mirrors app/services/agent.py.

All write operations require ownership. Read operations grant access to own
skills plus any with visibility="public".
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.skill import VALID_SKILL_VISIBILITIES, AgentSkill, Skill
from app.models.user import User
from app.services import audit as audit_svc
from app.services.workspace import is_client_seat, workspace_visibility_filter_by_user_id

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def validate_slug(name: str) -> str:
    """Validate a skill name is a kebab-case slug; raise 400 otherwise."""
    if not name or not _SLUG_RE.match(name):
        raise HTTPException(
            400,
            "Skill name must be a kebab-case slug (lowercase letters, digits, "
            "hyphens; must start with a letter or digit).",
        )
    if len(name) > 64:
        raise HTTPException(400, "Skill name must be 64 characters or fewer.")
    return name


def parse_skill_markdown(raw: str) -> tuple[str | None, str | None, str]:
    """Parse a SKILL.md document: YAML-ish frontmatter between `---` fences,
    followed by the instructions body.

    Only simple scalar `key: value` frontmatter lines are supported (no
    nested structures) — sufficient for `name` and `description`, the only
    fields this gateway reads. Falls back to (None, None, raw) if there is
    no well-formed frontmatter block.

    Returns (name, description, body).
    """
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, None, raw.strip()

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return None, None, raw.strip()

    frontmatter_lines = lines[1:end_idx]
    body = "\n".join(lines[end_idx + 1:]).strip()

    name: str | None = None
    description: str | None = None
    for line in frontmatter_lines:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip().strip('"').strip("'")
        if key == "name":
            name = value or None
        elif key == "description":
            description = value or None

    return name, description, body


def _accessible_filter(user_id: uuid.UUID):
    """SQLAlchemy WHERE clause: own skills OR public skills in the same
    tenant (D21/D22 — a client seat never sees an internal-shared public
    skill, or another workspace's; internal users are unaffected)."""
    return or_(
        Skill.user_id == user_id,
        and_(
            Skill.visibility == "public",
            workspace_visibility_filter_by_user_id(user_id, Skill),
        ),
    )


async def get_skill(
    session: AsyncSession,
    skill_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Skill | None:
    result = await session.execute(
        select(Skill).where(Skill.id == skill_id, _accessible_filter(user_id))
    )
    return result.scalar_one_or_none()


async def list_skills(
    session: AsyncSession,
    user_id: uuid.UUID,
    scope: str = "all",
    q: str | None = None,
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Skill], int]:
    """List skills with optional filtering.

    scope="all"  → public skills + own skills
    scope="mine" → only own skills
    """
    if scope == "mine":
        base = Skill.user_id == user_id
    else:
        base = _accessible_filter(user_id)

    filters: list[Any] = [base]
    if q:
        filters.append(Skill.name.ilike(f"%{q}%"))
    if category:
        filters.append(Skill.category == category)

    stmt = select(Skill).where(*filters).order_by(Skill.updated_at.desc())
    total_result = await session.execute(select(Skill).where(*filters))
    total = len(total_result.scalars().all())

    paged = await session.execute(stmt.limit(limit).offset(offset))
    return paged.scalars().all(), total  # type: ignore[return-value]


async def get_enabled_skills(session: AsyncSession, user_id: uuid.UUID) -> list[Skill]:
    """Candidate list for the auto-match selector: enabled + accessible."""
    result = await session.execute(
        select(Skill).where(_accessible_filter(user_id), Skill.enabled.is_(True))
    )
    return list(result.scalars().all())


async def get_skill_by_name(
    session: AsyncSession, user_id: uuid.UUID, name: str
) -> Skill | None:
    result = await session.execute(
        select(Skill).where(_accessible_filter(user_id), Skill.name == name)
    )
    return result.scalar_one_or_none()


async def _check_unique_name(
    session: AsyncSession, user_id: uuid.UUID, name: str, exclude_id: uuid.UUID | None = None
) -> None:
    filters = [Skill.user_id == user_id, Skill.name == name]
    if exclude_id is not None:
        filters.append(Skill.id != exclude_id)
    existing = await session.execute(select(Skill).where(*filters))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(400, f"You already have a skill named '{name}'")


async def create_skill(
    session: AsyncSession,
    user: User,
    name: str,
    description: str | None = None,
    instructions: str | None = None,
    source_markdown: str | None = None,
    enabled: bool = True,
    visibility: str = "personal",
    category: str | None = None,
) -> Skill:
    name = validate_slug(name)
    if visibility not in VALID_SKILL_VISIBILITIES:
        raise HTTPException(400, f"visibility must be one of {VALID_SKILL_VISIBILITIES}")
    # D23: every booth attendee shares one workspace, so a client seat's
    # "public" skill would be visible to every other attendee, not just to
    # Brandbiz staff. Coerce rather than 422 — routers/skills.py's create
    # form defaults visibility to "personal" already, but callers (and the
    # "create with AI" flow) may still pass "public" explicitly.
    if is_client_seat(user):
        visibility = "personal"
    await _check_unique_name(session, user.id, name)

    skill = Skill(
        user_id=user.id,
        name=name,
        description=description,
        instructions=instructions,
        source_markdown=source_markdown,
        enabled=enabled,
        visibility=visibility,
        category=category,
        # NULL for internal staff, unchanged from pre-D23 behavior.
        workspace_id=user.workspace_id,
    )
    session.add(skill)
    await session.commit()
    await session.refresh(skill)

    await audit_svc.log(
        action="skill_created",
        user_id=user.id,
        details={"skill_id": str(skill.id), "name": name},
    )
    return skill


async def create_skill_from_markdown(
    session: AsyncSession,
    user: User,
    raw_markdown: str,
    visibility: str = "personal",
    category: str | None = None,
) -> Skill:
    """Parse an uploaded SKILL.md and create a skill from it.

    Frontmatter `name` is required (it becomes the slug); falls back to a
    slugified first line of the body if absent.
    """
    name, description, body = parse_skill_markdown(raw_markdown)
    if not name:
        raise HTTPException(
            400, "SKILL.md must declare a `name` in its frontmatter."
        )
    return await create_skill(
        session=session,
        user=user,
        name=name,
        description=description,
        instructions=body,
        source_markdown=raw_markdown,
        enabled=True,
        visibility=visibility,
        category=category,
    )


async def update_skill(
    session: AsyncSession,
    user: User,
    skill_id: uuid.UUID,
    **kwargs: Any,
) -> Skill:
    result = await session.execute(
        select(Skill).where(Skill.id == skill_id, Skill.user_id == user.id)
    )
    skill = result.scalar_one_or_none()
    if skill is None:
        raise HTTPException(404, "Skill not found")

    allowed = {
        "name", "description", "instructions", "source_markdown",
        "enabled", "visibility", "category",
    }
    for key, value in kwargs.items():
        if key not in allowed:
            continue
        if key == "name":
            value = validate_slug(value)
            if value != skill.name:
                await _check_unique_name(session, user.id, value, exclude_id=skill_id)
        if key == "visibility" and value not in VALID_SKILL_VISIBILITIES:
            raise HTTPException(400, f"visibility must be one of {VALID_SKILL_VISIBILITIES}")
        setattr(skill, key, value)

    await session.commit()
    await session.refresh(skill)

    await audit_svc.log(
        action="skill_updated",
        user_id=user.id,
        details={"skill_id": str(skill_id), "fields": list(kwargs.keys())},
    )
    return skill


async def delete_skill(
    session: AsyncSession,
    user: User,
    skill_id: uuid.UUID,
) -> None:
    result = await session.execute(
        select(Skill).where(Skill.id == skill_id, Skill.user_id == user.id)
    )
    skill = result.scalar_one_or_none()
    if skill is None:
        raise HTTPException(404, "Skill not found")

    await session.execute(delete(Skill).where(Skill.id == skill_id))
    await session.commit()

    await audit_svc.log(
        action="skill_deleted",
        user_id=user.id,
        details={"skill_id": str(skill_id)},
    )


# ---------------------------------------------------------------------------
# Agent-pin helpers (mirrors agent.py's knowledge-file attach/detach)
# ---------------------------------------------------------------------------

async def attach_skill(
    session: AsyncSession,
    user: User,
    agent_id: uuid.UUID,
    skill_id: uuid.UUID,
) -> None:
    """Pin a skill to an agent: always injected when that agent runs."""
    agent = await session.execute(
        select(Agent).where(Agent.id == agent_id, Agent.user_id == user.id)
    )
    if agent.scalar_one_or_none() is None:
        raise HTTPException(404, "Agent not found")

    skill = await get_skill(session, skill_id, user.id)
    if skill is None:
        raise HTTPException(404, "Skill not found or not accessible")

    existing = await session.execute(
        select(AgentSkill).where(
            AgentSkill.agent_id == agent_id,
            AgentSkill.skill_id == skill_id,
        )
    )
    if existing.scalar_one_or_none() is None:
        session.add(AgentSkill(agent_id=agent_id, skill_id=skill_id))
        await session.commit()


async def detach_skill(
    session: AsyncSession,
    user: User,
    agent_id: uuid.UUID,
    skill_id: uuid.UUID,
) -> None:
    agent = await session.execute(
        select(Agent).where(Agent.id == agent_id, Agent.user_id == user.id)
    )
    if agent.scalar_one_or_none() is None:
        raise HTTPException(404, "Agent not found")

    await session.execute(
        delete(AgentSkill).where(
            AgentSkill.agent_id == agent_id,
            AgentSkill.skill_id == skill_id,
        )
    )
    await session.commit()


async def get_agent_skill_ids(
    session: AsyncSession,
    agent_id: uuid.UUID,
) -> list[uuid.UUID]:
    """Return skill IDs pinned to this agent."""
    result = await session.execute(
        select(AgentSkill.skill_id).where(AgentSkill.agent_id == agent_id)
    )
    return [row[0] for row in result.all()]


async def get_pinned_skills(
    session: AsyncSession,
    agent_id: uuid.UUID,
) -> list[Skill]:
    """Return the full Skill rows pinned to this agent (for UI hydration)."""
    result = await session.execute(
        select(Skill).join(AgentSkill, AgentSkill.skill_id == Skill.id).where(
            AgentSkill.agent_id == agent_id
        )
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# System-prompt composition
# ---------------------------------------------------------------------------

def build_skill_system_block(skills: list[Skill]) -> str:
    """Format selected skills into a labelled system-prompt section."""
    blocks = []
    for skill in skills:
        if not skill.instructions:
            continue
        blocks.append(f"# Skill: {skill.name}\n{skill.instructions}")
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# "Create with AI" — conversational skill authoring
# ---------------------------------------------------------------------------
#
# Local model only, same as skill_selector.match_skills_by_description() — a
# background utility call to the local model skips PolicyEngine.decide() the
# same way (policy_engine.py's own first rule: local model is always
# allowed). Unlike that background heuristic, this is a foreground drafting
# helper, so on any failure we surface a friendly message rather than
# silently returning nothing.

_DRAFT_FALLBACK_MESSAGE = (
    "Something went wrong on my end — could you rephrase what you'd like this skill to do?"
)

_DRAFT_INCOMPLETE_MESSAGE = (
    "I need a bit more detail — could you tell me more about what this skill should do?"
)

_DRAFT_SYSTEM = (
    'You are helping a user author a "Skill" for an internal company AI gateway — a reusable '
    "instruction bundle with a name, a description (used to auto-trigger it), and instructions "
    "(the system-prompt body applied when it fires).\n\n"
    "Ask ONE clarifying question at a time until you understand: what the skill should do, when it "
    "should trigger, and any specific format or tone it should use. Keep questions short.\n\n"
    "Once you have enough information, respond with ONLY a JSON object (no other text) with exactly "
    "these keys:\n"
    '  "name": a kebab-case slug, lowercase letters/digits/hyphens only, at most 64 characters\n'
    '  "description": trigger text — what it does, then "Use when...", at most 300 characters\n'
    '  "instructions": the instructions the assistant should follow when this skill fires\n\n'
    "Do not wrap the JSON in a code fence. If you still need more information, respond with plain "
    "text only (your next question) — never a partial JSON object."
)


def _slugify_fallback(text: str) -> str:
    """Best-effort kebab-case slug from arbitrary text, for a name that fails strict validation."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:64] or "untitled-skill"


def _extract_json_object(text: str) -> dict | None:
    """Defensively pull a JSON object out of a reply that may include prose or code fences."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        parsed = json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


async def draft_skill(messages: list[dict]) -> dict:
    """Conversational skill authoring: ask the local model to keep clarifying until it can draft
    a skill, then extract {name, description, instructions} from its reply.

    `messages` is the modal's full transcript: [{"role": "user"|"assistant", "content": str}, ...].
    Returns {"done": bool, "message": str | None, "draft": dict | None}.
    """
    from app.llm.base import ChatMessage
    from app.llm.router import LOCAL_MODEL_CODE, get_router

    try:
        client = get_router().get(LOCAL_MODEL_CODE)
        chat_messages = [ChatMessage(role="system", content=_DRAFT_SYSTEM)]
        for m in messages:
            role = m.get("role")
            content = m.get("content", "")
            if role in ("user", "assistant") and content:
                chat_messages.append(ChatMessage(role=role, content=content))

        reply = ""
        async for chunk in client.stream_chat(
            chat_messages,
            options={"num_predict": 400},
            keep_alive="5m",
        ):
            if chunk.content:
                reply += chunk.content
                if len(reply) > 4000:  # safety cap: bail if the model is unexpectedly verbose
                    break

        reply = reply.strip()
        parsed = _extract_json_object(reply)
        if parsed:
            name = str(parsed.get("name", "")).strip().lower()
            description = str(parsed.get("description", "")).strip()
            instructions = str(parsed.get("instructions", "")).strip()
            if name and description and instructions:
                if not _SLUG_RE.match(name):
                    name = _slugify_fallback(name)
                return {
                    "done": True,
                    "message": None,
                    "draft": {
                        "name": name[:64],
                        "description": description[:1000],
                        "instructions": instructions[:8000],
                    },
                }
            # Parsed JSON but incomplete — ask to continue rather than showing raw JSON.
            return {"done": False, "message": _DRAFT_INCOMPLETE_MESSAGE, "draft": None}

        # No JSON found — treat the reply as the next clarifying question.
        return {"done": False, "message": reply or _DRAFT_FALLBACK_MESSAGE, "draft": None}

    except Exception:
        return {"done": False, "message": _DRAFT_FALLBACK_MESSAGE, "draft": None}
