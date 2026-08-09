from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


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
        **opts,
    ) -> AsyncIterator[ChatChunk]:
        """Stream chat completions as ChatChunk deltas."""
        ...

    async def ping(self) -> bool:
        """Return True if the provider is reachable. External providers always return True."""
        return True
