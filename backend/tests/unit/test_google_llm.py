"""Unit tests for GoogleClient — all SDK calls are mocked, no real API traffic.

Real-API tests are gated on GOOGLE_API_KEY and marked with @REAL_API.
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import google.genai as _genai
import pytest

from app.llm.base import ChatMessage, LLMProviderError
from app.llm.google import GoogleClient
from app.llm.tuning import GenerationTuning, ReasoningLevel, ResponseMode

REAL_API = pytest.mark.skipif(
    not os.getenv("GOOGLE_API_KEY") or getattr(_genai, "_IS_STUB", False),
    reason="GOOGLE_API_KEY not set or google-genai not installed — skipping real API call",
)


# ---------------------------------------------------------------------------
# Async generator helpers — simulate generate_content_stream
# ---------------------------------------------------------------------------

async def _stream(chunks):
    for c in chunks:
        yield c


async def _await_stream(chunks):
    """Coroutine resolving to an async iterator — matches google-genai .aio.* SDK shape."""
    return _stream(chunks)


def _text_chunk(text: str):
    return SimpleNamespace(
        text=text,
        usage_metadata=None,
        candidates=[],
    )


def _usage_chunk(prompt_tokens: int, completion_tokens: int, finish: str = "STOP"):
    return SimpleNamespace(
        text=None,
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt_tokens,
            candidates_token_count=completion_tokens,
        ),
        candidates=[
            SimpleNamespace(
                finish_reason=SimpleNamespace(value=1, name=finish),
            )
        ],
    )


def _intermediate_chunk(text: str):
    """Chunk with text but no usage / unspecified finish reason."""
    return SimpleNamespace(
        text=text,
        usage_metadata=None,
        candidates=[
            SimpleNamespace(
                finish_reason=SimpleNamespace(value=0, name="FINISH_REASON_UNSPECIFIED"),
            )
        ],
    )


# ---------------------------------------------------------------------------
# Fixture: patch genai.Client
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_sdk():
    with patch("app.llm.google.genai.Client") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


# ---------------------------------------------------------------------------
# Stream shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_yields_text_chunks(mock_sdk):
    chunks = [_text_chunk("Hello"), _text_chunk(" world"), _usage_chunk(10, 5)]
    mock_sdk.aio.models.generate_content_stream = lambda *a, **k: _await_stream(chunks)

    client = GoogleClient(api_key="test-key")
    result = [c async for c in client.stream_chat([ChatMessage(role="user", content="Hi")])]

    text_chunks = [c for c in result if c.content]
    assert len(text_chunks) == 2
    assert text_chunks[0].content == "Hello"
    assert text_chunks[1].content == " world"


@pytest.mark.asyncio
async def test_final_chunk_has_usage(mock_sdk):
    chunks = [_text_chunk("Sure"), _usage_chunk(20, 3)]
    mock_sdk.aio.models.generate_content_stream = lambda *a, **k: _await_stream(chunks)

    client = GoogleClient(api_key="test-key")
    result = [c async for c in client.stream_chat([ChatMessage(role="user", content="Hi")])]

    last = result[-1]
    assert last.prompt_tokens == 20
    assert last.completion_tokens == 3
    assert last.finish_reason == "STOP"
    assert last.model == "gemini-2.5-flash"


@pytest.mark.asyncio
async def test_multiple_chunks_then_usage(mock_sdk):
    chunks = [_text_chunk("a"), _text_chunk("b"), _text_chunk("c"), _usage_chunk(5, 3)]
    mock_sdk.aio.models.generate_content_stream = lambda *a, **k: _await_stream(chunks)

    client = GoogleClient(api_key="test-key")
    result = [c async for c in client.stream_chat([ChatMessage(role="user", content="x")])]

    assert [c.content for c in result] == ["a", "b", "c", ""]
    assert result[-1].prompt_tokens == 5
    assert result[-1].completion_tokens == 3


@pytest.mark.asyncio
async def test_none_text_chunks_are_skipped(mock_sdk):
    """Chunks with text=None or '' must not appear as text deltas."""
    chunks = [_text_chunk("ok"), _usage_chunk(5, 1)]
    # Insert a chunk with no text
    empty = SimpleNamespace(text=None, usage_metadata=None, candidates=[])
    mock_sdk.aio.models.generate_content_stream = lambda *a, **k: _await_stream([empty] + chunks)

    client = GoogleClient(api_key="test-key")
    result = [c async for c in client.stream_chat([ChatMessage(role="user", content="Hi")])]

    text_chunks = [c for c in result if c.content]
    assert len(text_chunks) == 1
    assert text_chunks[0].content == "ok"


@pytest.mark.asyncio
async def test_intermediate_unspecified_finish_reason_ignored(mock_sdk):
    """finish_reason=0 (UNSPECIFIED) on intermediate chunks must not bleed into final."""
    chunks = [_intermediate_chunk("hi"), _usage_chunk(5, 1, finish="STOP")]
    mock_sdk.aio.models.generate_content_stream = lambda *a, **k: _await_stream(chunks)

    client = GoogleClient(api_key="test-key")
    result = [c async for c in client.stream_chat([ChatMessage(role="user", content="x")])]

    assert result[-1].finish_reason == "STOP"


# ---------------------------------------------------------------------------
# Request shape — verify what the adapter sends to the SDK
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_system_message_becomes_system_instruction(mock_sdk):
    """system role must go to GenerateContentConfig.system_instruction, not contents."""
    from app.llm.google import genai_types

    chunks = [_text_chunk("hi"), _usage_chunk(5, 1)]
    captured: dict = {}

    async def _capture_stream(*args, **kwargs):
        captured.update(kwargs)
        return _stream(chunks)

    mock_sdk.aio.models.generate_content_stream = _capture_stream

    client = GoogleClient(api_key="test-key")
    async for _ in client.stream_chat([
        ChatMessage(role="system", content="You are helpful."),
        ChatMessage(role="user", content="Hi"),
    ]):
        pass

    cfg = captured.get("config")
    assert cfg is not None
    assert cfg.system_instruction == "You are helpful."
    # System role must NOT appear in contents
    contents = captured.get("contents", [])
    assert all(c.get("role") != "system" for c in contents)


@pytest.mark.asyncio
async def test_assistant_role_maps_to_model(mock_sdk):
    """ChatMessage role='assistant' must become 'model' in the Gemini contents list."""
    chunks = [_text_chunk("ok"), _usage_chunk(5, 1)]
    captured: dict = {}

    async def _capture(*args, **kwargs):
        captured.update(kwargs)
        return _stream(chunks)

    mock_sdk.aio.models.generate_content_stream = _capture

    client = GoogleClient(api_key="test-key")
    async for _ in client.stream_chat([
        ChatMessage(role="user", content="Hello"),
        ChatMessage(role="assistant", content="Hi there"),
        ChatMessage(role="user", content="Thanks"),
    ]):
        pass

    contents = captured["contents"]
    assert contents[1]["role"] == "model"
    assert contents[1]["parts"][0]["text"] == "Hi there"


@pytest.mark.asyncio
async def test_max_tokens_mapped_to_max_output_tokens(mock_sdk):
    """`max_tokens` kwarg must be forwarded as `max_output_tokens` in the config."""
    chunks = [_text_chunk("x"), _usage_chunk(3, 1)]
    captured: dict = {}

    async def _capture(*args, **kwargs):
        captured.update(kwargs)
        return _stream(chunks)

    mock_sdk.aio.models.generate_content_stream = _capture

    client = GoogleClient(api_key="test-key")
    async for _ in client.stream_chat(
        [ChatMessage(role="user", content="Hi")],
        max_tokens=512,
    ):
        pass

    cfg = captured.get("config")
    assert cfg is not None
    assert cfg.max_output_tokens == 512


@pytest.mark.asyncio
async def test_model_passed_to_sdk(mock_sdk):
    chunks = [_text_chunk("ok"), _usage_chunk(3, 1)]
    captured: dict = {}

    async def _capture(*args, **kwargs):
        captured.update(kwargs)
        return _stream(chunks)

    mock_sdk.aio.models.generate_content_stream = _capture

    client = GoogleClient(api_key="test-key", text_model="gemini-2.5-pro")
    async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
        pass

    assert captured.get("model") == "gemini-2.5-pro"


# ---------------------------------------------------------------------------
# G-A1/G-A2: GenerationTuning -> thinking_config
# ---------------------------------------------------------------------------

def test_supports_reasoning_is_true():
    client = GoogleClient(api_key="test-key")
    assert client.supports_reasoning is True


@pytest.mark.asyncio
async def test_thinking_config_built_for_reasoning_level(mock_sdk):
    from app.llm.google import genai_types

    chunks = [_text_chunk("hi"), _usage_chunk(5, 1)]
    captured: dict = {}

    async def _capture(*args, **kwargs):
        captured.update(kwargs)
        return _stream(chunks)

    mock_sdk.aio.models.generate_content_stream = _capture

    client = GoogleClient(api_key="test-key")
    tuning = GenerationTuning(mode=ResponseMode.THINKING)
    async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")], tuning=tuning):
        pass

    cfg = captured.get("config")
    assert cfg is not None
    assert isinstance(cfg.thinking_config, genai_types.ThinkingConfig)
    assert cfg.thinking_config.thinking_budget == 8192


@pytest.mark.asyncio
async def test_no_reasoning_means_no_thinking_config_and_no_unknown_key(mock_sdk):
    """This is the regression that would have caught the pre-fix bug: Google's
    config is a TYPED object that hard-fails on an unknown key, unlike the
    other adapters' blind dict splats — proving no stray key reaches it."""
    chunks = [_text_chunk("hi"), _usage_chunk(5, 1)]
    captured: dict = {}

    async def _capture(*args, **kwargs):
        captured.update(kwargs)
        return _stream(chunks)

    mock_sdk.aio.models.generate_content_stream = _capture

    client = GoogleClient(api_key="test-key")
    async for _ in client.stream_chat(
        [ChatMessage(role="user", content="Hi")], tuning=GenerationTuning()
    ):
        pass

    # INSTANT + no temperature => config_args stays empty => config is None,
    # exactly like the pre-G-A1 behavior with no opts at all.
    assert captured.get("config") is None


