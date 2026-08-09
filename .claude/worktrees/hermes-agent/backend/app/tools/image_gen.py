"""
app/tools/image_gen.py

Image generation tool — authorization helpers and Gemini gemini-3.1-flash-image integration.

Exported helpers used by both the orchestrator node and the /image REST endpoint.
Authorization is always delegated to PolicyEngine.decide() — never bypassed.
"""
from __future__ import annotations

import base64
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.llm.base import LLMProviderError
from app.llm.google import GoogleClient
from app.models.classification import DataTier
from app.models.user import User
from app.services.policy_engine import PolicyDecision, PolicyEngine

# Matches English and Thai image-generation phrasing.
# Pattern 1: English action verbs followed by image nouns (ASCII word boundaries only).
# Pattern 2: Thai action verbs (create/draw/make/request/want/show) → image nouns.
#   Note: \b does not work before Thai Unicode chars, so no word boundary is used here.
_IMAGE_RE = re.compile(
    r"(generate|create|make|draw|render|show\s+me)\b.{0,50}\b"
    r"(image|picture|photo|illustration|artwork|art)"
    r"|"
    r"(สร้าง|วาด|ทำ|ขอ|อยากได้|อยากเห็น|เอา|แสดง|หา|ส่ง|ให้ดู).{0,30}(รูป|ภาพ)"
    r"|"
    r"(รูป|ภาพ).{0,30}(สร้าง|วาด|ทำ|ให้|หน่อย|ด้วย)",
    re.IGNORECASE,
)

# Catalog code for the image model — must match model_catalog.code.
IMAGE_MODEL_CODE = "gemini-3.1-flash-image"


def is_image_request(text: str) -> bool:
    """Return True if the message looks like an image-generation request."""
    return bool(_IMAGE_RE.search(text))


async def authorize_image(
    session: AsyncSession,
    user: User,
    tier: DataTier,
) -> PolicyDecision:
    """Run PolicyEngine.decide() for IMAGE_MODEL_CODE.

    Callers must check image_authorized(decision) on the result before proceeding.
    Passes estimated_input_tokens=0 — image generation is not token-quota-gated.
    """
    return await PolicyEngine(session).decide(user, IMAGE_MODEL_CODE, tier, 0)


def image_authorized(decision: PolicyDecision) -> bool:
    """Return True only when PolicyEngine granted the image model without downgrade.

    A downgrade to local (ROLE_NOT_ALLOWED or TIER_BLOCKS_EXTERNAL) means the
    external image API must not be called — local LLMs cannot generate images.
    """
    return (
        decision.allowed
        and not decision.downgrade_to_local
        and decision.model_code == IMAGE_MODEL_CODE
    )


def _decode_data_url(data_url: str) -> tuple[bytes, str] | None:
    """Parse a data URL into (raw_bytes, mime_type). Returns None if malformed or non-image."""
    try:
        if not data_url.startswith("data:image/"):
            return None
        header, _, payload = data_url.partition(",")
        if not payload or ";base64" not in header:
            return None
        mime_type = header.removeprefix("data:").replace(";base64", "")
        return base64.b64decode(payload), mime_type
    except Exception:
        return None


async def generate_image_bytes(
    prompt: str,
    references: list[str] | None = None,
) -> tuple[bytes, str]:
    """Call gemini-3.1-flash-image and return (raw_bytes, mime_type).

    Authorization must be checked BEFORE calling this function via
    authorize_image() + image_authorized().

    ``references`` is an optional list of image data URLs (``data:image/*;base64,...``)
    that are passed to the model as visual references to guide generation.
    Malformed or non-image data URLs are silently skipped.
    """
    cfg = get_settings()
    if not cfg.google_api_key:
        raise LLMProviderError("GOOGLE_API_KEY is not configured — image generation unavailable")

    decoded: list[tuple[bytes, str]] = []
    for ref in references or []:
        result = _decode_data_url(ref)
        if result is not None:
            decoded.append(result)

    client = GoogleClient(api_key=cfg.google_api_key)
    return await client.generate_image_gemini(
        prompt, model=IMAGE_MODEL_CODE, references=decoded or None
    )


def bytes_to_data_url(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Encode raw image bytes as a data URL suitable for inline display.

    Gemini returns JPEG by default; callers may pass the actual MIME type when
    known (e.g. ``"image/png"`` for PNG responses).
    """
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{b64}"
