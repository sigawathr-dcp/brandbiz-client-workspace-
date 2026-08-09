from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator

from app.llm.tuning import GenerationTuning


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class ChatChunk:
    content: str
    model: str | None = None
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    metadata: dict | None = None


class LLMProviderError(Exception):
    """Raised when an upstream LLM provider returns an error.

    provider_code mirrors the HTTP status the provider returned (e.g. 429, 503).
    None means the status is unknown.
    """

    def __init__(self, message: str, provider_code: int | None = None) -> None:
        super().__init__(message)
        self.provider_code = provider_code


class LLMClient(ABC):
    @abstractmethod
    def stream_chat(
        self,
        messages: list[ChatMessage],
        *,
        tuning: GenerationTuning | None = None,
        **opts,
    ) -> AsyncIterator[ChatChunk]:
        """Stream chat completions as ChatChunk deltas.

        `tuning` is the typed per-turn seam (mode/reasoning_level/temperature,
        see app.llm.tuning) — this is the only channel through which the
        orchestrator hands per-turn knobs down; `**opts` remains for the
        handful of non-chat callers (skill_selector, intent classification)
        that pass Ollama-native kwargs like `options={...}` / `keep_alive=`.
        """
        ...

    @property
    def supports_reasoning(self) -> bool:
        """Whether this client can honor GenerationTuning.effective_reasoning().

        Checked by orchestrator.emit_start before content starts streaming
        (§7.4) so an unsupported request is surfaced as a notice instead of
        being silently dropped or sent to a vendor that will 400 on it.
        """
        return False

    async def ping(self) -> bool:
        """Return True if the provider is reachable. External providers always return True."""
        return True
