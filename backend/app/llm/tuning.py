"""
app/llm/tuning.py

Typed per-turn generation tuning ("response mode" + "reasoning level") — the
single seam through which the chat pipeline (app/agents/orchestrator.py) hands
per-turn knobs down into a vendor adapter (app/llm/<provider>.py).

Lives in app/llm/, not app/services/, so the dependency direction stays
services -> llm, never the reverse, and vendor adapters can import it without
a circular import. Stdlib-only (enum, dataclasses) — app/routers/automations.py
lazily imports the orchestrator to keep openai/google-genai out of unit-test
collection, and this module must not break that.

Per PLAN.md §7.2, provider knowledge stays inside app/llm/<provider>.py — the
orchestrator and this module never branch on which vendor is in play. See
G-A1/G-A2 in docs/gap-closure.md.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class ResponseMode(str, Enum):
    """User-facing speed/quality knob (G-A1)."""

    INSTANT = "instant"
    THINKING = "thinking"
    PRO = "pro"


class ReasoningLevel(str, Enum):
    """Depth-of-reasoning override, distinct from mode (G-A2)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAX = "max"


# mode is primary; reasoning_level (if set) overrides mode's default depth.
# INSTANT never reasons, regardless of what reasoning_level carries — see
# GenerationTuning.effective_reasoning().
_MODE_DEFAULT_REASONING: dict[ResponseMode, ReasoningLevel | None] = {
    ResponseMode.INSTANT: None,
    ResponseMode.THINKING: ReasoningLevel.MEDIUM,
    ResponseMode.PRO: ReasoningLevel.HIGH,
}


@dataclass(frozen=True)
class GenerationTuning:
    """Per-turn tuning resolved once in chat_policy.prepare_chat and carried
    down through ChatState to app.agents.orchestrator.call_llm, which passes
    it untouched to LLMClient.stream_chat(tuning=...). Only the adapters in
    app/llm/<provider>.py read mode/reasoning_level/temperature and translate
    them into vendor-specific kwargs — the orchestrator never branches on
    provider (§7.2).
    """

    mode: ResponseMode = ResponseMode.INSTANT
    reasoning_level: ReasoningLevel | None = None
    temperature: float | None = None
    # Set by without_reasoning() when emit_start finds the resolved model
    # can't honor reasoning (LLMClient.supports_reasoning is False) — distinct
    # from reasoning_level being unset, which means "use the mode default".
    reasoning_disabled: bool = False

    def effective_reasoning(self) -> ReasoningLevel | None:
        """The reasoning level that should actually be requested from a
        vendor. None means "don't ask for extended reasoning at all"."""
        if self.reasoning_disabled or self.mode is ResponseMode.INSTANT:
            return None
        return self.reasoning_level or _MODE_DEFAULT_REASONING[self.mode]

    def without_reasoning(self) -> "GenerationTuning":
        """Return a copy with reasoning forced off. Used when the resolved
        model can't honor it, so the turn proceeds instead of the vendor
        silently ignoring (or 400ing on) an unsupported parameter."""
        return replace(self, reasoning_disabled=True)
