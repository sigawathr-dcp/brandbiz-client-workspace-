from typing import AsyncIterator

import anthropic

from app.llm.base import ChatChunk, ChatMessage, LLMClient, LLMProviderError


class AnthropicClient(LLMClient):
    def __init__(self, api_key: str, model: str) -> None:
        self._model = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        **opts,
    ) -> AsyncIterator[ChatChunk]:
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
            "max_tokens": opts.pop("max_tokens", 4096),
            "messages": sdk_messages,
        }
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
