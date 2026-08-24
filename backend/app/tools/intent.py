"""
app/tools/intent.py

Intent detection for auto-model routing. Supports English and Thai.

Two-layer approach:
  1. classify_intent(text) — async, asks the local LLM with a strict token cap.
     Falls back to regex (detect_intent_model) on any error so routing is never
     blocked by the model being offline or slow.
  2. detect_intent_model(text) — sync regex fallback, always available.

Priority: coding is checked before research so a message like
"What is the best way to fix this bug?" routes to the coding model,
not the research model.
"""
from __future__ import annotations

import re

RESEARCH_MODEL_CODE = "perplexity-sonar"
CODING_MODEL_CODE = "claude-sonnet-4"

# Matches explicit coding actions (verb + programming noun) and standalone
# programming-specific terms that unambiguously indicate a coding request.
_CODING_RE = re.compile(
    r"(?i)"
    # action verb followed by a programming noun (up to 80 chars apart)
    r"(?:write|implement|create|fix|debug|refactor|build|generate)\b.{0,80}\b"
    r"(?:function|class|script|program|code|bug|error|api|endpoint|module|method|tests?|test\s+cases?)\b"
    r"|\b(?:algorithm|compile|syntax\s+error|unit\s+tests?|test\s+cases?|stack\s+trace|recursion|dockerfile|sql\s+(?:query|schema))\b"
    # Thai: verb + programming noun, or programming noun + verb
    r"|(?:เขียน|แก้ไข|ดีบัก|สร้าง).{0,30}(?:โค้ด|ฟังก์ชัน|คลาส|โปรแกรม|สคริปต์|บัก)"
    r"|(?:โค้ด|บัก|สคริปต์).{0,20}(?:แก้|ดู|ช่วย|เขียน|สร้าง)",
    re.DOTALL,
)

# Matches research/lookup intent: question starters, explicit search verbs,
# and recency-qualified nouns.
_RESEARCH_RE = re.compile(
    r"(?i)"
    # WH-question starters
    r"\b(?:what\s+(?:is|are)|who\s+(?:is|are)|when\s+(?:did|was|is|are)"
    r"|where\s+(?:is|are)|how\s+(?:does|do)|why\s+(?:is|are|does|do))\b"
    r"|\b(?:research|look\s+up|search\s+for|find\s+(?:out|information))\b"
    r"|\b(?:latest|current|recent)\s+(?:news|update|status|trend|development|information)\b"
    # Thai research/lookup terms
    r"|(?:ค้นหา|วิจัย|หาข้อมูล|สืบค้น|ข่าวล่าสุด|ข้อมูลล่าสุด|ข่าวปัจจุบัน)",
    re.DOTALL,
)


def is_coding_request(text: str) -> bool:
    return bool(_CODING_RE.search(text))


def is_research_request(text: str) -> bool:
    return bool(_RESEARCH_RE.search(text))


def detect_intent_model(text: str) -> str | None:
    """Regex-based intent detection. Used as fallback when LLM classifier fails.

    Coding takes priority: a message matching both (e.g. "how do I fix this bug?")
    routes to the coding model, not the research model.
    """
    if is_coding_request(text):
        return CODING_MODEL_CODE
    if is_research_request(text):
        return RESEARCH_MODEL_CODE
    return None


_CLASSIFY_SYSTEM = (
    "You are an intent classifier. Classify the message into one of three categories:\n"
    "- coding: writing, debugging, or explaining code; programming questions\n"
    "- research: looking up facts, news, current events, web search\n"
    "- general: anything else\n"
    "Reply with ONLY one lowercase word: coding, research, or general."
)


async def classify_intent(text: str) -> str | None:
    """Ask the local LLM to classify intent; fall back to regex on any error.

    Uses a 10-token cap so the model outputs a single word and returns quickly.
    Passes keep_alive=5m so the model stays warm for the main chat call that
    follows immediately after classification.
    """
    from app.llm.base import ChatMessage
    from app.llm.router import DEFAULT_MODEL_CODE, get_router

    try:
        client = get_router().get(DEFAULT_MODEL_CODE)
        label = ""
        async for chunk in client.stream_chat(
            [
                ChatMessage(role="system", content=_CLASSIFY_SYSTEM),
                ChatMessage(role="user", content=text),
            ],
            options={"num_predict": 10},
            keep_alive="5m",
        ):
            if chunk.content:
                label += chunk.content
                if len(label) > 30:  # safety cap: bail if model is unexpectedly verbose
                    break

        label = label.strip().lower()
        if "coding" in label:
            return CODING_MODEL_CODE
        if "research" in label:
            return RESEARCH_MODEL_CODE
        return None

    except Exception:
        return detect_intent_model(text)
