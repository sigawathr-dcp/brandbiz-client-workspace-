"""Unit tests for OpenAIClient — all SDK calls are mocked, no real API traffic."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest

from app.llm.openai import OpenAIClient
from app.llm.base import ChatMessage, LLMProviderError
from app.llm.tuning import GenerationTuning, ReasoningLevel, ResponseMode


# ---------------------------------------------------------------------------
# Chunk factory helpers — mirror OpenAI SSE ChatCompletionChunk shapes
# ---------------------------------------------------------------------------

def _text_chunk(content: str, finish_reason: str | None = None):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content=content),
                finish_reason=finish_reason,
            )
        ],
        usage=None,
    )


def _finish_chunk(finish_reason: str = "stop"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content=None),
                finish_reason=finish_reason,
            )
        ],
        usage=None,
    )


def _usage_chunk(prompt_tokens: int, completion_tokens: int):
    """Last chunk emitted when stream_options.include_usage=True — choices is empty."""
    return SimpleNamespace(
        choices=[],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


async def _async_gen(chunks):
    for chunk in chunks:
        yield chunk


# ---------------------------------------------------------------------------
# Fixture: patch AsyncOpenAI at the module import level
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_sdk():
    with patch("app.llm.openai.openai.AsyncOpenAI") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


# ---------------------------------------------------------------------------
# Stream shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_yields_text_chunks(mock_sdk):
    chunks = [
        _text_chunk("Hello"),
        _text_chunk(" world"),
        _finish_chunk("stop"),
        _usage_chunk(prompt_tokens=10, completion_tokens=5),
    ]
    mock_sdk.chat.completions.create = AsyncMock(return_value=_async_gen(chunks))

    client = OpenAIClient(api_key="test-key", model="gpt-4o-mini")
    result = [c async for c in client.stream_chat([ChatMessage(role="user", content="Hi")])]

    text_chunks = [c for c in result if c.content]
    assert len(text_chunks) == 2
    assert text_chunks[0].content == "Hello"
    assert text_chunks[1].content == " world"


@pytest.mark.asyncio
async def test_final_chunk_has_usage(mock_sdk):
    chunks = [
        _text_chunk("Sure"),
        _finish_chunk("stop"),
        _usage_chunk(prompt_tokens=20, completion_tokens=3),
    ]
    mock_sdk.chat.completions.create = AsyncMock(return_value=_async_gen(chunks))

    client = OpenAIClient(api_key="test-key", model="gpt-4o-mini")
    result = [c async for c in client.stream_chat([ChatMessage(role="user", content="Hi")])]

    last = result[-1]
    assert last.prompt_tokens == 20
    assert last.completion_tokens == 3
    assert last.finish_reason == "stop"
    assert last.model == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_multiple_text_chunks_then_usage(mock_sdk):
    chunks = [
        _text_chunk("a"),
        _text_chunk("b"),
        _text_chunk("c"),
        _finish_chunk("stop"),
        _usage_chunk(prompt_tokens=5, completion_tokens=3),
    ]
    mock_sdk.chat.completions.create = AsyncMock(return_value=_async_gen(chunks))

    client = OpenAIClient(api_key="test-key", model="gpt-4o-mini")
    result = [c async for c in client.stream_chat([ChatMessage(role="user", content="x")])]

    assert [c.content for c in result] == ["a", "b", "c", ""]
    assert result[-1].prompt_tokens == 5
    assert result[-1].completion_tokens == 3


@pytest.mark.asyncio
async def test_none_content_deltas_are_skipped(mock_sdk):
    """Chunks with delta.content=None (e.g. the finish chunk) must not appear as text."""
    chunks = [
        _text_chunk("ok"),
        _finish_chunk("stop"),
        _usage_chunk(5, 1),
    ]
    mock_sdk.chat.completions.create = AsyncMock(return_value=_async_gen(chunks))

    client = OpenAIClient(api_key="test-key", model="gpt-4o-mini")
    result = [c async for c in client.stream_chat([ChatMessage(role="user", content="Hi")])]

    text_chunks = [c for c in result if c.content]
    assert len(text_chunks) == 1
    assert text_chunks[0].content == "ok"


# ---------------------------------------------------------------------------
# Request shape — verify what gets sent to the SDK
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_system_message_passed_through_in_messages(mock_sdk):
    """Unlike Anthropic, OpenAI accepts system role directly in the messages list."""
    chunks = [_text_chunk("hi"), _finish_chunk(), _usage_chunk(5, 1)]
    mock_sdk.chat.completions.create = AsyncMock(return_value=_async_gen(chunks))

    client = OpenAIClient(api_key="test-key", model="gpt-4o-mini")
    async for _ in client.stream_chat([
        ChatMessage(role="system", content="You are helpful."),
        ChatMessage(role="user", content="Hi"),
    ]):
        pass

    _, call_kwargs = mock_sdk.chat.completions.create.call_args
    messages = call_kwargs["messages"]
    assert messages[0] == {"role": "system", "content": "You are helpful."}
    assert messages[1] == {"role": "user", "content": "Hi"}


@pytest.mark.asyncio
async def test_request_shape_matches_api_spec(mock_sdk):
    """stream=True, stream_options, model, and extra opts forwarded."""
    chunks = [_text_chunk("x"), _finish_chunk(), _usage_chunk(3, 1)]
    mock_sdk.chat.completions.create = AsyncMock(return_value=_async_gen(chunks))

    client = OpenAIClient(api_key="test-key", model="gpt-4o")
    async for _ in client.stream_chat(
        [ChatMessage(role="user", content="Hello")],
        temperature=0.7,
        max_tokens=512,
    ):
        pass

    _, call_kwargs = mock_sdk.chat.completions.create.call_args
    assert call_kwargs["model"] == "gpt-4o"
    assert call_kwargs["stream"] is True
    assert call_kwargs["stream_options"] == {"include_usage": True}
    assert call_kwargs["temperature"] == 0.7
    assert call_kwargs["max_completion_tokens"] == 512  # D25: max_tokens is translated for gpt-5.x
    assert call_kwargs["messages"] == [{"role": "user", "content": "Hello"}]


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_status_error_maps_to_provider_error(mock_sdk):
    mock_response = MagicMock()
    mock_response.status_code = 401
    error = openai.AuthenticationError(
        "Unauthorized",
        response=mock_response,
        body={"error": {"message": "Unauthorized", "type": "invalid_request_error"}},
    )
    mock_sdk.chat.completions.create = AsyncMock(side_effect=error)

    client = OpenAIClient(api_key="bad-key", model="gpt-4o-mini")
    with pytest.raises(LLMProviderError, match="openai 401"):
        async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
            pass


@pytest.mark.asyncio
async def test_rate_limit_error_maps_to_provider_error(mock_sdk):
    mock_response = MagicMock()
    mock_response.status_code = 429
    error = openai.RateLimitError(
        "Rate limited",
        response=mock_response,
        body={},
    )
    mock_sdk.chat.completions.create = AsyncMock(side_effect=error)

    client = OpenAIClient(api_key="test-key", model="gpt-4o-mini")
    with pytest.raises(LLMProviderError, match="openai 429"):
        async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
            pass


@pytest.mark.asyncio
async def test_connection_error_maps_to_provider_error(mock_sdk):
    mock_sdk.chat.completions.create = AsyncMock(
        side_effect=openai.APIConnectionError(request=MagicMock())
    )

    client = OpenAIClient(api_key="test-key", model="gpt-4o-mini")
    with pytest.raises(LLMProviderError, match="unreachable"):
        async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
            pass


@pytest.mark.asyncio
async def test_timeout_error_maps_to_provider_error(mock_sdk):
    """APITimeoutError is a subclass of APIConnectionError — same handler."""
    mock_sdk.chat.completions.create = AsyncMock(
        side_effect=openai.APITimeoutError(request=MagicMock())
    )

    client = OpenAIClient(api_key="test-key", model="gpt-4o-mini")
    with pytest.raises(LLMProviderError, match="unreachable"):
        async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
            pass


# ---------------------------------------------------------------------------
# G-A1/G-A2: GenerationTuning -> reasoning_effort (reasoning-capable models only)
# ---------------------------------------------------------------------------

def test_supports_reasoning_defaults_false():
    """Most registered OpenAI codes (gpt-4o, gpt-4o-mini) are not reasoning
    models — the flag must default off, not on."""
    client = OpenAIClient(api_key="test-key", model="gpt-4o")
    assert client.supports_reasoning is False


def test_supports_reasoning_true_when_constructed_with_flag():
    client = OpenAIClient(api_key="test-key", model="o3-mini", supports_reasoning=True)
    assert client.supports_reasoning is True


@pytest.mark.asyncio
async def test_non_reasoning_model_ignores_reasoning_request_and_applies_temperature(mock_sdk):
    """A model with supports_reasoning=False must not receive reasoning_effort
    even if the caller's tuning asks for it — emit_start is responsible for
    stripping the request before it gets here; this just proves the adapter
    itself never forwards it."""
    chunks = [_text_chunk("x"), _finish_chunk(), _usage_chunk(3, 1)]
    mock_sdk.chat.completions.create = AsyncMock(return_value=_async_gen(chunks))

    client = OpenAIClient(api_key="test-key", model="gpt-4o")
    tuning = GenerationTuning(mode=ResponseMode.THINKING, temperature=0.6)
    async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")], tuning=tuning):
        pass

    _, call_kwargs = mock_sdk.chat.completions.create.call_args
    assert "reasoning_effort" not in call_kwargs
    assert call_kwargs["temperature"] == 0.6


@pytest.mark.asyncio
async def test_reasoning_model_receives_effort_and_omits_temperature(mock_sdk):
    chunks = [_text_chunk("x"), _finish_chunk(), _usage_chunk(3, 1)]
    mock_sdk.chat.completions.create = AsyncMock(return_value=_async_gen(chunks))

    client = OpenAIClient(api_key="test-key", model="o3-mini", supports_reasoning=True)
    tuning = GenerationTuning(mode=ResponseMode.THINKING, temperature=0.6)
    async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")], tuning=tuning):
        pass

    _, call_kwargs = mock_sdk.chat.completions.create.call_args
    assert call_kwargs["reasoning_effort"] == "medium"
    assert "temperature" not in call_kwargs


@pytest.mark.asyncio
async def test_max_reasoning_level_clamps_to_high(mock_sdk):
    """OpenAI has no 'max' reasoning_effort tier."""
    chunks = [_text_chunk("x"), _finish_chunk(), _usage_chunk(3, 1)]
    mock_sdk.chat.completions.create = AsyncMock(return_value=_async_gen(chunks))

    client = OpenAIClient(api_key="test-key", model="o3-mini", supports_reasoning=True)
    tuning = GenerationTuning(mode=ResponseMode.PRO, reasoning_level=ReasoningLevel.MAX)
    async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")], tuning=tuning):
        pass

    _, call_kwargs = mock_sdk.chat.completions.create.call_args
    assert call_kwargs["reasoning_effort"] == "high"
