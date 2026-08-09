"""Unit tests for HermesClient — all HTTP calls are mocked, no real API traffic."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.llm.base import ChatMessage, LLMProviderError
from app.llm.hermes import HermesClient

_BASE_URL = "http://localhost:8642/v1"


# ---------------------------------------------------------------------------
# SSE helpers — build fake response lines as Hermes's OpenAI-compatible
# API server would emit them
# ---------------------------------------------------------------------------

def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}"


def _text_chunk(content: str) -> str:
    return _sse({
        "choices": [{"delta": {"content": content}, "finish_reason": None}],
    })


def _final_chunk(
    finish_reason: str = "stop",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> str:
    return _sse({
        "choices": [{"delta": {"content": ""}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    })


async def _lines_gen(lines: list[str]):
    for line in lines:
        yield line
    yield "data: [DONE]"


# ---------------------------------------------------------------------------
# Fixture: patch httpx.AsyncClient.stream
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, lines: list[str], status_code: int = 200) -> None:
        self._lines = lines
        self.status_code = status_code

    def aiter_lines(self):
        return _lines_gen(self._lines)

    async def aread(self) -> bytes:
        return b'{"error": "bad request"}'

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _patch_stream(lines: list[str], status_code: int = 200):
    fake_response = _FakeResponse(lines, status_code)
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(return_value=fake_response)
    return patch("app.llm.hermes.httpx.AsyncClient", return_value=mock_client)


def _client(**kwargs) -> HermesClient:
    kwargs.setdefault("api_key", "test-key")
    kwargs.setdefault("base_url", _BASE_URL)
    return HermesClient(**kwargs)


# ---------------------------------------------------------------------------
# Stream shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_yields_text_chunks():
    lines = [_text_chunk("Hello"), _text_chunk(" world"), _final_chunk()]
    with _patch_stream(lines):
        client = _client()
        result = [c async for c in client.stream_chat([ChatMessage(role="user", content="Hi")])]

    text_chunks = [c for c in result if c.content]
    assert len(text_chunks) == 2
    assert text_chunks[0].content == "Hello"
    assert text_chunks[1].content == " world"


@pytest.mark.asyncio
async def test_final_chunk_has_usage():
    lines = [_text_chunk("Sure"), _final_chunk(prompt_tokens=20, completion_tokens=3)]
    with _patch_stream(lines):
        client = _client()
        result = [c async for c in client.stream_chat([ChatMessage(role="user", content="Hi")])]

    last = result[-1]
    assert last.prompt_tokens == 20
    assert last.completion_tokens == 3
    assert last.finish_reason == "stop"
    assert last.model == "hermes-agent"


# ---------------------------------------------------------------------------
# Request shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_request_hits_configured_base_url():
    lines = [_text_chunk("x"), _final_chunk()]
    captured = {}

    fake_response = _FakeResponse(lines)
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    def capture_stream(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured.update(kwargs)
        return fake_response

    mock_client.stream = capture_stream

    with patch("app.llm.hermes.httpx.AsyncClient", return_value=mock_client):
        client = _client(base_url="http://hermes.internal:8642/v1")
        async for _ in client.stream_chat([ChatMessage(role="user", content="Hello")]):
            pass

    assert captured["url"] == "http://hermes.internal:8642/v1/chat/completions"
    assert captured["json"]["stream"] is True
    assert captured["json"]["model"] == "hermes-agent"
    assert captured["json"]["messages"] == [{"role": "user", "content": "Hello"}]


@pytest.mark.asyncio
async def test_default_timeout_is_120s():
    lines = [_text_chunk("x"), _final_chunk()]
    with _patch_stream(lines) as mock_ctor:
        client = _client()
        async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
            pass

    assert mock_ctor.call_args.kwargs["timeout"] == 120.0


@pytest.mark.asyncio
async def test_custom_timeout_is_honored():
    """Background agent tasks (Task 3.12) inject a much longer timeout via
    HermesClient(timeout=...) / config.hermes_api_timeout, since Hermes's
    unattended tool loop can run far longer than an interactive chat turn."""
    lines = [_text_chunk("x"), _final_chunk()]
    with _patch_stream(lines) as mock_ctor:
        client = _client(timeout=600.0)
        async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
            pass

    assert mock_ctor.call_args.kwargs["timeout"] == 600.0


@pytest.mark.asyncio
async def test_base_url_trailing_slash_stripped():
    lines = [_text_chunk("x"), _final_chunk()]
    captured = {}

    fake_response = _FakeResponse(lines)
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    def capture_stream(method, url, **kwargs):
        captured["url"] = url
        return fake_response

    mock_client.stream = capture_stream

    with patch("app.llm.hermes.httpx.AsyncClient", return_value=mock_client):
        client = _client(base_url="http://hermes.internal:8642/v1/")
        async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
            pass

    assert captured["url"] == "http://hermes.internal:8642/v1/chat/completions"


@pytest.mark.asyncio
async def test_auth_header_present():
    lines = [_text_chunk("x"), _final_chunk()]
    captured_headers = {}

    fake_response = _FakeResponse(lines)
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    def capture_stream(*args, **kwargs):
        captured_headers.update(kwargs.get("headers", {}))
        return fake_response

    mock_client.stream = capture_stream

    with patch("app.llm.hermes.httpx.AsyncClient", return_value=mock_client):
        client = _client(api_key="my-secret-key")
        async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
            pass

    assert captured_headers["Authorization"] == "Bearer my-secret-key"


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_200_maps_to_provider_error():
    with _patch_stream([], status_code=401):
        client = _client(api_key="bad-key")
        with pytest.raises(LLMProviderError, match="hermes 401"):
            async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
                pass


@pytest.mark.asyncio
async def test_timeout_maps_to_provider_error():
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(side_effect=httpx.TimeoutException("timed out"))

    with patch("app.llm.hermes.httpx.AsyncClient", return_value=mock_client):
        client = _client()
        with pytest.raises(LLMProviderError, match="unreachable"):
            async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
                pass


@pytest.mark.asyncio
async def test_connect_error_maps_to_provider_error():
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(side_effect=httpx.ConnectError("connection refused"))

    with patch("app.llm.hermes.httpx.AsyncClient", return_value=mock_client):
        client = _client()
        with pytest.raises(LLMProviderError, match="unreachable"):
            async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
                pass
