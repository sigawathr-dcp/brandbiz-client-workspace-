"""
app/services/studio.py

True Studio service — generates images (via Gemini, through PolicyEngine §7.2),
generates videos (via Veo, in-process background task),
and generates music clips (via Lyria 3 Clip, in-process background task).

All actions are audited. Prompts are encrypted before DB insert (§7.1).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import crypto
from app.db import session_factory
from app.models.studio import StudioGeneration
from app.models.user import User
from app.services import audit as audit_svc
from app.services.classifier import detect_tier
from app.services.policy_engine import DenyReason
from app.tools.image_gen import (
    IMAGE_MODEL_CODE,
    authorize_image,
    bytes_to_data_url,
    generate_image_bytes,
    image_authorized,
)
from app.tools.video_gen import (
    VIDEO_MODEL_CODE,
    authorize_video,
    generate_video_bytes,
    video_authorized,
)
from app.tools.music_gen import (
    MUSIC_MODEL_CODE,
    authorize_music,
    generate_music_bytes,
    music_authorized,
)

# ---------------------------------------------------------------------------
# Template seed data (one source of truth — also returned by list_templates)
# ---------------------------------------------------------------------------

_IMAGE_TEMPLATES = [
    {
        "id": "tpl-img-1",
        "type": "image",
        "title": "Advertisement Poster",
        "preview_image": "/studio-templates/tpl-img-1.jpg",
        "description": (
            "You are a senior E-commerce Creative Director. Create a premium "
            "product advertisement poster with elegant typography and vivid colours."
        ),
    },
    {
        "id": "tpl-img-2",
        "type": "image",
        "title": "Animated Multiverse: The 2000s Collection",
        "preview_image": "/studio-templates/tpl-img-2.jpg",
        "description": (
            "Create a 5-panel horizontal collage (2×3 grid) using the uploaded "
            "person's face. Reimagine them in iconic 2000s cartoon universes."
        ),
    },
    {
        "id": "tpl-img-3",
        "type": "image",
        "title": "Hogwarts Student Dossier",
        "preview_image": "/studio-templates/tpl-img-3.jpg",
        "description": (
            "Create a premium Hogwarts Student Dossier poster based on the "
            "uploaded portrait photo. The user will be sorted into a house."
        ),
    },
    {
        "id": "tpl-img-4",
        "type": "image",
        "title": "How to Dress to Match Your Face",
        "preview_image": "/studio-templates/tpl-img-4.jpg",
        "description": (
            "Create a premium Korean-style fashion recommendation infographic "
            "template showing outfit pairings matched to face shape."
        ),
    },
    {
        "id": "tpl-img-5",
        "type": "image",
        "title": "Tiny Me Universe",
        "preview_image": "/studio-templates/tpl-img-5.jpg",
        "description": (
            "Transform this photo into a magical 'Tiny Me' universe where adorable "
            "miniature animated versions of the person live in a giant world."
        ),
    },
    {
        "id": "tpl-img-6",
        "type": "image",
        "title": "Turn Your Photo Into Japanese Urban Art",
        "preview_image": "/studio-templates/tpl-img-6.jpg",
        "description": (
            "Create a realistic illustration portrait based on the uploaded photo "
            "in the style of Japanese Urban Art with ink wash and bold linework."
        ),
    },
]

_VIDEO_TEMPLATES = [
    {
        "id": "tpl-vid-1",
        "type": "video",
        "title": "Product Viral Ads Video",
        "preview_image": "/studio-templates/tpl-vid-1.jpg",
        "description": (
            "Analyze the uploaded product image, identify the product, and create "
            "a high-energy viral ad video with dynamic cuts and bold captions."
        ),
    },
    {
        "id": "tpl-vid-2",
        "type": "video",
        "title": "Hip-Hop Pet Dancing",
        "preview_image": "/studio-templates/tpl-vid-2.jpg",
        "description": (
            "Create a vertical 9:16 video using the uploaded pet photo. "
            "The pet is dancing energetically to a power hip-hop beat."
        ),
    },
    {
        "id": "tpl-vid-3",
        "type": "video",
        "title": "Pet at the Office Desk",
        "preview_image": "/studio-templates/tpl-vid-3.jpg",
        "description": (
            "8-second cinematic clip: [USER_PET] sitting attentively on an office "
            "chair at a modern open-plan workspace, looking professional."
        ),
    },
    {
        "id": "tpl-vid-4",
        "type": "video",
        "title": "Pet Playing Basketball",
        "preview_image": "/studio-templates/tpl-vid-4.jpg",
        "description": (
            "Create a cinematic, ultra-realistic video of a [ANIMAL] playing "
            "basketball on an outdoor street court with dramatic lighting."
        ),
    },
    {
        "id": "tpl-vid-5",
        "type": "video",
        "title": "Pet in Bakery Restaurant",
        "preview_image": "/studio-templates/tpl-vid-5.jpg",
        "description": (
            "A realistic [ANIMAL] with natural anatomy and authentic physical "
            "features working as a baker in a cosy artisan pastry shop."
        ),
    },
    {
        "id": "tpl-vid-6",
        "type": "video",
        "title": "Your Pet in Kung Fu Mode",
        "preview_image": "/studio-templates/tpl-vid-6.jpg",
        "description": (
            "A realistic [ANIMAL] wearing traditional kung fu attire, performing "
            "martial arts moves with graceful, slow-motion cinematography."
        ),
    },
]

_MUSIC_TEMPLATES = [
    {
        "id": "tpl-mus-1",
        "type": "music",
        "title": "Confidence Anthem — T-Pop / TikTok",
        "preview_image": "/studio-templates/tpl-mus-1.jpg",
        "description": (
            "Upbeat Thai T-Pop track, catchy synth melody, trendy rhythm, "
            "confident and playful lyrics about self-empowerment."
        ),
    },
    {
        "id": "tpl-mus-2",
        "type": "music",
        "title": "Stressed But Bright",
        "preview_image": "/studio-templates/tpl-mus-2.jpg",
        "description": (
            "Bright and cheerful Thai commercial jingle style, catchy melody, "
            "playful rhythm, overly happy tone that masks underlying stress."
        ),
    },
    {
        "id": "tpl-mus-3",
        "type": "music",
        "title": "Procrastination as K-Pop",
        "preview_image": "/studio-templates/tpl-mus-3.jpg",
        "description": (
            "Modern Korean K-Pop group track, synth-heavy polished production, "
            "MULTI-VOCAL HARMONY, about putting off tasks until tomorrow."
        ),
    },
    {
        "id": "tpl-mus-4",
        "type": "music",
        "title": "Bad Luck as Love Ballad",
        "preview_image": "/studio-templates/tpl-mus-4.jpg",
        "description": (
            "Dramatic Thai pop love ballad, grand piano and sweeping strings, "
            "heartbreak-level emotion aimed at ordinary daily misfortunes."
        ),
    },
    {
        "id": "tpl-mus-5",
        "type": "music",
        "title": "Cravings as Thai City Pop",
        "preview_image": "/studio-templates/tpl-mus-5.jpg",
        "description": (
            "Thai City Pop / vintage drama OST feel. Rhodes piano, warm electric "
            "bass, smooth groove about irresistible late-night food cravings."
        ),
    },
    {
        "id": "tpl-mus-6",
        "type": "music",
        "title": "Life as Rap",
        "preview_image": "/studio-templates/tpl-mus-6.jpg",
        "description": (
            "Thai hip-hop rap track, old-school boom-bap beat with modern production, "
            "confident charismatic flow narrating everyday hustle."
        ),
    },
]

_ALL_TEMPLATES = _IMAGE_TEMPLATES + _VIDEO_TEMPLATES + _MUSIC_TEMPLATES


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate(
    session: AsyncSession,
    user: User,
    type_: str,
    model_label: str,
    prompt: str,
    settings: dict[str, Any],
    references: list[str] | None = None,
    background: BackgroundTasks | None = None,
    parent_id: uuid.UUID | None = None,
) -> StudioGeneration:
    """Create a StudioGeneration record.

    - image: routes through PolicyEngine + Gemini (real, synchronous).
    - video: routes through PolicyEngine + Veo (real, background task; returns status='processing').
    - music: routes through PolicyEngine + Lyria (real, background task; returns status='processing').
    Prompt is encrypted before DB insert (§7.1).
    ``references`` (image data URLs) is forwarded to image generation only; not persisted.
    ``parent_id``, if given, must reference a generation owned by ``user``; used to link
    an edit/regenerate to its source (image edit, video/music regenerate-with-tweaks).
    """
    if parent_id is not None:
        parent = await get_generation(session, user.id, parent_id)
        if parent is None:
            raise HTTPException(status_code=404, detail="Parent generation not found")

    if type_ == "image":
        return await _generate_image(session, user, model_label, prompt, settings, references, parent_id)
    elif type_ == "video":
        return await _generate_video(session, user, model_label, prompt, settings, background, parent_id)
    elif type_ == "music":
        return await _generate_music(session, user, model_label, prompt, settings, background, parent_id)
    else:
        raise HTTPException(status_code=422, detail=f"Unknown studio type: {type_!r}")


async def list_generations(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    limit: int = 50,
    offset: int = 0,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort: str = "recent",
) -> list[StudioGeneration]:
    stmt = select(StudioGeneration).where(StudioGeneration.user_id == user_id)
    if date_from is not None:
        stmt = stmt.where(StudioGeneration.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(StudioGeneration.created_at < date_to)
    if sort == "oldest":
        stmt = stmt.order_by(StudioGeneration.created_at.asc())
    else:
        stmt = stmt.order_by(StudioGeneration.created_at.desc())
    stmt = stmt.offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


def list_templates(type_filter: str | None = None) -> list[dict]:
    """Return seed templates, optionally filtered by type."""
    if not type_filter or type_filter == "all":
        return _ALL_TEMPLATES
    return [t for t in _ALL_TEMPLATES if t["type"] == type_filter]


async def get_generation(
    session: AsyncSession,
    user_id: uuid.UUID,
    gen_id: uuid.UUID,
) -> StudioGeneration | None:
    """Return one StudioGeneration by id, scoped to user_id. Returns None if not found."""
    result = await session.execute(
        select(StudioGeneration).where(
            StudioGeneration.id == gen_id,
            StudioGeneration.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _generate_image(
    session: AsyncSession,
    user: User,
    model_label: str,
    prompt: str,
    settings: dict[str, Any],
    references: list[str] | None = None,
    parent_id: uuid.UUID | None = None,
) -> StudioGeneration:
    tier = detect_tier(prompt)
    decision = await authorize_image(session, user, tier)

    if not image_authorized(decision):
        reasons = [r.value if hasattr(r, "value") else str(r) for r in decision.reasons]
        if DenyReason.ROLE_NOT_ALLOWED.value in reasons:
            denial_msg = (
                "You are not authorized to generate images. "
                "This feature is available to L5-level users and above, "
                "or members of the Marketing department."
            )
        elif (
            DenyReason.TIER_BLOCKS_EXTERNAL.value in reasons
            or DenyReason.TIER_4_REQUIRES_L5.value in reasons
        ):
            denial_msg = (
                "Image generation is not available because the prompt "
                "contains confidential or restricted data."
            )
        else:
            denial_msg = "You are not authorized to generate images."

        await audit_svc.log(
            action="studio_image_denied",
            user_id=user.id,
            details={"reasons": reasons},
        )
        raise HTTPException(
            status_code=403,
            detail={
                "error": "studio_image_unauthorized",
                "reasons": reasons,
                "message": denial_msg,
            },
        )

    await audit_svc.log(
        action="studio_generate_requested",
        user_id=user.id,
        details={"type": "image", "model_label": model_label, "prompt_length": len(prompt)},
    )

    try:
        image_bytes, mime_type = await generate_image_bytes(prompt, references)
        output_ref = bytes_to_data_url(image_bytes, mime_type)
        status = "completed"
    except Exception:
        status = "failed"
        output_ref = None
        raise
    finally:
        ct, nonce, tag, kv = crypto.encrypt(prompt)
        gen = StudioGeneration(
            user_id=user.id,
            parent_id=parent_id,
            type="image",
            model_label=model_label,
            prompt_ciphertext=ct,
            prompt_nonce=nonce,
            prompt_tag=tag,
            key_version=kv,
            settings=settings or None,
            status=status,
            output_ref=output_ref if status == "completed" else None,
            token_cost=None,
        )
        session.add(gen)
        await session.commit()
        await session.refresh(gen)

    await audit_svc.log(
        action="studio_image_generated",
        user_id=user.id,
        details={
            "generation_id": str(gen.id),
            "model": IMAGE_MODEL_CODE,
            "bytes": len(image_bytes) if status == "completed" else 0,
            "references": len(references) if references else 0,
            "parent_id": str(parent_id) if parent_id else None,
        },
    )
    return gen


async def _generate_video(
    session: AsyncSession,
    user: User,
    model_label: str,
    prompt: str,
    settings: dict[str, Any],
    background: BackgroundTasks | None,
    parent_id: uuid.UUID | None = None,
) -> StudioGeneration:
    """Authorize, insert a 'processing' row, schedule Veo job in background."""
    tier = detect_tier(prompt)
    decision = await authorize_video(session, user, tier)

    if not video_authorized(decision):
        reasons = [r.value if hasattr(r, "value") else str(r) for r in decision.reasons]
        if DenyReason.ROLE_NOT_ALLOWED.value in reasons:
            denial_msg = (
                "You are not authorized to generate videos. "
                "This feature is available to L5-level users and above, "
                "or members of the Marketing department."
            )
        elif (
            DenyReason.TIER_BLOCKS_EXTERNAL.value in reasons
            or DenyReason.TIER_4_REQUIRES_L5.value in reasons
        ):
            denial_msg = (
                "Video generation is not available because the prompt "
                "contains confidential or restricted data."
            )
        elif DenyReason.UNKNOWN_MODEL.value in reasons or DenyReason.MODEL_INACTIVE.value in reasons:
            denial_msg = (
                "Video generation is temporarily unavailable — the video model is not "
                "configured in the database. Please contact your administrator."
            )
        else:
            denial_msg = "You are not authorized to generate videos."

        await audit_svc.log(
            action="studio_video_denied",
            user_id=user.id,
            details={"reasons": reasons},
        )
        raise HTTPException(
            status_code=403,
            detail={
                "error": "studio_video_unauthorized",
                "reasons": reasons,
                "message": denial_msg,
            },
        )

    await audit_svc.log(
        action="studio_generate_requested",
        user_id=user.id,
        details={"type": "video", "model_label": model_label, "prompt_length": len(prompt)},
    )

    # Encrypt and persist with status='processing'
    ct, nonce, tag, kv = crypto.encrypt(prompt)
    gen = StudioGeneration(
        user_id=user.id,
        parent_id=parent_id,
        type="video",
        model_label=model_label,
        prompt_ciphertext=ct,
        prompt_nonce=nonce,
        prompt_tag=tag,
        key_version=kv,
        settings=settings or None,
        status="processing",
        output_ref=None,
        token_cost=None,
    )
    session.add(gen)
    await session.commit()
    await session.refresh(gen)

    # Schedule the Veo call in the background (runs after HTTP response returns)
    if background is not None:
        background.add_task(
            _run_video_generation,
            gen_id=gen.id,
            user_id=user.id,
            prompt=prompt,
            settings=settings,
        )

    return gen


async def _run_video_generation(
    gen_id: uuid.UUID,
    user_id: uuid.UUID,
    prompt: str,
    settings: dict[str, Any],
) -> None:
    """Background task: call Veo, update the StudioGeneration row to completed/failed.

    Opens its own DB session because the request session has already been closed
    by the time this task runs.
    """
    status = "failed"
    output_ref: str | None = None
    extra_details: dict[str, Any] = {}

    try:
        video_bytes, mime_type = await generate_video_bytes(prompt, settings)
        output_ref = bytes_to_data_url(video_bytes, mime_type)
        status = "completed"
        extra_details = {"bytes": len(video_bytes), "model": VIDEO_MODEL_CODE}
    except Exception as exc:
        extra_details = {"error": str(exc)}

    async with session_factory() as session:
        await session.execute(
            update(StudioGeneration)
            .where(StudioGeneration.id == gen_id)
            .values(status=status, output_ref=output_ref)
        )
        await session.commit()

        await audit_svc.log(
            action="studio_video_generated" if status == "completed" else "studio_video_failed",
            user_id=user_id,
            details={"generation_id": str(gen_id), "status": status, **extra_details},
        )


async def _generate_music(
    session: AsyncSession,
    user: User,
    model_label: str,
    prompt: str,
    settings: dict[str, Any],
    background: BackgroundTasks | None,
    parent_id: uuid.UUID | None = None,
) -> StudioGeneration:
    """Authorize, insert a 'processing' row, schedule Lyria job in background."""
    tier = detect_tier(prompt)
    decision = await authorize_music(session, user, tier)

    if not music_authorized(decision):
        reasons = [r.value if hasattr(r, "value") else str(r) for r in decision.reasons]
        if DenyReason.ROLE_NOT_ALLOWED.value in reasons:
            denial_msg = (
                "You are not authorized to generate music. "
                "This feature is available to L5-level users and above, "
                "or members of the Marketing department."
            )
        elif (
            DenyReason.TIER_BLOCKS_EXTERNAL.value in reasons
            or DenyReason.TIER_4_REQUIRES_L5.value in reasons
        ):
            denial_msg = (
                "Music generation is not available because the prompt "
                "contains confidential or restricted data."
            )
        else:
            denial_msg = "You are not authorized to generate music."

        await audit_svc.log(
            action="studio_music_denied",
            user_id=user.id,
            details={"reasons": reasons},
        )
        raise HTTPException(
            status_code=403,
            detail={
                "error": "studio_music_unauthorized",
                "reasons": reasons,
                "message": denial_msg,
            },
        )

    await audit_svc.log(
        action="studio_generate_requested",
        user_id=user.id,
        details={"type": "music", "model_label": model_label, "prompt_length": len(prompt)},
    )

    # Encrypt and persist with status='processing'
    ct, nonce, tag, kv = crypto.encrypt(prompt)
    gen = StudioGeneration(
        user_id=user.id,
        parent_id=parent_id,
        type="music",
        model_label=model_label,
        prompt_ciphertext=ct,
        prompt_nonce=nonce,
        prompt_tag=tag,
        key_version=kv,
        settings=settings or None,
        status="processing",
        output_ref=None,
        token_cost=None,
    )
    session.add(gen)
    await session.commit()
    await session.refresh(gen)

    # Schedule the Lyria call in the background (runs after HTTP response returns)
    if background is not None:
        background.add_task(
            _run_music_generation,
            gen_id=gen.id,
            user_id=user.id,
            prompt=prompt,
            settings=settings,
        )

    return gen


async def _run_music_generation(
    gen_id: uuid.UUID,
    user_id: uuid.UUID,
    prompt: str,
    settings: dict[str, Any],
) -> None:
    """Background task: call Lyria, update the StudioGeneration row to completed/failed.

    Opens its own DB session because the request session has already been closed
    by the time this task runs.
    """
    status = "failed"
    output_ref: str | None = None
    extra_details: dict[str, Any] = {}

    try:
        audio_bytes, mime_type = await generate_music_bytes(prompt, settings)
        output_ref = bytes_to_data_url(audio_bytes, mime_type)
        status = "completed"
        extra_details = {"bytes": len(audio_bytes), "model": MUSIC_MODEL_CODE}
    except Exception as exc:
        extra_details = {"error": str(exc)}

    async with session_factory() as session:
        await session.execute(
            update(StudioGeneration)
            .where(StudioGeneration.id == gen_id)
            .values(status=status, output_ref=output_ref)
        )
        await session.commit()

        await audit_svc.log(
            action="studio_music_generated" if status == "completed" else "studio_music_failed",
            user_id=user_id,
            details={"generation_id": str(gen_id), "status": status, **extra_details},
        )
