from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from app.llm.base import ChatChunk, ChatMessage, LLMClient, LLMProviderError

_BASE_URL = "https://api.perplexity.ai"
_DEFAULT_MODEL = "sonar"


class PerplexityClient(LLMClient):
    def __init__(self, api_key: str, model: str = _DEFAULT_MODEL) -> None:
        self._model = model
        self._api_key = api_key

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        **opts,
    ) -> AsyncIterator[ChatChunk]:
        sdk_messages = [{"role": m.role, "content": m.content} for m in messages]

        payload: dict = {
            "model": self._model,
            "messages": sdk_messages,
            "stream": True,
            **opts,
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{_BASE_URL}/chat/completions",
                    json=payload,
                    headers=headers,
                ) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        raise LLMProviderError(
                            f"perplexity {response.status_code}: {body.decode()}"
                        )

                    citations: list[str] | None = None
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

                        if raw_citations := chunk.get("citations"):
                            citations = raw_citations

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
                        metadata={"citations": citations} if citations else None,
                    )
        except LLMProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise LLMProviderError("perplexity unreachable: timeout") from exc
        except httpx.ConnectError as exc:
            raise LLMProviderError(f"perplexity unreachable: {exc}") from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"perplexity unreachable: {exc}") from exc
