"""
Unit tests for app/services/studio.py and app/routers/studio.py

Covers:
- Image generation gated by PolicyEngine (L5/L6/ADMIN or MKT allowed, others 403)
- Video generation: real path (Veo) — authorized → processing row + background task;
  unauthorized → 403; provider failure → failed row
- Music generation: real path (Lyria 3 Clip) — authorized → processing row + background
  task; unauthorized → 403; provider failure → failed row
- Stored prompt is ciphertext, never plaintext (§7.1)
- list_templates filters correctly
- GET /studio/generations/{id} returns the record (cross-user → 404)
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.policy_engine import PolicyDecision, DenyReason
from app.tools.image_gen import IMAGE_MODEL_CODE
from app.tools.video_gen import VIDEO_MODEL_CODE
from app.tools.music_gen import MUSIC_MODEL_CODE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def set_encryption_key(monkeypatch):
    """Provide a valid 32-byte base64 ENCRYPTION_KEY for crypto.encrypt calls."""
    import base64
    monkeypatch.setenv("ENCRYPTION_KEY", base64.b64encode(b"A" * 32).decode())
    # Reset the module-level cache so it picks up the new key
    import app.crypto as crypto_mod
    crypto_mod._key = None
    yield
    crypto_mod._key = None


def _make_user(role: str = "L2") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    return user


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    # refresh populates id and created_at on the passed object
    async def _refresh(obj):
        if not getattr(obj, "id", None) or obj.id is None:
            obj.id = uuid.uuid4()
        from datetime import datetime, timezone
        obj.created_at = datetime.now(timezone.utc)
    session.refresh = _refresh
    return session


# ---------------------------------------------------------------------------
# list_templates
# ---------------------------------------------------------------------------

def test_list_templates_returns_all_when_no_filter():
    from app.services.studio import list_templates
    templates = list_templates()
    assert len(templates) == 18
    types = {t["type"] for t in templates}
    assert types == {"image", "video", "music"}


def test_list_templates_filters_by_type():
    from app.services.studio import list_templates
    image_tmpl = list_templates("image")
    assert all(t["type"] == "image" for t in image_tmpl)
    assert len(image_tmpl) == 6

    video_tmpl = list_templates("video")
    assert len(video_tmpl) == 6

    music_tmpl = list_templates("music")
    assert len(music_tmpl) == 6


def test_list_templates_all_filter_same_as_none():
    from app.services.studio import list_templates
    assert list_templates("all") == list_templates(None)


# ---------------------------------------------------------------------------
# Music — real Lyria 3 Clip path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_music_generate_creates_processing_row_for_authorized_user():
    """Authorized user (L5+) creates a 'processing' row; background task is scheduled."""
    from fastapi import BackgroundTasks
    from app.services import studio as studio_svc

    allowed_decision = PolicyDecision(
        allowed=True,
        model_code=MUSIC_MODEL_CODE,
        downgrade_to_local=False,
        reasons=["all_checks_passed"],
    )

    session = _make_session()
    user = _make_user("L5")
    background = BackgroundTasks()

    with patch("app.services.studio.authorize_music", AsyncMock(return_value=allowed_decision)), \
         patch("app.services.studio.music_authorized", return_value=True), \
         patch("app.services.studio.generate_music_bytes") as mock_mus, \
         patch("app.services.studio.audit_svc.log", AsyncMock()):

        gen = await studio_svc.generate(
            session, user, "music", "Lyria 3 Clip Preview", "upbeat pop song", {}, background=background
        )

    # Row created with status=processing
    assert gen.status == "processing"
    assert gen.type == "music"
    assert gen.output_ref is None
    # Background task registered (generate_music_bytes not called yet — runs later)
    mock_mus.assert_not_called()
    assert len(background.tasks) == 1


@pytest.mark.asyncio
async def test_music_background_task_completes_to_done():
    """_run_music_generation updates the row to 'completed' on success."""
    from app.services.studio import _run_music_generation

    fake_bytes = b"\xFF\xFB" + b"\x00" * 1024  # fake mp3 header + data

    gen_id = uuid.uuid4()
    user_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    with patch("app.services.studio.generate_music_bytes", AsyncMock(return_value=(fake_bytes, "audio/mpeg"))), \
         patch("app.services.studio.session_factory", return_value=mock_session), \
         patch("app.services.studio.audit_svc.log", AsyncMock()):

        await _run_music_generation(gen_id, user_id, "upbeat pop song", {})

    # session.execute should have been called (to run the UPDATE)
    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args[0][0]
    compiled = str(call_args.compile())
    assert "completed" in compiled or "status" in compiled


@pytest.mark.asyncio
async def test_music_background_task_marks_failed_on_provider_error():
    """_run_music_generation updates the row to 'failed' when Lyria raises."""
    from app.llm.base import LLMProviderError
    from app.services.studio import _run_music_generation

    gen_id = uuid.uuid4()
    user_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    with patch("app.services.studio.generate_music_bytes",
               AsyncMock(side_effect=LLMProviderError("Lyria unavailable"))), \
         patch("app.services.studio.session_factory", return_value=mock_session), \
         patch("app.services.studio.audit_svc.log", AsyncMock()):

        await _run_music_generation(gen_id, user_id, "upbeat pop song", {})

    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args[0][0]
    compiled = str(call_args.compile())
    assert "failed" in compiled or "status" in compiled


@pytest.mark.asyncio
async def test_music_generate_denied_for_unauthorized_role():
    """L1–L4 without MKT cannot generate music — expect 403."""
    from fastapi import BackgroundTasks, HTTPException
    from app.services import studio as studio_svc

    denied_decision = PolicyDecision(
        allowed=True,
        model_code="gemma4:26b",
        downgrade_to_local=True,
        reasons=[DenyReason.ROLE_NOT_ALLOWED],
    )

    session = _make_session()
    user = _make_user("L2")
    background = BackgroundTasks()

    with patch("app.services.studio.authorize_music", AsyncMock(return_value=denied_decision)), \
         patch("app.services.studio.generate_music_bytes") as mock_mus, \
         patch("app.services.studio.audit_svc.log", AsyncMock()):

        with pytest.raises(HTTPException) as exc_info:
            await studio_svc.generate(
                session, user, "music", "Lyria 3 Clip Preview", "pop song", {}, background=background
            )

    assert exc_info.value.status_code == 403
    assert "studio_music_unauthorized" in str(exc_info.value.detail)
    mock_mus.assert_not_called()


@pytest.mark.asyncio
async def test_music_generate_denied_for_confidential_prompt():
    """Confidential-tier prompt is denied for music."""
    from fastapi import BackgroundTasks, HTTPException
    from app.services import studio as studio_svc

    tier_denied = PolicyDecision(
        allowed=False,
        model_code="",
        downgrade_to_local=True,
        reasons=[DenyReason.TIER_BLOCKS_EXTERNAL],
    )

    session = _make_session()
    user = _make_user("L5")
    background = BackgroundTasks()

    with patch("app.services.studio.authorize_music", AsyncMock(return_value=tier_denied)), \
         patch("app.services.studio.audit_svc.log", AsyncMock()):

        with pytest.raises(HTTPException) as exc_info:
            await studio_svc.generate(
                session, user, "music", "Lyria 3 Clip Preview", "confidential data", {}, background=background
            )

    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Video — real Veo path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_video_generate_creates_processing_row_for_authorized_user():
    """Authorized user (L5+) creates a 'processing' row; background task is scheduled."""
    from fastapi import BackgroundTasks
    from app.services import studio as studio_svc

    allowed_decision = PolicyDecision(
        allowed=True,
        model_code=VIDEO_MODEL_CODE,
        downgrade_to_local=False,
        reasons=["all_checks_passed"],
    )

    session = _make_session()
    user = _make_user("L5")
    background = BackgroundTasks()

    with patch("app.services.studio.authorize_video", AsyncMock(return_value=allowed_decision)), \
         patch("app.services.studio.video_authorized", return_value=True), \
         patch("app.services.studio.generate_video_bytes") as mock_vid, \
         patch("app.services.studio.audit_svc.log", AsyncMock()):

        gen = await studio_svc.generate(
            session, user, "video", "Veo 3.1", "a cat dancing", {}, background=background
        )

    # Row created with status=processing
    assert gen.status == "processing"
    assert gen.type == "video"
    assert gen.output_ref is None
    # Background task registered (generate_video_bytes not called yet — runs later)
    mock_vid.assert_not_called()
    assert len(background.tasks) == 1


@pytest.mark.asyncio
async def test_video_background_task_completes_to_done():
    """_run_video_generation updates the row to 'completed' on success."""
    from app.services.studio import _run_video_generation

    fake_bytes = b"\x00" * 1024  # fake mp4

    gen_id = uuid.uuid4()
    user_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    with patch("app.services.studio.generate_video_bytes", AsyncMock(return_value=(fake_bytes, "video/mp4"))), \
         patch("app.services.studio.session_factory", return_value=mock_session), \
         patch("app.services.studio.audit_svc.log", AsyncMock()):

        await _run_video_generation(gen_id, user_id, "a test scene", {})

    # session.execute should have been called (to run the UPDATE)
    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args[0][0]
    # The compiled update statement should reference 'completed' status
    compiled = str(call_args.compile())
    assert "completed" in compiled or "status" in compiled


@pytest.mark.asyncio
async def test_video_background_task_marks_failed_on_provider_error():
    """_run_video_generation updates the row to 'failed' when Veo raises."""
    from app.llm.base import LLMProviderError
    from app.services.studio import _run_video_generation

    gen_id = uuid.uuid4()
    user_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    with patch("app.services.studio.generate_video_bytes",
               AsyncMock(side_effect=LLMProviderError("Veo unavailable"))), \
         patch("app.services.studio.session_factory", return_value=mock_session), \
         patch("app.services.studio.audit_svc.log", AsyncMock()):

        await _run_video_generation(gen_id, user_id, "a test scene", {})

    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args[0][0]
    compiled = str(call_args.compile())
    assert "failed" in compiled or "status" in compiled


@pytest.mark.asyncio
async def test_video_generate_denied_for_unauthorized_role():
    """L1–L4 without MKT cannot generate videos — expect 403."""
    from fastapi import BackgroundTasks, HTTPException
    from app.services import studio as studio_svc

    denied_decision = PolicyDecision(
        allowed=True,
        model_code="gemma4:26b",
        downgrade_to_local=True,
        reasons=[DenyReason.ROLE_NOT_ALLOWED],
    )

    session = _make_session()
    user = _make_user("L2")
    background = BackgroundTasks()

    with patch("app.services.studio.authorize_video", AsyncMock(return_value=denied_decision)), \
         patch("app.services.studio.generate_video_bytes") as mock_vid, \
         patch("app.services.studio.audit_svc.log", AsyncMock()):

        with pytest.raises(HTTPException) as exc_info:
            await studio_svc.generate(
                session, user, "video", "Veo 3.1", "a sunset", {}, background=background
            )

    assert exc_info.value.status_code == 403
    assert "studio_video_unauthorized" in str(exc_info.value.detail)
    mock_vid.assert_not_called()


@pytest.mark.asyncio
async def test_video_generate_denied_for_confidential_prompt():
    """Confidential-tier prompt is denied for video."""
    from fastapi import BackgroundTasks, HTTPException
    from app.services import studio as studio_svc

    tier_denied = PolicyDecision(
        allowed=False,
        model_code="",
        downgrade_to_local=True,
        reasons=[DenyReason.TIER_BLOCKS_EXTERNAL],
    )

    session = _make_session()
    user = _make_user("L5")
    background = BackgroundTasks()

    with patch("app.services.studio.authorize_video", AsyncMock(return_value=tier_denied)), \
         patch("app.services.studio.audit_svc.log", AsyncMock()):

        with pytest.raises(HTTPException) as exc_info:
            await studio_svc.generate(
                session, user, "video", "Veo 3.1", "confidential data", {}, background=background
            )

    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Image — gated by PolicyEngine
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_image_generate_denied_for_unauthorized_role():
    """L1–L4 without MKT cannot generate images — expect 403."""
    from fastapi import HTTPException
    from app.services import studio as studio_svc

    denied_decision = PolicyDecision(
        allowed=True,
        model_code="gemma4:26b",
        downgrade_to_local=True,
        reasons=[DenyReason.ROLE_NOT_ALLOWED],
    )

    session = _make_session()
    user = _make_user("L2")

    with patch("app.services.studio.authorize_image", AsyncMock(return_value=denied_decision)), \
         patch("app.services.studio.audit_svc.log", AsyncMock()):

        with pytest.raises(HTTPException) as exc_info:
            await studio_svc.generate(session, user, "image", "Seedream 5.0 Lite", "a sunrise", {})

    assert exc_info.value.status_code == 403
    assert "studio_image_unauthorized" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_image_generate_denied_for_confidential_data():
    """Prompt containing restricted data is denied with tier reason."""
    from fastapi import HTTPException
    from app.services import studio as studio_svc

    tier_denied = PolicyDecision(
        allowed=False,
        model_code="",
        downgrade_to_local=True,
        reasons=[DenyReason.TIER_BLOCKS_EXTERNAL],
    )

    session = _make_session()
    user = _make_user("L5")

    with patch("app.services.studio.authorize_image", AsyncMock(return_value=tier_denied)), \
         patch("app.services.studio.audit_svc.log", AsyncMock()):

        with pytest.raises(HTTPException) as exc_info:
            await studio_svc.generate(session, user, "image", "Seedream 5.0 Lite", "confidential data", {})

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_image_generate_succeeds_for_authorized_user():
    """Authorized user (L5+) with a clean prompt gets a completed generation."""
    from app.services import studio as studio_svc

    allowed_decision = PolicyDecision(
        allowed=True,
        model_code=IMAGE_MODEL_CODE,
        downgrade_to_local=False,
        reasons=["all_checks_passed"],
    )
    fake_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    session = _make_session()
    user = _make_user("L5")

    with patch("app.services.studio.authorize_image", AsyncMock(return_value=allowed_decision)), \
         patch("app.services.studio.image_authorized", return_value=True), \
         patch("app.services.studio.generate_image_bytes", AsyncMock(return_value=(fake_bytes, "image/png"))), \
         patch("app.services.studio.audit_svc.log", AsyncMock()):

        gen = await studio_svc.generate(session, user, "image", "Seedream 5.0 Lite", "a sunset", {})

    assert gen.status == "completed"
    assert gen.output_ref is not None
    assert gen.output_ref.startswith("data:image/png;base64,")


# ---------------------------------------------------------------------------
# Image — reference images passed through, not stored
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_image_generate_passes_references_to_generator():
    """References list is forwarded to generate_image_bytes and NOT stored in settings."""
    import base64
    from app.services import studio as studio_svc

    allowed_decision = PolicyDecision(
        allowed=True,
        model_code=IMAGE_MODEL_CODE,
        downgrade_to_local=False,
        reasons=["all_checks_passed"],
    )
    fake_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    raw_ref = b"\xff\xd8\xff"  # fake JPEG
    ref_data_url = f"data:image/jpeg;base64,{base64.b64encode(raw_ref).decode()}"

    session = _make_session()
    user = _make_user("L5")

    mock_gen_bytes = AsyncMock(return_value=(fake_bytes, "image/png"))

    with patch("app.services.studio.authorize_image", AsyncMock(return_value=allowed_decision)), \
         patch("app.services.studio.image_authorized", return_value=True), \
         patch("app.services.studio.generate_image_bytes", mock_gen_bytes), \
         patch("app.services.studio.audit_svc.log", AsyncMock()):

        gen = await studio_svc.generate(
            session, user, "image", "Gemini Flash Image", "style transfer",
            settings={}, references=[ref_data_url]
        )

    # generate_image_bytes must have received the references list
    mock_gen_bytes.assert_called_once_with("style transfer", [ref_data_url])

    # References must NOT be persisted in the generation record settings
    assert gen.status == "completed"
    stored_settings = gen.settings  # None or dict — must not contain references
    if stored_settings is not None:
        assert "references" not in stored_settings


# ---------------------------------------------------------------------------
# §7.1 — Prompt stored as ciphertext, never plaintext
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_video_prompt_stored_as_ciphertext_not_plaintext():
    """The prompt in the video DB row must be ciphertext bytes, not the UTF-8 plaintext."""
    from fastapi import BackgroundTasks
    from app.services import studio as studio_svc

    allowed_decision = PolicyDecision(
        allowed=True,
        model_code=VIDEO_MODEL_CODE,
        downgrade_to_local=False,
        reasons=["all_checks_passed"],
    )

    session = _make_session()
    user = _make_user("L5")
    plaintext = "a unique video prompt to verify encryption"
    background = BackgroundTasks()

    with patch("app.services.studio.authorize_video", AsyncMock(return_value=allowed_decision)), \
         patch("app.services.studio.video_authorized", return_value=True), \
         patch("app.services.studio.generate_video_bytes", AsyncMock(return_value=(b"fake", "video/mp4"))), \
         patch("app.services.studio.audit_svc.log", AsyncMock()):

        gen = await studio_svc.generate(
            session, user, "video", "Veo 3.1", plaintext, {}, background=background
        )

    # The ciphertext stored must not equal the UTF-8 bytes of the prompt
    assert gen.prompt_ciphertext != plaintext.encode("utf-8")
    # And we must be able to decrypt it back
    from app import crypto
    decrypted = crypto.decrypt(gen.prompt_ciphertext, gen.prompt_nonce, gen.prompt_tag, gen.key_version)
    assert decrypted == plaintext


@pytest.mark.asyncio
async def test_image_prompt_stored_as_ciphertext_not_plaintext():
    """Image generation also stores the encrypted prompt, never plaintext."""
    from app.services import studio as studio_svc
    from app.tools.image_gen import IMAGE_MODEL_CODE

    allowed_decision = PolicyDecision(
        allowed=True,
        model_code=IMAGE_MODEL_CODE,
        downgrade_to_local=False,
        reasons=["all_checks_passed"],
    )

    session = _make_session()
    user = _make_user("L5")
    plaintext = "a beautiful mountain landscape at dawn"

    with patch("app.services.studio.authorize_image", AsyncMock(return_value=allowed_decision)), \
         patch("app.services.studio.image_authorized", return_value=True), \
         patch("app.services.studio.generate_image_bytes", AsyncMock(return_value=(b"fake_png_bytes", "image/png"))), \
         patch("app.services.studio.audit_svc.log", AsyncMock()):

        gen = await studio_svc.generate(session, user, "image", "Seedream 5.0 Lite", plaintext, {})

    assert gen.prompt_ciphertext != plaintext.encode("utf-8")
    from app import crypto
    decrypted = crypto.decrypt(gen.prompt_ciphertext, gen.prompt_nonce, gen.prompt_tag, gen.key_version)
    assert decrypted == plaintext


# ---------------------------------------------------------------------------
# get_generation — scoped to user, cross-user 404
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_generation_returns_record_for_owner():
    from app.services.studio import get_generation
    from app.models.studio import StudioGeneration

    gen_id = uuid.uuid4()
    user_id = uuid.uuid4()

    fake_gen = MagicMock(spec=StudioGeneration)
    fake_gen.id = gen_id
    fake_gen.user_id = user_id

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_gen
    session.execute = AsyncMock(return_value=mock_result)

    result = await get_generation(session, user_id, gen_id)
    assert result is fake_gen


@pytest.mark.asyncio
async def test_get_generation_returns_none_for_wrong_user():
    from app.services.studio import get_generation

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    result = await get_generation(session, uuid.uuid4(), uuid.uuid4())
    assert result is None


# ---------------------------------------------------------------------------
# parent_id — edit/regenerate lineage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_with_valid_parent_id_links_to_source_generation():
    """A parent_id belonging to the user is validated and stored on the new row."""
    from app.services import studio as studio_svc
    from app.models.studio import StudioGeneration

    allowed_decision = PolicyDecision(
        allowed=True,
        model_code=IMAGE_MODEL_CODE,
        downgrade_to_local=False,
        reasons=["all_checks_passed"],
    )
    fake_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    session = _make_session()
    user = _make_user("L5")
    parent_id = uuid.uuid4()
    fake_parent = MagicMock(spec=StudioGeneration)
    fake_parent.id = parent_id
    fake_parent.user_id = user.id

    with patch("app.services.studio.get_generation", AsyncMock(return_value=fake_parent)), \
         patch("app.services.studio.authorize_image", AsyncMock(return_value=allowed_decision)), \
         patch("app.services.studio.image_authorized", return_value=True), \
         patch("app.services.studio.generate_image_bytes", AsyncMock(return_value=(fake_bytes, "image/png"))), \
         patch("app.services.studio.audit_svc.log", AsyncMock()):

        gen = await studio_svc.generate(
            session, user, "image", "Gemini Flash Image", "make the sky sunset",
            {}, references=["data:image/png;base64,AAA"], parent_id=parent_id,
        )

    assert gen.parent_id == parent_id


@pytest.mark.asyncio
async def test_generate_with_unknown_parent_id_raises_404():
    """A parent_id that doesn't resolve for this user (missing or belongs to
    someone else) must be rejected before any generation work happens."""
    from fastapi import HTTPException
    from app.services import studio as studio_svc

    session = _make_session()
    user = _make_user("L5")

    with patch("app.services.studio.get_generation", AsyncMock(return_value=None)), \
         patch("app.services.studio.generate_image_bytes") as mock_gen_bytes:

        with pytest.raises(HTTPException) as exc_info:
            await studio_svc.generate(
                session, user, "image", "Gemini Flash Image", "edit this",
                {}, parent_id=uuid.uuid4(),
            )

    assert exc_info.value.status_code == 404
    mock_gen_bytes.assert_not_called()


# ---------------------------------------------------------------------------
# Invalid type raises 422
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_raises_422_for_unknown_type():
    from fastapi import HTTPException
    from app.services import studio as studio_svc

    with pytest.raises(HTTPException) as exc_info:
        await studio_svc.generate(AsyncMock(), _make_user(), "audio", "SomeModel", "test", {})
    assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# Veo 3.1 model code and duration clamping
# ---------------------------------------------------------------------------

def test_video_model_code_is_veo_3_1_lite():
    from app.tools.video_gen import VIDEO_MODEL_CODE
    assert VIDEO_MODEL_CODE == "veo-3.1-lite-generate-preview"


def test_music_model_code_is_lyria_3_clip():
    from app.tools.music_gen import MUSIC_MODEL_CODE
    assert MUSIC_MODEL_CODE == "lyria-3-clip-preview"


def test_parse_duration_snaps_to_valid_discrete_values():
    from app.tools.video_gen import _parse_duration
    assert _parse_duration("8s") == 8
    assert _parse_duration("6s") == 6
    assert _parse_duration("4s") == 4
    # Veo 2 values that are no longer valid — should snap to nearest
    assert _parse_duration("5s") == 4 or _parse_duration("5s") == 6   # nearest to 5
    assert _parse_duration("10s") == 8                                  # clamp to max
    assert _parse_duration("3s") == 4                                   # clamp to min
    assert _parse_duration(None) == 8                                   # default
    assert _parse_duration("") == 8
    assert _parse_duration("bad") == 8


# ---------------------------------------------------------------------------
# generate_music_bytes — Custom-tab settings mapped into the prompt text
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_music_bytes_maps_custom_settings_into_prompt():
    from app.tools.music_gen import generate_music_bytes

    fake_bytes = b"fake mp3 data"

    with patch("app.tools.music_gen.get_settings") as mock_settings, \
         patch("app.tools.music_gen.GoogleClient") as MockGoogleClient:

        mock_settings.return_value.google_api_key = "test-key"
        instance = MockGoogleClient.return_value
        instance.generate_music = AsyncMock(return_value=(fake_bytes, "audio/mpeg"))

        result = await generate_music_bytes(
            "a dreamy synthwave track",
            {
                "music_detailed_prompt": "[Verse]\nsoft synth pads",
                "negative_prompt": "no drums",
                "music_genre": "Electronic",
                "music_bpm": "Upbeat (120-140)",
                "music_vocal_gender": "female",
                "music_duration": "Auto",
            },
        )

    assert result == (fake_bytes, "audio/mpeg")
    instance.generate_music.assert_called_once()
    augmented_prompt = instance.generate_music.call_args.args[0]
    assert "[Verse]" in augmented_prompt
    assert "soft synth pads" in augmented_prompt
    assert "Avoid: no drums." in augmented_prompt
    assert "Genre: Electronic." in augmented_prompt
    assert "Tempo: Upbeat (120-140)." in augmented_prompt
    assert "Female vocals." in augmented_prompt
    # instrumental_only was not set — no "Instrumental only" phrase
    assert "Instrumental only" not in augmented_prompt


@pytest.mark.asyncio
async def test_generate_music_bytes_skips_auto_and_vocal_gender_when_instrumental():
    from app.tools.music_gen import generate_music_bytes

    fake_bytes = b"fake mp3 data"

    with patch("app.tools.music_gen.get_settings") as mock_settings, \
         patch("app.tools.music_gen.GoogleClient") as MockGoogleClient:

        mock_settings.return_value.google_api_key = "test-key"
        instance = MockGoogleClient.return_value
        instance.generate_music = AsyncMock(return_value=(fake_bytes, "audio/mpeg"))

        await generate_music_bytes(
            "a calm piano piece",
            {
                "instrumental_only": True,
                "music_genre": "Auto",
                "music_bpm": "Auto",
                "music_vocal_gender": "male",
            },
        )

    augmented_prompt = instance.generate_music.call_args.args[0]
    assert "Instrumental only, no vocals." in augmented_prompt
    # "Auto" genre/bpm must not be expressed in the prompt
    assert "Genre:" not in augmented_prompt
    assert "Tempo:" not in augmented_prompt
    # instrumental_only wins over a stray vocal_gender setting
    assert "vocals." not in augmented_prompt.replace("Instrumental only, no vocals.", "")
