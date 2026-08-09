"""Unit tests for AnthropicClient — all SDK calls are mocked, no real API traffic."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import pytest

from app.llm.anthropic import AnthropicClient
from app.llm.base import ChatMessage, LLMProviderError


# ---------------------------------------------------------------------------
# Event factory helpers — mirror Anthropic SSE event shapes
# ---------------------------------------------------------------------------

def _msg_start(input_tokens: int = 10):
    return SimpleNamespace(
        type="message_start",
        message=SimpleNamespace(usage=SimpleNamespace(input_tokens=input_tokens)),
    )


def _text_delta(text: str):
    return SimpleNamespace(
        type="content_block_delta",
        index=0,
        delta=SimpleNamespace(type="text_delta", text=text),
    )


def _non_text_delta():
    """Simulates an input_json_delta that should be silently ignored."""
    return SimpleNamespace(
        type="content_block_delta",
        index=0,
        delta=SimpleNamespace(type="input_json_delta", partial_json='{"k":'),
    )


def _msg_delta(output_tokens: int = 5, stop_reason: str = "end_turn"):
    return SimpleNamespace(
        type="message_delta",
        delta=SimpleNamespace(stop_reason=stop_reason, stop_sequence=None),
        usage=SimpleNamespace(output_tokens=output_tokens),
    )


def _content_block_start():
    return SimpleNamespace(type="content_block_start", index=0)


def _content_block_stop():
    return SimpleNamespace(type="content_block_stop", index=0)


def _msg_stop():
    return SimpleNamespace(type="message_stop")


async def _async_gen(events):
    for event in events:
        yield event


# ---------------------------------------------------------------------------
# Fixture: patch AsyncAnthropic at the module import level
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_sdk():
    with patch("app.llm.anthropic.anthropic.AsyncAnthropic") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


# ---------------------------------------------------------------------------
# Stream shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_yields_text_chunks(mock_sdk):
    events = [
        _msg_start(input_tokens=12),
        _content_block_start(),
        _text_delta("Hello"),
        _text_delta(" world"),
        _content_block_stop(),
        _msg_delta(output_tokens=7),
        _msg_stop(),
    ]
    mock_sdk.messages.create = AsyncMock(return_value=_async_gen(events))

    client = AnthropicClient(api_key="test-key", model="claude-sonnet-4-6")
    chunks = [c async for c in client.stream_chat([ChatMessage(role="user", content="Hi")])]

    text_chunks = [c for c in chunks if c.content]
    assert len(text_chunks) == 2
    assert text_chunks[0].content == "Hello"
    assert text_chunks[1].content == " world"


@pytest.mark.asyncio
async def test_final_chunk_has_usage(mock_sdk):
    events = [
        _msg_start(input_tokens=20),
        _text_delta("Sure"),
        _msg_delta(output_tokens=3, stop_reason="end_turn"),
    ]
    mock_sdk.messages.create = AsyncMock(return_value=_async_gen(events))

    client = AnthropicClient(api_key="test-key", model="claude-sonnet-4-6")
    chunks = [c async for c in client.stream_chat([ChatMessage(role="user", content="Hi")])]

    last = chunks[-1]
    assert last.prompt_tokens == 20
    assert last.completion_tokens == 3
    assert last.finish_reason == "end_turn"
    assert last.model == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_multiple_chunks_then_usage(mock_sdk):
    """Stream yields N text chunks then one usage chunk — consumer sees them all."""
    events = [
        _msg_start(input_tokens=5),
        _text_delta("a"),
        _text_delta("b"),
        _text_delta("c"),
        _msg_delta(output_tokens=3),
    ]
    mock_sdk.messages.create = AsyncMock(return_value=_async_gen(events))

    client = AnthropicClient(api_key="test-key", model="claude-sonnet-4-6")
    chunks = [c async for c in client.stream_chat([ChatMessage(role="user", content="x")])]

    assert [c.content for c in chunks] == ["a", "b", "c", ""]
    assert chunks[-1].prompt_tokens == 5
    assert chunks[-1].completion_tokens == 3


@pytest.mark.asyncio
async def test_non_text_deltas_are_skipped(mock_sdk):
    events = [
        _msg_start(),
        _non_text_delta(),
        _text_delta("ok"),
        _msg_delta(),
    ]
    mock_sdk.messages.create = AsyncMock(return_value=_async_gen(events))

    client = AnthropicClient(api_key="test-key", model="claude-sonnet-4-6")
    chunks = [c async for c in client.stream_chat([ChatMessage(role="user", content="Hi")])]

    text_chunks = [c for c in chunks if c.content]
    assert len(text_chunks) == 1
    assert text_chunks[0].content == "ok"


# ---------------------------------------------------------------------------
# Request shape — verify what gets sent to the SDK
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_system_message_extracted_to_top_level_param(mock_sdk):
    """system role must NOT appear in the messages list — Anthropic rejects it."""
    events = [_msg_start(), _text_delta("hi"), _msg_delta()]
    mock_sdk.messages.create = AsyncMock(return_value=_async_gen(events))

    client = AnthropicClient(api_key="test-key", model="claude-sonnet-4-6")
    async for _ in client.stream_chat([
        ChatMessage(role="system", content="You are helpful."),
        ChatMessage(role="user", content="Hi"),
    ]):
        pass

    _, call_kwargs = mock_sdk.messages.create.call_args
    assert call_kwargs.get("system") == "You are helpful."
    assert all(m["role"] != "system" for m in call_kwargs["messages"])


@pytest.mark.asyncio
async def test_request_shape_matches_api_spec(mock_sdk):
    """model, max_tokens, stream=True, messages forwarded correctly."""
    events = [_msg_start(), _text_delta("x"), _msg_delta()]
    mock_sdk.messages.create = AsyncMock(return_value=_async_gen(events))

    client = AnthropicClient(api_key="test-key", model="claude-opus-4-8")
    async for _ in client.stream_chat(
        [ChatMessage(role="user", content="Hello")],
        max_tokens=512,
        temperature=0.5,
    ):
        pass

    _, call_kwargs = mock_sdk.messages.create.call_args
    assert call_kwargs["model"] == "claude-opus-4-8"
    assert call_kwargs["max_tokens"] == 512
    assert call_kwargs["temperature"] == 0.5
    assert call_kwargs["stream"] is True
    assert call_kwargs["messages"] == [{"role": "user", "content": "Hello"}]


@pytest.mark.asyncio
async def test_default_max_tokens_applied(mock_sdk):
    events = [_msg_start(), _text_delta("hi"), _msg_delta()]
    mock_sdk.messages.create = AsyncMock(return_value=_async_gen(events))

    client = AnthropicClient(api_key="test-key", model="claude-sonnet-4-6")
    async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
        pass

    _, call_kwargs = mock_sdk.messages.create.call_args
    assert call_kwargs["max_tokens"] == 4096


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_status_error_maps_to_provider_error(mock_sdk):
    mock_response = MagicMock()
    mock_response.status_code = 401
    error = anthropic.APIStatusError(
        "Unauthorized",
        response=mock_response,
        body={"error": {"message": "Unauthorized"}},
    )
    mock_sdk.messages.create = AsyncMock(side_effect=error)

    client = AnthropicClient(api_key="bad-key", model="claude-sonnet-4-6")
    with pytest.raises(LLMProviderError, match="anthropic 401"):
        async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
            pass


@pytest.mark.asyncio
async def test_rate_limit_error_maps_to_provider_error(mock_sdk):
    mock_response = MagicMock()
    mock_response.status_code = 429
    error = anthropic.RateLimitError(
        "Rate limited",
        response=mock_response,
        body={},
    )
    mock_sdk.messages.create = AsyncMock(side_effect=error)

    client = AnthropicClient(api_key="test-key", model="claude-sonnet-4-6")
    with pytest.raises(LLMProviderError, match="anthropic 429"):
        async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
            pass


@pytest.mark.asyncio
async def test_connection_error_maps_to_provider_error(mock_sdk):
    mock_sdk.messages.create = AsyncMock(
        side_effect=anthropic.APIConnectionError(request=MagicMock())
    )

    client = AnthropicClient(api_key="test-key", model="claude-sonnet-4-6")
    with pytest.raises(LLMProviderError, match="unreachable"):
        async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
            pass


@pytest.mark.asyncio
async def test_timeout_error_maps_to_provider_error(mock_sdk):
    """APITimeoutError is a subclass of APIConnectionError — same handler."""
    mock_sdk.messages.create = AsyncMock(
        side_effect=anthropic.APITimeoutError(request=MagicMock())
    )

    client = AnthropicClient(api_key="test-key", model="claude-sonnet-4-6")
    with pytest.raises(LLMProviderError, match="unreachable"):
        async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
            pass
