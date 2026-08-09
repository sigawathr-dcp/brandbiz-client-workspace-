"""Unit tests for LlamaCppClient — retry logic and error mapping.

All httpx I/O is mocked; no real network calls are made.
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.llm.base import LLMClient, ChatMessage, LLMProviderError
from app.llm.llamacpp import LlamaCppClient
from app.llm.tuning import GenerationTuning, ResponseMode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ndjson_line(
    content: str | None = None,
    done: bool = False,
    done_reason: str | None = None,
    prompt_eval_count: int | None = None,
    eval_count: int | None = None,
) -> str:
    """Build one NDJSON line as Ollama's native /api/chat emits."""
    chunk: dict = {
        "model": "gemma4:26b",
        "message": {"role": "assistant", "content": content or ""},
        "done": done,
    }
    if done and done_reason:
        chunk["done_reason"] = done_reason
    if done and prompt_eval_count is not None:
        chunk["prompt_eval_count"] = prompt_eval_count
    if done and eval_count is not None:
        chunk["eval_count"] = eval_count
    return json.dumps(chunk)


def _stream_cm(lines: list[str]) -> MagicMock:
    """Return a mock for `async with client.stream(...) as response`.

    The response has status_code=200 and aiter_lines() yields the given lines.
    """
    async def _aiter():
        for line in lines:
            yield line

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.aiter_lines = MagicMock(return_value=_aiter())

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_response)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


