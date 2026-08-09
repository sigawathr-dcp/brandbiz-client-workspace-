"""
app/routers/image.py

POST /image — generate an image via Gemini gemini-3.1-flash-image.

Access: authorized by PolicyEngine.decide() — Marketing department (MKT) and
roles L5/L6/ADMIN by default (configured via model_catalog + permission tables).
Returns:  {"url": "data:image/png;base64,..."} — base64-encoded PNG.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import require_consent
from app.llm.base import LLMProviderError
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

router = APIRouter(prefix="/image", tags=["image"])


class ImageRequest(BaseModel):
    prompt: str


class ImageResponse(BaseModel):
    url: str  # data:image/png;base64,...


@router.post("", response_model=ImageResponse)
async def generate_image(
    body: ImageRequest,
    user: Annotated[User, Depends(require_consent)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ImageResponse:
    # Classify the prompt to apply tier-based external-call restrictions.
    tier = detect_tier(body.prompt)

    # PolicyEngine.decide() is the single gate for all external model calls (§7.2).
    decision = await authorize_image(session, user, tier)
    if not image_authorized(decision):
        reasons = [r.value if hasattr(r, "value") else str(r) for r in decision.reasons]
        if DenyReason.ROLE_NOT_ALLOWED.value in reasons:
            denial_msg = (
                "You are not authorized to generate images. "
                "This feature is available to L5-level users and above, "
                "or members of the Marketing department."
            )
        elif DenyReason.TIER_BLOCKS_EXTERNAL.value in reasons or DenyReason.TIER_4_REQUIRES_L5.value in reasons:
            denial_msg = (
                "Image generation is not available because the prompt "
                "contains confidential or restricted data."
            )
        else:
            denial_msg = "You are not authorized to generate images."
        raise HTTPException(
            status_code=403,
            detail={
                "error": "image_generation_unauthorized",
                "reasons": reasons,
                "message": denial_msg,
            },
        )

    await audit_svc.log(
        action="image_requested",
        user_id=user.id,
        details={"prompt_length": len(body.prompt)},
    )

    try:
        image_bytes, mime_type = await generate_image_bytes(body.prompt)
    except LLMProviderError as exc:
        provider_code = exc.provider_code
        if provider_code == 429:
            raise HTTPException(status_code=429, detail=str(exc))
        raise HTTPException(status_code=502, detail=str(exc))
    url = bytes_to_data_url(image_bytes, mime_type)

    await audit_svc.log(
        action="image_generated",
        user_id=user.id,
        details={"bytes": len(image_bytes)},
    )

    await session.commit()
    return ImageResponse(url=url)
