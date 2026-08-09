from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from app.llm.base import ChatChunk, ChatMessage, LLMClient, LLMProviderError
from app.llm.tuning import GenerationTuning

_DEFAULT_MODEL = "hermes-agent"


class HermesClient(LLMClient):
    """OpenAI-compatible client for a self-hosted Hermes Agent API server.

    Hermes runs its own agent loop (tools, memory, skills) per request before
    streaming a response, so time-to-first-token is higher than a plain chat
    model. base_url points at the operator's own Hermes instance (default
    port 8642), not a fixed vendor endpoint.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = _DEFAULT_MODEL,
        timeout: float = 120.0,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    # Hermes runs its own agent loop with no extended-reasoning knob exposed
    # to us — supports_reasoning stays the base-class default (False).

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        *,
        tuning: GenerationTuning | None = None,
        **opts,
    ) -> AsyncIterator[ChatChunk]:
        tuning = tuning or GenerationTuning()
        sdk_messages = [{"role": m.role, "content": m.content} for m in messages]

        payload: dict = {
            "model": self._model,
            "messages": sdk_messages,
            "stream": True,
        }
        if tuning.temperature is not None:
            payload["temperature"] = tuning.temperature
        payload.update(opts)

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                ) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        raise LLMProviderError(
                            f"hermes {response.status_code}: {body.decode()}"
                        )

                    prompt_tokens: int | None = None
                    completion_tokens: int | None = None
                    finish_reason: str | None = None

                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data == "[DONE]":
                            break

                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue

                        if usage := chunk.get("usage"):
                            prompt_tokens = usage.get("prompt_tokens")
                            completion_tokens = usage.get("completion_tokens")

                        for choice in chunk.get("choices", []):
                            if fr := choice.get("finish_reason"):
                                finish_reason = fr
                            content = (choice.get("delta") or {}).get("content") or ""
                            if content:
                                yield ChatChunk(content=content, model=self._model)

                    yield ChatChunk(
                        content="",
                        model=self._model,
                        finish_reason=finish_reason,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                    )
        except LLMProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise LLMProviderError("hermes unreachable: timeout") from exc
        except httpx.ConnectError as exc:
            raise LLMProviderError(f"hermes unreachable: {exc}") from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"hermes unreachable: {exc}") from exc