def _error_stream_cm(status_code: int, body: bytes) -> MagicMock:
    """Return a mock that simulates a non-200 upstream response."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.aread = AsyncMock(return_value=body)

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_response)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


def _connect_error_cm(exc: Exception) -> MagicMock:
    """Return a mock whose __aenter__ raises the given exception (simulates connect failure)."""
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(side_effect=exc)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


def _make_client(
    connect_retries: int = 3,
    connect_timeout: float = 1.0,
    read_timeout: float = 5.0,
) -> LlamaCppClient:
    return LlamaCppClient(
        base_url="http://fake-ollama:11435",
        model="gemma4:26b",
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        connect_retries=connect_retries,
    )


async def _collect(client: LlamaCppClient, msg: str = "hi") -> list:
    chunks = []
    async for chunk in client.stream_chat([ChatMessage(role="user", content=msg)]):
        chunks.append(chunk)
    return chunks


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_yields_chunks_on_success():
    """Successful stream returns ChatChunk objects with content."""
    lines = [
        _make_ndjson_line("Hello"),
        _make_ndjson_line(" world"),
        _make_ndjson_line(done=True, done_reason="stop", prompt_eval_count=3, eval_count=2),
    ]

    mock_httpx_client = MagicMock()
    mock_httpx_client.stream = MagicMock(return_value=_stream_cm(lines))
    mock_httpx_client.__aenter__ = AsyncMock(return_value=mock_httpx_client)
    mock_httpx_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_httpx_client):
        chunks = await _collect(_make_client())

    content = "".join(c.content for c in chunks)
    assert "Hello" in content
    assert "world" in content
    # Last chunk carries token counts
    last = chunks[-1]
    assert last.prompt_tokens == 3
    assert last.completion_tokens == 2


# ---------------------------------------------------------------------------
# Retry on connect errors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connect_error_exhausts_retries_and_raises_friendly_message():
    """ConnectError on every attempt → LLMProviderError with actionable message."""
    client = _make_client(connect_retries=3)
    exc = httpx.ConnectError("Connection refused")

    mock_httpx_client = MagicMock()
    mock_httpx_client.stream = MagicMock(return_value=_connect_error_cm(exc))
    mock_httpx_client.__aenter__ = AsyncMock(return_value=mock_httpx_client)
    mock_httpx_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_httpx_client):
        with patch("asyncio.sleep", new_callable=AsyncMock):  # don't actually wait
            with pytest.raises(LLMProviderError) as exc_info:
                await _collect(client)

    assert "reachable" in str(exc_info.value).lower()
    assert "http://fake-ollama:11435" in str(exc_info.value)


@pytest.mark.asyncio
async def test_connect_error_retries_correct_number_of_times():
    """Client attempts exactly connect_retries times before giving up."""
    retries = 4
    client = _make_client(connect_retries=retries)
    exc = httpx.ConnectError("Connection refused")

    mock_httpx_client = MagicMock()
    mock_httpx_client.stream = MagicMock(return_value=_connect_error_cm(exc))
    mock_httpx_client.__aenter__ = AsyncMock(return_value=mock_httpx_client)
    mock_httpx_client.__aexit__ = AsyncMock(return_value=None)

    sleep_calls = []

    async def fake_sleep(n: float) -> None:
        sleep_calls.append(n)

    with patch("httpx.AsyncClient", return_value=mock_httpx_client):
        with patch("asyncio.sleep", side_effect=fake_sleep):
            with pytest.raises(LLMProviderError):
                await _collect(client)

    # stream() called exactly `retries` times
    assert mock_httpx_client.stream.call_count == retries
    # sleep called retries-1 times (no sleep after the last attempt)
    assert len(sleep_calls) == retries - 1


@pytest.mark.asyncio
async def test_retry_recovers_after_one_connect_failure():
    """First attempt fails with ConnectError; second succeeds — chunks are returned."""
    lines = [
        _make_ndjson_line("ok", done=True, done_reason="stop"),
    ]
    success_cm = _stream_cm(lines)
    fail_cm = _connect_error_cm(httpx.ConnectError("transient"))

    call_count = 0

    def _side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return fail_cm if call_count == 1 else success_cm

    mock_httpx_client = MagicMock()
    mock_httpx_client.stream = MagicMock(side_effect=_side_effect)
    mock_httpx_client.__aenter__ = AsyncMock(return_value=mock_httpx_client)
    mock_httpx_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_httpx_client):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            chunks = await _collect(_make_client(connect_retries=3))

    assert any(c.content == "ok" for c in chunks)
    assert mock_httpx_client.stream.call_count == 2


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_404_model_not_found_raises_friendly_message():
    """Upstream 404 'model not found' → model-not-available error message."""
    body = b'{"error":"model \'gemma4:26b\' not found, try pulling it first"}'

    mock_httpx_client = MagicMock()
    mock_httpx_client.stream = MagicMock(return_value=_error_stream_cm(404, body))
    mock_httpx_client.__aenter__ = AsyncMock(return_value=mock_httpx_client)
    mock_httpx_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_httpx_client):
        with pytest.raises(LLMProviderError) as exc_info:
            await _collect(_make_client())

    msg = str(exc_info.value)
    assert "gemma4:26b" in msg
    assert "not available" in msg.lower()


@pytest.mark.asyncio
async def test_non_200_non_404_raises_status_message():
    """Generic non-200 response includes the HTTP status code."""
    body = b'{"error":"internal server error"}'

    mock_httpx_client = MagicMock()
    mock_httpx_client.stream = MagicMock(return_value=_error_stream_cm(500, body))
    mock_httpx_client.__aenter__ = AsyncMock(return_value=mock_httpx_client)
    mock_httpx_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_httpx_client):
        with pytest.raises(LLMProviderError) as exc_info:
            await _collect(_make_client())

    assert "500" in str(exc_info.value)


@pytest.mark.asyncio
async def test_read_timeout_raises_friendly_message():
    """ReadTimeout during streaming → timeout error message (not retried)."""
    mock_response = MagicMock()
    mock_response.status_code = 200

    async def _slow_aiter():
        yield _make_ndjson_line("partial")
        raise httpx.ReadTimeout("read timed out")

    mock_response.aiter_lines = MagicMock(return_value=_slow_aiter())

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_response)
    cm.__aexit__ = AsyncMock(return_value=None)

    mock_httpx_client = MagicMock()
    mock_httpx_client.stream = MagicMock(return_value=cm)
    mock_httpx_client.__aenter__ = AsyncMock(return_value=mock_httpx_client)
    mock_httpx_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_httpx_client):
        with pytest.raises(LLMProviderError) as exc_info:
            await _collect(_make_client(connect_retries=3))

    assert "timed out" in str(exc_info.value).lower()
    # ReadTimeout is NOT retried — stream() should only have been called once
    assert mock_httpx_client.stream.call_count == 1


@pytest.mark.asyncio
async def test_stream_skips_malformed_json_lines():
    """Lines that are not valid JSON are silently skipped."""
    lines = ["not-json-at-all", "{also-bad"]

    mock_httpx_client = MagicMock()
    mock_httpx_client.stream = MagicMock(return_value=_stream_cm(lines))
    mock_httpx_client.__aenter__ = AsyncMock(return_value=mock_httpx_client)
    mock_httpx_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_httpx_client):
        chunks = await _collect(_make_client())

    assert chunks == []


# ---------------------------------------------------------------------------
# G-A1/G-A2: GenerationTuning -> Ollama's options{} nesting
# ---------------------------------------------------------------------------

def _capturing_client(lines: list[str]) -> tuple[MagicMock, dict]:
    captured: dict = {}

    def _capture_stream(method, url, **kwargs):
        captured.update(kwargs)
        return _stream_cm(lines)

    mock_httpx_client = MagicMock()
    mock_httpx_client.stream = MagicMock(side_effect=_capture_stream)
    mock_httpx_client.__aenter__ = AsyncMock(return_value=mock_httpx_client)
    mock_httpx_client.__aexit__ = AsyncMock(return_value=None)
    return mock_httpx_client, captured


def test_supports_reasoning_defaults_false():
    """Most Ollama-served models have no 'think' mode — the flag must default
    off, not on (a wrong-by-default True would 400 on unsupported models)."""
    client = _make_client()
    assert client.supports_reasoning is False


@pytest.mark.asyncio
async def test_temperature_nested_under_options_not_top_level():
    """Regression test for the pre-G-A1 bug: temperature was sent top-level,
    where Ollama's /api/chat silently ignores it — it belongs under "options"."""
    lines = [_make_ndjson_line("ok", done=True)]
    mock_httpx_client, captured = _capturing_client(lines)

    with patch("httpx.AsyncClient", return_value=mock_httpx_client):
        client = _make_client()
        async for _ in client.stream_chat(
            [ChatMessage(role="user", content="hi")],
            tuning=GenerationTuning(temperature=0.3),
        ):
            pass

    payload = captured["json"]
    assert "temperature" not in payload
    assert payload["options"]["temperature"] == 0.3


