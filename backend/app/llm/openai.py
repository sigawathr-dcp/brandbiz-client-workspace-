import base64
from typing import AsyncIterator

import openai

from app.llm.base import ChatChunk, ChatMessage, LLMClient, LLMProviderError
from app.llm.tuning import GenerationTuning, ReasoningLevel

_DEFAULT_IMAGE_MODEL = "gpt-image-1"

# OpenAI's reasoning_effort has no "max" tier — clamp our MAX level to "high".
_REASONING_EFFORT: dict[ReasoningLevel, str] = {
    ReasoningLevel.LOW: "low",
    ReasoningLevel.MEDIUM: "medium",
    ReasoningLevel.HIGH: "high",
    ReasoningLevel.MAX: "high",
}


def _translate_opts(opts: dict) -> dict:
    """Map the Ollama-native kwargs helper callers pass into OpenAI params.

    intent / skill_selector / prompt_assistant were written against the local
    model and pass ``options={"num_predict": N}`` + ``keep_alive="5m"`` (see
    LLMClient.stream_chat docstring). With D25 the default model is OpenAI, so:
    ``num_predict`` -> ``max_completion_tokens``; ``keep_alive`` and any other
    Ollama-only option are dropped (OpenAI rejects unknown params with a 400).
    Everything else is passed through verbatim.
    """
    out: dict = {}
    for key, value in opts.items():
        if key == "keep_alive":
            continue
        if key == "options":
            if isinstance(value, dict) and value.get("num_predict") is not None:
                out["max_completion_tokens"] = int(value["num_predict"])
            continue
        if key == "max_tokens":
            out["max_completion_tokens"] = value
            continue
        out[key] = value
    return out


class OpenAIClient(LLMClient):
    def __init__(self, api_key: str, model: str, *, supports_reasoning: bool = False) -> None:
        self._model = model
        self._client = openai.AsyncOpenAI(api_key=api_key)
        # Only o-series / gpt-5-reasoning-class models accept reasoning_effort
        # (and reject an explicit temperature) — a per-instance flag set at
        # registration time in app/llm/router.py, not a name sniff here.
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
        sdk_messages = [{"role": m.role, "content": m.content} for m in messages]

        kwargs: dict = {
            "model": self._model,
            "messages": sdk_messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        reasoning = tuning.effective_reasoning() if self._supports_reasoning else None
        if reasoning is not None:
            kwargs["reasoning_effort"] = _REASONING_EFFORT[reasoning]
            # Reasoning models reject an explicit temperature — same drop
            # rule as Anthropic's extended thinking.
        elif tuning.temperature is not None and not self._supports_reasoning:
            # gpt-5.x reasoning-class models 400 on an explicit temperature
            # even at reasoning_effort=none; only classic models get one.
            kwargs["temperature"] = tuning.temperature

        kwargs.update(_translate_opts(opts))

        try:
            finish_reason: str | None = None
            prompt_tokens: int | None = None
            completion_tokens: int | None = None

            stream = await self._client.chat.completions.create(**kwargs)
            async for chunk in stream:
                if chunk.usage is not None:
                    prompt_tokens = chunk.usage.prompt_tokens
                    completion_tokens = chunk.usage.completion_tokens
                for choice in chunk.choices:
                    if choice.finish_reason is not None:
                        finish_reason = choice.finish_reason
                    if choice.delta.content:
                        yield ChatChunk(content=choice.delta.content, model=self._model)

            yield ChatChunk(
                content="",
                model=self._model,
                finish_reason=finish_reason,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        except openai.APIStatusError as exc:
            raise LLMProviderError(
                f"openai {exc.status_code}: {exc.message}"
            ) from exc
        except openai.APIConnectionError as exc:
            raise LLMProviderError(f"openai unreachable: {exc}") from exc

    async def raw_chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **extra,
    ) -> dict:
        """Non-streaming OpenAI-compatible passthrough (preserves tools/tool_calls).

        Returns the full completion as a dict so the compat router can relay it
        verbatim.  Callers must NOT pass 'model' or 'stream' in extra — those
        are set here.
        """
        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_completion_tokens"] = max_tokens
        kwargs.update(_translate_opts({k: v for k, v in extra.items() if k not in ("model", "stream")}))

        try:
            completion = await self._client.chat.completions.create(**kwargs)
            return completion.model_dump()
        except openai.APIStatusError as exc:
            raise LLMProviderError(f"openai {exc.status_code}: {exc.message}") from exc
        except openai.APIConnectionError as exc:
            raise LLMProviderError(f"openai unreachable: {exc}") from exc

    async def raw_streaming_chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **extra,
    ):  # AsyncIterator[str] — yields "data: …\n\n" SSE lines
        """Streaming OpenAI-compatible passthrough (preserves tools/tool_calls).

        Yields raw SSE lines (``data: {json}\\n\\n``) suitable for passing
        directly to a FastAPI ``StreamingResponse``.
        """
        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_completion_tokens"] = max_tokens
        kwargs.update(_translate_opts({k: v for k, v in extra.items() if k not in ("model", "stream", "stream_options")}))

        try:
            stream = await self._client.chat.completions.create(**kwargs)
            async for chunk in stream:
                yield f"data: {chunk.model_dump_json(exclude_unset=True)}\n\n"
            yield "data: [DONE]\n\n"
        except openai.APIStatusError as exc:
            raise LLMProviderError(f"openai {exc.status_code}: {exc.message}") from exc
        except openai.APIConnectionError as exc:
            raise LLMProviderError(f"openai unreachable: {exc}") from exc

    async def ping(self) -> bool:
        """True if the API key is valid and the configured model is visible.

        Used by the startup check and /health now that an OpenAI model can be
        the default (D25). Never raises.
        """
        try:
            await self._client.with_options(timeout=5.0).models.retrieve(self._model)
            return True
        except Exception:
            return False

    async def generate_image(self, prompt: str, model: str = _DEFAULT_IMAGE_MODEL) -> bytes:
        """Generate an image using gpt-image-1. Returns raw PNG bytes."""
        try:
            response = await self._client.images.generate(
                model=model,
                prompt=prompt,
                n=1,
            )
            b64 = response.data[0].b64_json
            return base64.b64decode(b64)
        except openai.APIStatusError as exc:
            raise LLMProviderError(f"openai {exc.status_code}: {exc.message}") from exc
        except openai.APIConnectionError as exc:
            raise LLMProviderError(f"openai unreachable: {exc}") from exc