@pytest.mark.asyncio
async def test_temperature_applied_alongside_reasoning(mock_sdk):
    chunks = [_text_chunk("hi"), _usage_chunk(5, 1)]
    captured: dict = {}

    async def _capture(*args, **kwargs):
        captured.update(kwargs)
        return _stream(chunks)

    mock_sdk.aio.models.generate_content_stream = _capture

    client = GoogleClient(api_key="test-key")
    tuning = GenerationTuning(mode=ResponseMode.PRO, reasoning_level=ReasoningLevel.MAX, temperature=0.2)
    async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")], tuning=tuning):
        pass

    cfg = captured["config"]
    assert cfg.temperature == 0.2
    assert cfg.thinking_config.thinking_budget == 24576


# ---------------------------------------------------------------------------
# Image generation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_image_returns_bytes(mock_sdk):
    expected_bytes = b"\x89PNG\r\nfake-image-data"
    mock_response = SimpleNamespace(
        generated_images=[
            SimpleNamespace(
                image=SimpleNamespace(image_bytes=expected_bytes)
            )
        ]
    )
    mock_sdk.models.generate_images = lambda **k: mock_response

    client = GoogleClient(api_key="test-key")
    result = await client.generate_image("A red circle")

    assert result == expected_bytes


@pytest.mark.asyncio
async def test_generate_image_uses_correct_model(mock_sdk):
    call_kwargs: dict = {}
    expected = b"fake"
    mock_response = SimpleNamespace(
        generated_images=[SimpleNamespace(image=SimpleNamespace(image_bytes=expected))]
    )

    def _capture_generate(**kwargs):
        call_kwargs.update(kwargs)
        return mock_response

    mock_sdk.models.generate_images = _capture_generate

    client = GoogleClient(api_key="test-key", image_model="imagen-3.0-fast-generate-001")
    await client.generate_image("A cat")

    assert call_kwargs["model"] == "imagen-3.0-fast-generate-001"
    assert call_kwargs["prompt"] == "A cat"


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_error_maps_to_provider_error(mock_sdk):
    from google.genai import errors as genai_errors

    err = genai_errors.APIError(400, {"message": "Bad request"})

    async def _fail(*args, **kwargs):
        raise err

    mock_sdk.aio.models.generate_content_stream = _fail

    client = GoogleClient(api_key="test-key")
    with pytest.raises(LLMProviderError, match="google 400"):
        async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
            pass


