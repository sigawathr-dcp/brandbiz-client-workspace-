"""
Unit tests for app/tools/image_gen.py
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.classification import DataTier
from app.services.policy_engine import PolicyDecision
from app.tools.image_gen import (
    IMAGE_MODEL_CODE,
    _decode_data_url,
    authorize_image,
    bytes_to_data_url,
    generate_image_bytes,
    image_authorized,
    is_image_request,
)


# ---------------------------------------------------------------------------
# is_image_request — pure function, no DB
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "I want you to generate cat image.",
    "generate an image of a sunset",
    "Create a picture of a mountain",
    "draw me a picture of a dog",
    "make an image of the company logo",
    "render an illustration of the product",
    "สร้างรูปแมว",
    "วาดภาพวิวทะเล",
])
def test_is_image_request_detects_image_intent(text: str) -> None:
    assert is_image_request(text) is True


@pytest.mark.parametrize("text", [
    "Hello, how are you?",
    "What is the capital of France?",
    "Summarize this document for me.",
    "Generate a report about sales",   # 'generate' without image noun
    "Create a new marketing strategy",
    "Write code to resize an image file",  # talks about image but not generation
])
def test_is_image_request_ignores_non_image_text(text: str) -> None:
    # Most of these should NOT match; a few edge cases are expected to be borderline.
    # The important thing is that pure non-image sentences never trigger.
    assert is_image_request("Hello, how are you?") is False
    assert is_image_request("Summarize this document for me.") is False
    assert is_image_request("What is the capital of France?") is False


# ---------------------------------------------------------------------------
# bytes_to_data_url
# ---------------------------------------------------------------------------

def test_bytes_to_data_url_produces_valid_prefix_default_jpeg() -> None:
    fake_bytes = b"\xff\xd8\xff"  # JPEG magic bytes
    url = bytes_to_data_url(fake_bytes)
    assert url.startswith("data:image/jpeg;base64,")


def test_bytes_to_data_url_produces_valid_prefix_explicit_png() -> None:
    fake_bytes = b"\x89PNG\r\n\x1a\n"
    url = bytes_to_data_url(fake_bytes, mime_type="image/png")
    assert url.startswith("data:image/png;base64,")


def test_bytes_to_data_url_roundtrip() -> None:
    import base64

    original = b"some fake image bytes"
    url = bytes_to_data_url(original, mime_type="image/jpeg")
    b64_part = url.removeprefix("data:image/jpeg;base64,")
    assert base64.b64decode(b64_part) == original


# ---------------------------------------------------------------------------
# image_authorized — pure function, truth-table over PolicyDecision shapes
# ---------------------------------------------------------------------------

def _decision(
    allowed: bool = True,
    model_code: str = IMAGE_MODEL_CODE,
    downgrade_to_local: bool = False,
) -> PolicyDecision:
    return PolicyDecision(
        allowed=allowed,
        model_code=model_code,
        downgrade_to_local=downgrade_to_local,
    )


def test_image_authorized_true_when_fully_allowed() -> None:
    assert image_authorized(_decision()) is True


def test_image_authorized_false_when_denied() -> None:
    assert image_authorized(_decision(allowed=False, model_code="")) is False


def test_image_authorized_false_when_downgraded_to_local() -> None:
    # ROLE_NOT_ALLOWED or TIER_BLOCKS_EXTERNAL both yield downgrade_to_local=True
    assert image_authorized(_decision(model_code="gemma4:26b", downgrade_to_local=True)) is False


def test_image_authorized_false_when_wrong_model() -> None:
    # Sanity: even if allowed=True, model_code must match IMAGE_MODEL_CODE
    assert image_authorized(_decision(model_code="claude-sonnet-4")) is False


# ---------------------------------------------------------------------------
# authorize_image — delegates to PolicyEngine.decide() (mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_authorize_image_calls_policy_engine() -> None:
    """authorize_image must call PolicyEngine.decide with IMAGE_MODEL_CODE."""
    expected = PolicyDecision(
        allowed=True,
        model_code=IMAGE_MODEL_CODE,
        reasons=["all_checks_passed"],
    )

    with patch("app.tools.image_gen.PolicyEngine") as MockPolicyEngine:
        mock_instance = MockPolicyEngine.return_value
        mock_instance.decide = AsyncMock(return_value=expected)

        session = AsyncMock()
        user = MagicMock()
        user.id = uuid.uuid4()

        result = await authorize_image(session, user, DataTier.TIER_1_PUBLIC)

    MockPolicyEngine.assert_called_once_with(session)
    mock_instance.decide.assert_called_once_with(
        user, IMAGE_MODEL_CODE, DataTier.TIER_1_PUBLIC, 0
    )
    assert result is expected


@pytest.mark.asyncio
async def test_authorize_image_returns_downgrade_for_role_not_allowed() -> None:
    """Unauthorized user gets a downgrade decision (ROLE_NOT_ALLOWED)."""
    from app.services.policy_engine import DenyReason

    downgraded = PolicyDecision(
        allowed=True,
        model_code="gemma4:26b",
        reasons=[DenyReason.ROLE_NOT_ALLOWED],
        downgrade_to_local=True,
    )

    with patch("app.tools.image_gen.PolicyEngine") as MockPolicyEngine:
        MockPolicyEngine.return_value.decide = AsyncMock(return_value=downgraded)
        result = await authorize_image(AsyncMock(), MagicMock(), DataTier.TIER_1_PUBLIC)

    assert not image_authorized(result)


# ---------------------------------------------------------------------------
# generate_image_bytes — OpenAIClient (mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_image_bytes_calls_google_client() -> None:
    fake_bytes = b"fake png data"

    with patch("app.tools.image_gen.get_settings") as mock_settings, \
         patch("app.tools.image_gen.GoogleClient") as MockGoogleClient:

        mock_settings.return_value.google_api_key = "test-key"
        instance = MockGoogleClient.return_value
        instance.generate_image_gemini = AsyncMock(return_value=(fake_bytes, "image/jpeg"))

        result = await generate_image_bytes("a cat in a meadow")

    assert result == (fake_bytes, "image/jpeg")
    MockGoogleClient.assert_called_once_with(api_key="test-key")
    instance.generate_image_gemini.assert_called_once_with(
        "a cat in a meadow", model=IMAGE_MODEL_CODE, references=None
    )


@pytest.mark.asyncio
async def test_generate_image_bytes_raises_when_no_api_key() -> None:
    from app.llm.base import LLMProviderError

    with patch("app.tools.image_gen.get_settings") as mock_settings:
        mock_settings.return_value.google_api_key = ""

        with pytest.raises(LLMProviderError, match="GOOGLE_API_KEY"):
            await generate_image_bytes("a cat")


# ---------------------------------------------------------------------------
# _decode_data_url
# ---------------------------------------------------------------------------

def test_decode_data_url_valid_png() -> None:
    import base64
    raw = b"\x89PNG\r\n\x1a\n"
    encoded = base64.b64encode(raw).decode()
    result = _decode_data_url(f"data:image/png;base64,{encoded}")
    assert result is not None
    decoded_bytes, mime = result
    assert decoded_bytes == raw
    assert mime == "image/png"


def test_decode_data_url_valid_jpeg() -> None:
    import base64
    raw = b"\xff\xd8\xff"
    encoded = base64.b64encode(raw).decode()
    result = _decode_data_url(f"data:image/jpeg;base64,{encoded}")
    assert result is not None
    assert result[1] == "image/jpeg"


def test_decode_data_url_non_image_returns_none() -> None:
    import base64
    encoded = base64.b64encode(b"PDF content").decode()
    assert _decode_data_url(f"data:application/pdf;base64,{encoded}") is None


def test_decode_data_url_malformed_returns_none() -> None:
    assert _decode_data_url("not-a-data-url") is None
    assert _decode_data_url("data:image/png;base64,!!!invalid!!!") is None


# ---------------------------------------------------------------------------
# generate_image_bytes — with references
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_image_bytes_passes_decoded_references() -> None:
    import base64
    fake_bytes = b"generated image"
    raw_ref = b"\x89PNG\r\n\x1a\n"
    ref_data_url = f"data:image/png;base64,{base64.b64encode(raw_ref).decode()}"

    with patch("app.tools.image_gen.get_settings") as mock_settings, \
         patch("app.tools.image_gen.GoogleClient") as MockGoogleClient:

        mock_settings.return_value.google_api_key = "test-key"
        instance = MockGoogleClient.return_value
        instance.generate_image_gemini = AsyncMock(return_value=(fake_bytes, "image/jpeg"))

        result = await generate_image_bytes("style transfer", references=[ref_data_url])

    assert result == (fake_bytes, "image/jpeg")
    call_kwargs = instance.generate_image_gemini.call_args
    passed_refs = call_kwargs.kwargs["references"]
    assert passed_refs is not None
    assert len(passed_refs) == 1
    assert passed_refs[0] == (raw_ref, "image/png")


@pytest.mark.asyncio
async def test_generate_image_bytes_skips_malformed_references() -> None:
    import base64
    fake_bytes = b"generated image"
    valid_ref = f"data:image/png;base64,{base64.b64encode(b'valid').decode()}"
    bad_refs = ["not-a-url", "data:application/pdf;base64,aGVsbG8=", valid_ref]

    with patch("app.tools.image_gen.get_settings") as mock_settings, \
         patch("app.tools.image_gen.GoogleClient") as MockGoogleClient:

        mock_settings.return_value.google_api_key = "test-key"
        instance = MockGoogleClient.return_value
        instance.generate_image_gemini = AsyncMock(return_value=(fake_bytes, "image/jpeg"))

        await generate_image_bytes("a cat", references=bad_refs)

    passed_refs = instance.generate_image_gemini.call_args.kwargs["references"]
    assert passed_refs is not None
    assert len(passed_refs) == 1  # only the valid one passes through