@pytest.mark.asyncio
async def test_caller_supplied_options_survive_merge_with_tuning():
    """skill_selector.py's explicit options={"num_predict": 200} must not be
    clobbered by tuning-derived options — caller's explicit choice wins."""
    lines = [_make_ndjson_line("ok", done=True)]
    mock_httpx_client, captured = _capturing_client(lines)

    with patch("httpx.AsyncClient", return_value=mock_httpx_client):
        client = _make_client()
        async for _ in client.stream_chat(
            [ChatMessage(role="user", content="hi")],
            tuning=GenerationTuning(temperature=0.9),
            options={"num_predict": 200},
        ):
            pass

    payload = captured["json"]
    assert payload["options"]["num_predict"] == 200
    assert payload["options"]["temperature"] == 0.9


@pytest.mark.asyncio
async def test_reasoning_sets_think_flag_only_when_client_supports_it():
    lines = [_make_ndjson_line("ok", done=True)]
    mock_httpx_client, captured = _capturing_client(lines)

    with patch("httpx.AsyncClient", return_value=mock_httpx_client):
        client = LlamaCppClient(
            base_url="http://fake-ollama:11435",
            model="qwen3-reasoning",
            supports_reasoning=True,
        )
        assert client.supports_reasoning is True
        async for _ in client.stream_chat(
            [ChatMessage(role="user", content="hi")],
            tuning=GenerationTuning(mode=ResponseMode.THINKING),
        ):
            pass

    payload = captured["json"]
    assert payload["think"] is True
    assert payload["options"]["num_predict"] == 1024  # THINKING's default level: MEDIUM


@pytest.mark.asyncio
async def test_reasoning_ignored_when_client_does_not_support_it():
    lines = [_make_ndjson_line("ok", done=True)]
    mock_httpx_client, captured = _capturing_client(lines)

    with patch("httpx.AsyncClient", return_value=mock_httpx_client):
        client = _make_client()  # supports_reasoning defaults False
        async for _ in client.stream_chat(
            [ChatMessage(role="user", content="hi")],
            tuning=GenerationTuning(mode=ResponseMode.THINKING),
        ):
            pass

    payload = captured["json"]
    assert "think" not in payload


# ---------------------------------------------------------------------------
# LLMClient.ping default + LlamaCppClient.ping
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_base_llmclient_ping_default_returns_true():
    """Base LLMClient.ping() returns True (external providers are 'always up')."""

    class _Stub(LLMClient):
        async def stream_chat(self, messages, **opts):
            return
            yield  # make it a generator

    stub = _Stub()
    result = await stub.ping()
    assert result is True


@pytest.mark.asyncio
async def test_llamacpp_ping_returns_true_when_reachable():
    """LlamaCppClient.ping() returns True when the server responds 200."""
    mock_response = MagicMock()
    mock_response.status_code = 200

    mock_httpx_client = MagicMock()
    mock_httpx_client.get = AsyncMock(return_value=mock_response)
    mock_httpx_client.__aenter__ = AsyncMock(return_value=mock_httpx_client)
    mock_httpx_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_httpx_client):
        result = await _make_client().ping()

    assert result is True


@pytest.mark.asyncio
async def test_llamacpp_ping_returns_false_when_unreachable():
    """LlamaCppClient.ping() returns False on connection error."""
    mock_httpx_client = MagicMock()
    mock_httpx_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
    mock_httpx_client.__aenter__ = AsyncMock(return_value=mock_httpx_client)
    mock_httpx_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_httpx_client):
        result = await _make_client().ping()

    assert result is False
