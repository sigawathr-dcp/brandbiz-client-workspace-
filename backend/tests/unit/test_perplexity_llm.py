"""Unit tests for PerplexityClient — all HTTP calls are mocked, no real API traffic."""
from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.llm.base import ChatMessage, LLMProviderError
from app.llm.perplexity import PerplexityClient
from app.llm.tuning import GenerationTuning, ResponseMode


# ---------------------------------------------------------------------------
# SSE helpers — build fake response lines as Perplexity would emit them
# ---------------------------------------------------------------------------

def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}"


def _text_chunk(content: str) -> str:
    return _sse({
        "choices": [{"delta": {"content": content}, "finish_reason": None}],
    })


def _final_chunk(
    finish_reason: str = "stop",
    citations: list[str] | None = None,
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> str:
    payload: dict = {
        "choices": [{"delta": {"content": ""}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    }
    if citations:
        payload["citations"] = citations
    return _sse(payload)


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
    return patch("app.llm.perplexity.httpx.AsyncClient", return_value=mock_client)


# ---------------------------------------------------------------------------
# Stream shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_yields_text_chunks():
    lines = [_text_chunk("Hello"), _text_chunk(" world"), _final_chunk()]
    with _patch_stream(lines):
        client = PerplexityClient(api_key="test-key")
        result = [c async for c in client.stream_chat([ChatMessage(role="user", content="Hi")])]

    text_chunks = [c for c in result if c.content]
    assert len(text_chunks) == 2
    assert text_chunks[0].content == "Hello"
    assert text_chunks[1].content == " world"


@pytest.mark.asyncio
async def test_final_chunk_has_usage():
    lines = [_text_chunk("Sure"), _final_chunk(prompt_tokens=20, completion_tokens=3)]
    with _patch_stream(lines):
        client = PerplexityClient(api_key="test-key")
        result = [c async for c in client.stream_chat([ChatMessage(role="user", content="Hi")])]

    last = result[-1]
    assert last.prompt_tokens == 20
    assert last.completion_tokens == 3
    assert last.finish_reason == "stop"
    assert last.model == "sonar"


@pytest.mark.asyncio
async def test_citations_surfaced_in_metadata():
    urls = ["https://example.com/source1", "https://example.com/source2"]
    lines = [_text_chunk("Bangkok weather"), _final_chunk(citations=urls)]
    with _patch_stream(lines):
        client = PerplexityClient(api_key="test-key")
        result = [c async for c in client.stream_chat([ChatMessage(role="user", content="weather?")])]

    last = result[-1]
    assert last.metadata is not None
    assert last.metadata["citations"] == urls


@pytest.mark.asyncio
async def test_no_citations_metadata_is_none():
    lines = [_text_chunk("hi"), _final_chunk()]
    with _patch_stream(lines):
        client = PerplexityClient(api_key="test-key")
        result = [c async for c in client.stream_chat([ChatMessage(role="user", content="Hi")])]

    last = result[-1]
    assert last.metadata is None


@pytest.mark.asyncio
async def test_citations_only_in_final_chunk_not_text_chunks():
    urls = ["https://example.com"]
    lines = [_text_chunk("a"), _text_chunk("b"), _final_chunk(citations=urls)]
    with _patch_stream(lines):
        client = PerplexityClient(api_key="test-key")
        result = [c async for c in client.stream_chat([ChatMessage(role="user", content="x")])]

    text_chunks = [c for c in result if c.content]
    for c in text_chunks:
        assert c.metadata is None

    last = result[-1]
    assert last.metadata["citations"] == urls


# ---------------------------------------------------------------------------
# Request shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_request_has_stream_true():
    lines = [_text_chunk("x"), _final_chunk()]
    captured_kwargs = {}

    fake_response = _FakeResponse(lines)
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    def capture_stream(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return fake_response

    mock_client.stream = capture_stream

    with patch("app.llm.perplexity.httpx.AsyncClient", return_value=mock_client):
        client = PerplexityClient(api_key="test-key")
        async for _ in client.stream_chat([ChatMessage(role="user", content="Hello")]):
            pass

    assert captured_kwargs["json"]["stream"] is True
    assert captured_kwargs["json"]["model"] == "sonar"
    assert captured_kwargs["json"]["messages"] == [{"role": "user", "content": "Hello"}]


# ---------------------------------------------------------------------------
# G-A1/G-A2: no reasoning knob on Sonar — temperature still applies
# ---------------------------------------------------------------------------

def test_supports_reasoning_defaults_false():
    client = PerplexityClient(api_key="test-key")
    assert client.supports_reasoning is False


@pytest.mark.asyncio
async def test_temperature_applied_reasoning_silently_not_forwarded():
    lines = [_text_chunk("x"), _final_chunk()]
    captured_kwargs = {}

    fake_response = _FakeResponse(lines)
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    def capture_stream(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return fake_response

    mock_client.stream = capture_stream

    with patch("app.llm.perplexity.httpx.AsyncClient", return_value=mock_client):
        client = PerplexityClient(api_key="test-key")
        # mode=THINKING asks for reasoning; Sonar has no such knob, so the
        # adapter must just apply temperature and drop the reasoning ask.
        tuning = GenerationTuning(mode=ResponseMode.THINKING, temperature=0.5)
        async for _ in client.stream_chat([ChatMessage(role="user", content="Hello")], tuning=tuning):
            pass

    assert captured_kwargs["json"]["temperature"] == 0.5
    assert "reasoning_effort" not in captured_kwargs["json"]
    assert "thinking" not in captured_kwargs["json"]


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

    with patch("app.llm.perplexity.httpx.AsyncClient", return_value=mock_client):
        client = PerplexityClient(api_key="my-secret-key")
        async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
            pass

    assert captured_headers["Authorization"] == "Bearer my-secret-key"


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_200_maps_to_provider_error():
    with _patch_stream([], status_code=401):
        client = PerplexityClient(api_key="bad-key")
        with pytest.raises(LLMProviderError, match="perplexity 401"):
            async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
                pass


@pytest.mark.asyncio
async def test_rate_limit_maps_to_provider_error():
    with _patch_stream([], status_code=429):
        client = PerplexityClient(api_key="test-key")
        with pytest.raises(LLMProviderError, match="perplexity 429"):
            async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
                pass


@pytest.mark.asyncio
async def test_timeout_maps_to_provider_error():
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(side_effect=httpx.TimeoutException("timed out"))

    with patch("app.llm.perplexity.httpx.AsyncClient", return_value=mock_client):
        client = PerplexityClient(api_key="test-key")
        with pytest.raises(LLMProviderError, match="unreachable"):
            async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
                pass


@pytest.mark.asyncio
async def test_connect_error_maps_to_provider_error():
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(
        side_effect=httpx.ConnectError("connection refused")
    )

    with patch("app.llm.perplexity.httpx.AsyncClient", return_value=mock_client):
        client = PerplexityClient(api_key="test-key")
        with pytest.raises(LLMProviderError, match="unreachable"):
            async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
                pass


# ---------------------------------------------------------------------------
# Real API test — skipped when PERPLEXITY_API_KEY is not set
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("PERPLEXITY_API_KEY"),
    reason="PERPLEXITY_API_KEY not set",
)
async def test_real_call_weather_in_bangkok():
    """Live call to Perplexity. Verifies streaming + citations are returned."""
    api_key = os.environ["PERPLEXITY_API_KEY"]
    client = PerplexityClient(api_key=api_key)

    chunks = [
        c async for c in client.stream_chat(
            [ChatMessage(role="user", content="What is the weather in Bangkok today?")]
        )
    ]

    text = "".join(c.content for c in chunks)
    assert len(text) > 10, "Expected a non-trivial response"

    last = chunks[-1]
    assert last.prompt_tokens is not None and last.prompt_tokens > 0
    assert last.completion_tokens is not None and last.completion_tokens > 0
    assert last.finish_reason == "stop"

    # Perplexity's sonar model returns citations for current-events queries
    assert last.metadata is not None, "Expected citations from sonar model"
    assert isinstance(last.metadata["citations"], list)
    assert len(last.metadata["citations"]) > 0, "Expected at least one citation URL"

    print("\n=== Perplexity real call result ===")
    print(f"Response text (first 300 chars): {text[:300]}")
    print(f"Tokens — prompt: {last.prompt_tokens}, completion: {last.completion_tokens}")
    print(f"Citations ({len(last.metadata['citations'])}):")
    for url in last.metadata["citations"]:
        print(f"  {url}")