@pytest.mark.asyncio
async def test_connection_error_maps_to_provider_error(mock_sdk):
    async def _fail(*args, **kwargs):
        raise ConnectionError("refused")

    mock_sdk.aio.models.generate_content_stream = _fail

    client = GoogleClient(api_key="test-key")
    with pytest.raises(LLMProviderError, match="google unreachable"):
        async for _ in client.stream_chat([ChatMessage(role="user", content="Hi")]):
            pass


@pytest.mark.asyncio
async def test_generate_image_api_error_maps_to_provider_error(mock_sdk):
    from google.genai import errors as genai_errors

    err = genai_errors.APIError(429, {"message": "Quota exceeded"})

    mock_sdk.models.generate_images = MagicMock(side_effect=err)

    client = GoogleClient(api_key="test-key")
    with pytest.raises(LLMProviderError, match="google 429"):
        await client.generate_image("A dog")


# ---------------------------------------------------------------------------
# Real API smoke tests (skipped unless GOOGLE_API_KEY is set)
# ---------------------------------------------------------------------------

@REAL_API
@pytest.mark.asyncio
async def test_real_text_stream():
    """Confirms streaming works against the live Gemini API."""
    client = GoogleClient(api_key=os.environ["GOOGLE_API_KEY"])
    chunks = [
        c async for c in client.stream_chat(
            [ChatMessage(role="user", content="Reply with exactly the word: hello")],
            max_tokens=20,
        )
    ]
    text = "".join(c.content for c in chunks)
    assert len(text) > 0, "Expected non-empty response"
    last = chunks[-1]
    assert last.finish_reason is not None
    assert last.prompt_tokens is not None and last.prompt_tokens > 0
    assert last.completion_tokens is not None and last.completion_tokens > 0


@REAL_API
@pytest.mark.asyncio
async def test_real_image_generation():
    """Confirms Imagen image generation returns valid bytes.

    NOTE: Imagen requires a billing-enabled Google AI project.
    This test is expected to fail on free-tier accounts with a 403/billing error.
    """
    client = GoogleClient(api_key=os.environ["GOOGLE_API_KEY"])
    img_bytes = await client.generate_image(
        "A simple solid blue square, minimal, no background details"
    )
    assert isinstance(img_bytes, bytes)
    assert len(img_bytes) > 100, "Expected real image data, got suspiciously small bytes"
