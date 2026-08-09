"""
app/tools/video_gen.py

Video generation tool — authorization helpers and Google Veo integration.

Exported helpers used by the studio service.
Authorization is always delegated to PolicyEngine.decide() — never bypassed (§7.2).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.llm.base import LLMProviderError
from app.llm.google import GoogleClient
from app.models.classification import DataTier
from app.models.user import User
from app.services.policy_engine import PolicyDecision, PolicyEngine
from app.tools.image_gen import bytes_to_data_url

# Matches the model_catalog.code seeded by migration 0021.
VIDEO_MODEL_CODE = "veo-3.1-lite-generate-preview"

# Veo 3.1 Lite only supports 16:9 and 9:16; default to 16:9 for anything else.
_VALID_ASPECT_RATIOS = {"16:9", "9:16"}

# Veo 3.1 Lite only accepts discrete durations: 4, 6, or 8 seconds.
_VALID_DURATIONS = (4, 6, 8)


def _parse_duration(video_length: str | None, default: int = 8) -> int:
    """Parse "Ns" → N, snap to nearest Veo 3.1 discrete duration {4, 6, 8}."""
    if not video_length:
        return default
    try:
        raw = int(video_length.rstrip("s"))
    except ValueError:
        return default
    # Snap to nearest allowed value
    return min(_VALID_DURATIONS, key=lambda d: abs(d - raw))


async def authorize_video(
    session: AsyncSession,
    user: User,
    tier: DataTier,
) -> PolicyDecision:
    """Run PolicyEngine.decide() for VIDEO_MODEL_CODE.

    Callers must check video_authorized(decision) on the result before proceeding.
    Passes estimated_input_tokens=0 — video generation is not token-quota-gated.
    """
    return await PolicyEngine(session).decide(user, VIDEO_MODEL_CODE, tier, 0)


def video_authorized(decision: PolicyDecision) -> bool:
    """Return True only when PolicyEngine granted the video model without downgrade."""
    return (
        decision.allowed
        and not decision.downgrade_to_local
        and decision.model_code == VIDEO_MODEL_CODE
    )


async def generate_video_bytes(prompt: str, settings: dict[str, Any]) -> tuple[bytes, str]:
    """Call Veo and return (raw_mp4_bytes, 'video/mp4').

    Authorization must be checked BEFORE calling this function via
    authorize_video() + video_authorized().
    """
    cfg = get_settings()
    if not cfg.google_api_key:
        raise LLMProviderError("GOOGLE_API_KEY is not configured — video generation unavailable")

    aspect_ratio = settings.get("aspect_ratio", "16:9")
    if aspect_ratio not in _VALID_ASPECT_RATIOS:
        aspect_ratio = "16:9"

    duration_seconds = _parse_duration(settings.get("video_length"))

    client = GoogleClient(api_key=cfg.google_api_key)
    return await client.generate_video(
        prompt,
        model=VIDEO_MODEL_CODE,
        aspect_ratio=aspect_ratio,
        duration_seconds=duration_seconds,
    )


__all__ = [
    "VIDEO_MODEL_CODE",
    "authorize_video",
    "video_authorized",
    "generate_video_bytes",
    "bytes_to_data_url",
]
