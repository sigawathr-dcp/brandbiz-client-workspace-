from typing import AsyncIterator

import anthropic

from app.llm.base import ChatChunk, ChatMessage, LLMClient, LLMProviderError
from app.llm.tuning import GenerationTuning, ReasoningLevel

# Anthropic extended-thinking budget per reasoning level. Anthropic requires
# max_tokens > budget_tokens, so callers below add headroom on top of this.
_THINKING_BUDGET_TOKENS: dict[ReasoningLevel, int] = {
    ReasoningLevel.LOW: 2048,
    ReasoningLevel.MEDIUM: 8000,
    ReasoningLevel.HIGH: 16000,
    ReasoningLevel.MAX: 32000,
}


class AnthropicClient(LLMClient):
    def __init__(self, api_key: str, model: str) -> None:
        self._model = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    @property
    def supports_reasoning(self) -> bool:
        return True

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        *,
        tuning: GenerationTuning | None = None,
        **opts,
    ) -> AsyncIterator[ChatChunk]:
        tuning = tuning or GenerationTuning()

        # Anthropic API requires system content as top-level param, not in messages list
        system: str | None = None
        sdk_messages: list[dict] = []
        for m in messages:
            if m.role == "system":
                system = m.content
            else:
                sdk_messages.append({"role": m.role, "content": m.content})

        kwargs: dict = {
            "model": self._model,
            "messages": sdk_messages,
        }

        reasoning = tuning.effective_reasoning()
        if reasoning is not None:
            budget = _THINKING_BUDGET_TOKENS[reasoning]
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
            kwargs["max_tokens"] = opts.pop("max_tokens", budget + 4096)
            # Extended thinking forces temperature=1 on Anthropic's side and a
            # non-1 value is a hard 400 — never forward tuning.temperature
            # while thinking is enabled; let the API default apply.
        else:
            kwargs["max_tokens"] = opts.pop("max_tokens", 4096)
            if tuning.temperature is not None:
                kwargs["temperature"] = tuning.temperature

        if system is not None:
            kwargs["system"] = system
        kwargs.update(opts)

        try:
            stream = await self._client.messages.create(stream=True, **kwargs)
            input_tokens: int | None = None
            async for event in stream:
                if event.type == "message_start":
                    input_tokens = event.message.usage.input_tokens
                elif event.type == "content_block_delta" and event.delta.type == "text_delta":
                    yield ChatChunk(content=event.delta.text, model=self._model)
                elif event.type == "content_block_delta" and event.delta.type == "thinking_delta":
                    # Surface that extended thinking is in progress without
                    # putting the reasoning trace into the visible answer —
                    # the orchestrator turns this into a one-shot SSE notice.
                    yield ChatChunk(content="", model=self._model, metadata={"thinking": True})
                elif event.type == "message_delta":
                    yield ChatChunk(
                        content="",
                        model=self._model,
                        finish_reason=event.delta.stop_reason,
                        prompt_tokens=input_tokens,
                        completion_tokens=event.usage.output_tokens,
                    )
        except anthropic.APIStatusError as exc:
            raise LLMProviderError(
                f"anthropic {exc.status_code}: {exc.message}"
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise LLMProviderError(f"anthropic unreachable: {exc}") from exc
