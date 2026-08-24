"""
app/services/prompt_assistant.py

G-A4 Prompt Assistant: rewrites a user's lazy draft into a better-structured
prompt before it's ever sent as a chat turn.

Modeled line-for-line on app/services/skill_selector.py — only the local
model is used (DEFAULT_MODEL_CODE), which is always policy-allowed and free,
so this adds no external call, no quota, and no PolicyEngine.decide() call
(§7.2 untouched; the eventual "Use this" send still goes through the normal
POST /chat -> prepare_chat -> PolicyEngine.decide() path).
"""
from __future__ import annotations

MAX_DRAFT_CHARS = 4000

_SYSTEM_PROMPT = (
    "You rewrite a user's draft prompt so an AI assistant can answer it "
    "better. Preserve the user's intent, language, and any specific names, "
    "numbers, or constraints exactly. Reply in the same language as the "
    "draft. Add missing structure: the goal, the audience, the desired "
    "output format, and the level of detail. Do not answer the question. "
    "Do not add facts the user did not supply. Do not add a preamble. "
    "Reply with ONLY the rewritten prompt."
)


def _extract_rewrite(raw: str) -> str | None:
    """Defensive extraction: the model may wrap the rewrite in ``` fences or
    a short preamble. Strip fences, then take the longest non-empty block.
    """
    text = raw.strip()
    if not text:
        return None

    if "```" in text:
        parts = [p.strip() for p in text.split("```") if p.strip()]
        if parts:
            text = max(parts, key=len)

    text = text.strip().strip("`").strip()
    return text or None


async def rewrite_prompt(draft: str, agent_instructions: str | None = None) -> str | None:
    """Rewrite `draft` via the local model. Returns None on any failure —
    never blocks the composer.
    """
    from app.llm.base import ChatMessage
    from app.llm.router import DEFAULT_MODEL_CODE, get_router

    truncated = draft[:MAX_DRAFT_CHARS]
    user_content = truncated
    if agent_instructions:
        user_content = f"Assistant's domain: {agent_instructions}\n\nDraft: {truncated}"

    try:
        client = get_router().get(DEFAULT_MODEL_CODE)
        raw = ""
        async for chunk in client.stream_chat(
            [
                ChatMessage(role="system", content=_SYSTEM_PROMPT),
                ChatMessage(role="user", content=user_content),
            ],
            options={"num_predict": 400},
            keep_alive="5m",
        ):
            if chunk.content:
                raw += chunk.content
                if len(raw) > MAX_DRAFT_CHARS:  # safety cap against a runaway reply
                    break

        return _extract_rewrite(raw)
    except Exception:
        return None
