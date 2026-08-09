"""
app/tools/music_gen.py

Music generation tool — authorization helpers and Google Lyria integration.

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

# Matches the model_catalog.code seeded by migration 0016.
MUSIC_MODEL_CODE = "lyria-3-clip-preview"


async def authorize_music(
    session: AsyncSession,
    user: User,
    tier: DataTier,
) -> PolicyDecision:
    """Run PolicyEngine.decide() for MUSIC_MODEL_CODE.

    Callers must check music_authorized(decision) on the result before proceeding.
    Passes estimated_input_tokens=0 — music generation is not token-quota-gated.
    """
    return await PolicyEngine(session).decide(user, MUSIC_MODEL_CODE, tier, 0)


def music_authorized(decision: PolicyDecision) -> bool:
    """Return True only when PolicyEngine granted the music model without downgrade."""
    return (
        decision.allowed
        and not decision.downgrade_to_local
        and decision.model_code == MUSIC_MODEL_CODE
    )


async def generate_music_bytes(prompt: str, settings: dict[str, Any]) -> tuple[bytes, str]:
    """Call Lyria and return (raw_audio_bytes, mime_type).

    Authorization must be checked BEFORE calling this function via
    authorize_music() + music_authorized().

    Settings are mapped into the prompt (Lyria Clip doesn't accept config knobs):
    - music_detailed_prompt → appended verbatim (structure notes, e.g. "[Verse]").
    - instrumental_only → appends "Instrumental only, no vocals."
    - negative_prompt → appends "Avoid: <value>."
    - music_genre → appends "Genre: <value>." (skipped when "Auto"/blank).
    - music_bpm → appends "Tempo: <value>." (skipped when "Auto"/blank).
    - music_vocal_gender → appends "<Male/Female> vocals." (skipped when "auto"
      or when instrumental_only is set).
    Duration is always 30s for Lyria 3 Clip; the music_duration setting is ignored.
    """
    cfg = get_settings()
    if not cfg.google_api_key:
        raise LLMProviderError("GOOGLE_API_KEY is not configured — music generation unavailable")

    # Augment the prompt with settings that must be expressed in text
    augmented = prompt.strip()

    detailed = settings.get("music_detailed_prompt", "")
    if isinstance(detailed, str) and detailed.strip():
        augmented += f" {detailed.strip()}"

    instrumental_only = bool(settings.get("instrumental_only"))
    if instrumental_only:
        augmented += " Instrumental only, no vocals."

    negative = settings.get("negative_prompt", "")
    if isinstance(negative, str) and negative.strip():
        augmented += f" Avoid: {negative.strip()}."

    genre = settings.get("music_genre", "")
    if isinstance(genre, str) and genre.strip() and genre.strip().lower() != "auto":
        augmented += f" Genre: {genre.strip()}."

    bpm = settings.get("music_bpm", "")
    if isinstance(bpm, str) and bpm.strip() and bpm.strip().lower() != "auto":
        augmented += f" Tempo: {bpm.strip()}."

    vocal_gender = settings.get("music_vocal_gender", "")
    if (
        isinstance(vocal_gender, str)
        and vocal_gender.strip().lower() in ("male", "female")
        and not instrumental_only
    ):
        augmented += f" {vocal_gender.strip().capitalize()} vocals."

    client = GoogleClient(api_key=cfg.google_api_key)
    return await client.generate_music(augmented, model=MUSIC_MODEL_CODE)


__all__ = [
    "MUSIC_MODEL_CODE",
    "authorize_music",
    "music_authorized",
    "generate_music_bytes",
    "bytes_to_data_url",
]
