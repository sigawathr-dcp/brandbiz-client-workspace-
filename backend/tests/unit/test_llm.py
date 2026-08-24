"""Unit tests for LLM base, llamacpp adapter, and router."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.llm.base import ChatChunk, ChatMessage, LLMProviderError
from app.llm.llamacpp import LlamaCppClient
from app.llm.router import DEFAULT_MODEL_CODE, LLMRouter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ndjson_lines(*contents: str, include_usage: bool = True) -> list[str]:
    """Build fake NDJSON lines as Ollama's native /api/chat emits."""
    lines: list[str] = []
    for i, text in enumerate(contents):
        is_last = i == len(contents) - 1
        chunk: dict = {
            "model": "qwen2.5-14b-local",
            "message": {"role": "assistant", "content": text},
            "done": is_last,
        }
        if is_last:
            chunk["done_reason"] = "stop"
            if include_usage:
                chunk["prompt_eval_count"] = 10
                chunk["eval_count"] = len(contents)
        lines.append(json.dumps(chunk))
    return lines


async def _async_iter(items: list[str]):
    for item in items:
        yield item


# ---------------------------------------------------------------------------
# LlamaCppClient tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_chat_yields_chunks():
    lines = _make_ndjson_lines("Hello", " world", "!")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.aiter_lines = lambda: _async_iter(lines)

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_client_ctx = AsyncMock()
    mock_client_ctx.__aenter__ = AsyncMock(return_value=MagicMock(stream=lambda *a, **kw: mock_ctx))
    mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

    client = LlamaCppClient(base_url="http://localhost:8080", model="qwen2.5-14b-local")

    with patch("app.llm.llamacpp.httpx.AsyncClient", return_value=mock_client_ctx):
        chunks = []
        async for chunk in client.stream_chat([ChatMessage(role="user", content="Hi")]):
            chunks.append(chunk)

    assert len(chunks) == 3
    assert chunks[0].content == "Hello"
    assert chunks[1].content == " world"
    assert chunks[2].content == "!"
    assert chunks[2].finish_reason == "stop"


@pytest.mark.asyncio
async def test_stream_chat_last_chunk_has_usage():
    lines = _make_ndjson_lines("Answer", include_usage=True)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.aiter_lines = lambda: _async_iter(lines)

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_client_ctx = AsyncMock()
    mock_client_ctx.__aenter__ = AsyncMock(return_value=MagicMock(stream=lambda *a, **kw: mock_ctx))
    mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

    client = LlamaCppClient(base_url="http://localhost:8080")

    with patch("app.llm.llamacpp.httpx.AsyncClient", return_value=mock_client_ctx):
        chunks = [c async for c in client.stream_chat([ChatMessage(role="user", content="Hi")])]

    last = chunks[-1]
    assert last.prompt_tokens == 10
    assert last.completion_tokens == 1


@pytest.mark.asyncio
async def test_stream_chat_http_error_raises():
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.aread = AsyncMock(return_value=b"Internal server error")

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_client_ctx = AsyncMock()
    mock_client_ctx.__aenter__ = AsyncMock(return_value=MagicMock(stream=lambda *a, **kw: mock_ctx))
    mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

    client = LlamaCppClient(base_url="http://localhost:8080")

    with patch("app.llm.llamacpp.httpx.AsyncClient", return_value=mock_client_ctx):
        with pytest.raises(LLMProviderError, match="500"):
            async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
                pass


@pytest.mark.asyncio
async def test_stream_chat_connect_error_raises_provider_error():
    client = LlamaCppClient(base_url="http://localhost:8080")

    with patch("app.llm.llamacpp.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(
            side_effect=httpx.ConnectError("Name or service not known")
        )
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(LLMProviderError, match="reachable"):
            async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
                pass


@pytest.mark.asyncio
async def test_stream_chat_timeout_raises_provider_error():
    client = LlamaCppClient(base_url="http://localhost:8080")

    with patch("app.llm.llamacpp.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(
            side_effect=httpx.TimeoutException("timed out")
        )
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(LLMProviderError, match="unreachable"):
            async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
                pass


@pytest.mark.asyncio
async def test_stream_chat_skips_malformed_sse():
    lines = ["not-json", "{also-bad"]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.aiter_lines = lambda: _async_iter(lines)

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_client_ctx = AsyncMock()
    mock_client_ctx.__aenter__ = AsyncMock(return_value=MagicMock(stream=lambda *a, **kw: mock_ctx))
    mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

    client = LlamaCppClient(base_url="http://localhost:8080")

    with patch("app.llm.llamacpp.httpx.AsyncClient", return_value=mock_client_ctx):
        chunks = [c async for c in client.stream_chat([ChatMessage(role="user", content="Hi")])]

    assert chunks == []


# ---------------------------------------------------------------------------
# LLMRouter tests
# ---------------------------------------------------------------------------

def _router() -> LLMRouter:
    return LLMRouter(DEFAULT_MODEL_CODE, LlamaCppClient(base_url="http://localhost:8080"))


def test_router_returns_default_client():
    router = _router()
    client = router.get(DEFAULT_MODEL_CODE)
    assert client is not None
    assert router.default_code == DEFAULT_MODEL_CODE


def test_router_unknown_model_raises():
    router = _router()
    with pytest.raises(KeyError, match="claude-sonnet-4"):
        router.get("claude-sonnet-4")


def test_router_register_and_retrieve():
    router = _router()
    fake_client = MagicMock()
    router.register("test-model", fake_client)
    assert router.get("test-model") is fake_client
