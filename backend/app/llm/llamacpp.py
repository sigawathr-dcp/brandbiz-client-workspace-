import asyncio
import json
from typing import AsyncIterator

import httpx

from app.llm.base import ChatChunk, ChatMessage, LLMClient, LLMProviderError
from app.llm.tuning import GenerationTuning, ReasoningLevel

_RETRY_BACKOFF = [0.5 * (i + 1) for i in range(10)]

# Ollama has no thinking-budget concept — reasoning depth is approximated as
# a generation-length hint (num_predict) on models that expose "think": true.
_NUM_PREDICT: dict[ReasoningLevel, int] = {
    ReasoningLevel.LOW: 512,
    ReasoningLevel.MEDIUM: 1024,
    ReasoningLevel.HIGH: 2048,
    ReasoningLevel.MAX: 4096,
}


class LlamaCppClient(LLMClient):
    """Chat client using Ollama's native /api/chat endpoint.

    Uses the native endpoint instead of the OpenAI-compatible /v1/chat/completions
    so that keep_alive is honoured reliably and tool-calling is available.
    Streaming response is NDJSON (one JSON object per line), not SSE.
    """

    def __init__(
        self,
        base_url: str,
        model: str = "local",
        connect_timeout: float = 10.0,
        read_timeout: float = 600.0,
        connect_retries: int = 3,
        keep_alive: str = "0",
        supports_reasoning: bool = False,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._connect_retries = max(connect_retries, 1)
        self._keep_alive = keep_alive
        # Off by default: most Ollama-served models have no "think" mode, and
        # a wrong-by-default True would 400 on models that don't support it.
        self._supports_reasoning = supports_reasoning

    @property
    def supports_reasoning(self) -> bool:
        return self._supports_reasoning

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        *,
        tuning: GenerationTuning | None = None,
        **opts,
    ) -> AsyncIterator[ChatChunk]:
        tuning = tuning or GenerationTuning()
        payload: dict = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "keep_alive": self._keep_alive,
        }

        # Ollama nests tuning params under "options", not top-level — a caller
        # (e.g. skill_selector) may already pass an explicit `options={...}`
        # kwarg, so build ours first and let the caller's keys win on merge
        # rather than being clobbered.
        caller_options = dict(opts.pop("options", {}))
        merged_options: dict = {}
        if tuning.temperature is not None:
            merged_options["temperature"] = tuning.temperature
        reasoning = tuning.effective_reasoning() if self._supports_reasoning else None
        if reasoning is not None:
            payload["think"] = True
            merged_options["num_predict"] = _NUM_PREDICT[reasoning]
        merged_options.update(caller_options)
        if merged_options:
            payload["options"] = merged_options

        payload.update(opts)

        timeout = httpx.Timeout(
            connect=self._connect_timeout,
            read=self._read_timeout,
            write=self._connect_timeout,
            pool=5.0,
        )

        last_connect_exc: Exception | None = None

        for attempt in range(self._connect_retries):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    async with client.stream(
                        "POST",
                        f"{self._base_url}/api/chat",
                        json=payload,
                    ) as response:
                        if response.status_code != 200:
                            body = await response.aread()
                            body_text = body.decode(errors="replace")[:400]
                            if response.status_code == 404 and (
                                "model" in body_text.lower() and "not found" in body_text.lower()
                            ):
                                raise LLMProviderError(
                                    f"Model '{self._model}' is not available on the local server. "
                                    "Run `ollama list` on the server to see available models."
                                )
                            raise LLMProviderError(
                                f"Ollama returned {response.status_code}: {body_text}"
                            )

                        # Native Ollama streams NDJSON — one JSON object per line.
                        async for line in response.aiter_lines():
                            if not line:
                                continue
                            try:
                                chunk = json.loads(line)
                            except json.JSONDecodeError:
                                continue

                            done = chunk.get("done", False)
                            content = chunk.get("message", {}).get("content") or ""
                            # done_reason and token counts only present in the final chunk.
                            finish_reason = chunk.get("done_reason") if done else None
                            prompt_tokens = chunk.get("prompt_eval_count") if done else None
                            completion_tokens = chunk.get("eval_count") if done else None

                            yield ChatChunk(
                                content=content,
                                model=chunk.get("model"),
                                finish_reason=finish_reason,
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                            )

                            if done:
                                return

                return

            except LLMProviderError:
                raise

            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
                last_connect_exc = exc
                if attempt < self._connect_retries - 1:
                    await asyncio.sleep(_RETRY_BACKOFF[attempt])

            except httpx.ReadTimeout as exc:
                raise LLMProviderError(
                    "Local model timed out while generating a response."
                ) from exc

            except httpx.HTTPError as exc:
                raise LLMProviderError(f"Ollama unreachable: {exc}") from exc

        raise LLMProviderError(
            f"Local model server is not reachable at {self._base_url}. "
            "Check that the model server is running and on the network."
        ) from last_connect_exc

    async def raw_chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **extra,
    ) -> dict:
        """Non-streaming passthrough via Ollama's OpenAI-compat endpoint.

        Uses ``{base_url}/v1/chat/completions`` (not ``/api/chat``) because the
        OpenAI-compat surface supports the full tool-calling schema.
        """
        payload: dict = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        payload.update({k: v for k, v in extra.items() if k not in ("model", "stream")})

        timeout = httpx.Timeout(
            connect=self._connect_timeout,
            read=self._read_timeout,
            write=self._connect_timeout,
            pool=5.0,
        )
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self._base_url}/v1/chat/completions",
                    json=payload,
                )
                if response.status_code != 200:
                    body_text = response.text[:400]
                    raise LLMProviderError(
                        f"Ollama returned {response.status_code}: {body_text}"
                    )
                return response.json()
        except LLMProviderError:
            raise
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Ollama unreachable: {exc}") from exc

    async def raw_streaming_chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **extra,
    ):  # AsyncIterator[str] — yields "data: …\n\n" SSE lines
        """Streaming passthrough via Ollama's OpenAI-compat endpoint.

        Yields raw SSE lines (``data: {json}\\n\\n``) forwarded verbatim from
        Ollama.  Ollama's OpenAI-compat endpoint emits standard SSE including
        ``data: [DONE]`` at the end.
        """
        payload: dict = {
            "model": self._model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        payload.update({k: v for k, v in extra.items() if k not in ("model", "stream")})

        timeout = httpx.Timeout(
            connect=self._connect_timeout,
            read=self._read_timeout,
            write=self._connect_timeout,
            pool=5.0,
        )
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/v1/chat/completions",
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        raise LLMProviderError(
                            f"Ollama returned {response.status_code}: "
                            f"{body.decode(errors='replace')[:400]}"
                        )
                    # Ollama SSE: each line is "data: {json}" or "data: [DONE]"
                    # aiter_lines() strips the trailing newlines; we re-add \n\n
                    # so the output is valid SSE for StreamingResponse.
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        yield line + "\n\n"
        except LLMProviderError:
            raise
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Ollama unreachable: {exc}") from exc

    async def ping(self) -> bool:
        """Return True if the Ollama server is reachable and responding."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as client:
                r = await client.get(f"{self._base_url}/api/tags")
                return r.status_code == 200
        except Exception:
            return False
