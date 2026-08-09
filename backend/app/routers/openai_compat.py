"""
app/routers/openai_compat.py

OpenAI-compatible passthrough endpoint — Part A of the n8n integration.

Exposes:
  POST /v1/chat/completions  — drop-in replacement for the OpenAI API; n8n's
                               "OpenAI Chat Model" node points here.
  GET  /v1/models            — returns the caller's allowed model list in the
                               OpenAI format; used by n8n's model dropdown.

Every call is:
  1. Authenticated via JWT or service-account API key (get_principal).
  2. Classified with detect_tier() on the full messages payload (§7.6).
  3. Gated by PolicyEngine.decide() — the single path to any LLM (§7.2).
  4. Audited (message_sent / message_received / tier_blocked) and quota-
     consumed for external models.
  5. Forwarded to the provider with tools/tool_choice intact — no stripping.

Confidential payloads (Tier 3/4) are silently downgraded to the local model
(D16). The agent in n8n receives the response normally; the downgrade is
visible only in the gateway audit log.

NOTE (v1 scope):
  Tool-calling passthrough is supported for OpenAI-compatible providers only
  (gpt-4o*, gemma4:26b via Ollama). Anthropic/Gemini providers raise 400 if
  selected — route to OpenAI or local for n8n workflows.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_principal
from app.llm.base import LLMProviderError
from app.llm.router import LOCAL_MODEL_CODE, get_router
from app.models.model_catalog import ModelCatalog
from app.models.user import User
from app.services import audit as audit_svc
from app.services import quota as quota_svc
from app.services.classifier import detect_tier
from app.services.policy_engine import DenyReason, PolicyEngine
from app.tools.intent import classify_intent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["openai-compat"])


# ---------------------------------------------------------------------------
# Request / response Pydantic models
# ---------------------------------------------------------------------------

class CompatMessage(BaseModel):
    """Permissive message schema — accepts tool_calls, tool_call_id, etc."""

    model_config = ConfigDict(extra="allow")

    role: str
    content: str | list | None = None
    name: str | None = None
    tool_calls: list | None = None
    tool_call_id: str | None = None


class CompatRequest(BaseModel):
    """Subset of the OpenAI /v1/chat/completions request body."""

    model_config = ConfigDict(extra="allow")

    model: str = "auto"
    messages: list[CompatMessage]
    tools: list[dict] | None = None
    tool_choice: str | dict | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool = False
    n: int = 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _r(reason: Any) -> str:
    return reason.value if hasattr(reason, "value") else str(reason)


def _text_from_messages(messages: list[CompatMessage]) -> str:
    """Extract plain text from messages for classification."""
    parts: list[str] = []
    for m in messages:
        if isinstance(m.content, str):
            parts.append(m.content)
        elif isinstance(m.content, list):
            # content may be a list of {type, text} parts
            for part in m.content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(part.get("text", ""))
    return "\n".join(parts)


async def _compute_cost(
    session: AsyncSession,
    model_code: str,
    tokens_input: int,
    tokens_output: int,
) -> Decimal:
    row = (await session.execute(
        select(
            ModelCatalog.cost_per_1k_input_tokens,
            ModelCatalog.cost_per_1k_output_tokens,
        ).where(ModelCatalog.code == model_code)
    )).one_or_none()
    if row is None or row.cost_per_1k_input_tokens is None:
        return Decimal("0")
    cost_in = row.cost_per_1k_input_tokens * Decimal(tokens_input) / 1000
    cost_out = (row.cost_per_1k_output_tokens or Decimal("0")) * Decimal(tokens_output) / 1000
    return cost_in + cost_out


def _openai_error(message: str, error_type: str = "policy_denied", status: int = 400) -> HTTPException:
    """Return an HTTPException with an OpenAI-shaped error body so n8n surfaces it."""
    return HTTPException(
        status_code=status,
        detail={
            "error": {
                "message": message,
                "type": error_type,
                "code": error_type,
            }
        },
    )


# ---------------------------------------------------------------------------
# GET /v1/models
# ---------------------------------------------------------------------------

@router.get("/models")
async def list_models(
    user: Annotated[User, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Return allowed models in OpenAI list-models format.

    n8n's OpenAI Chat Model node can use this to populate its model dropdown
    (set the base URL to https://api.decomplica.tech/v1 and n8n will GET /models).
    """
    from app.models.department import UserDepartment
    from app.models.permission import DepartmentModelPermission, RoleModelPermission
    from sqlalchemy import and_

    # Local model — always available
    local_row = (await session.execute(
        select(ModelCatalog).where(ModelCatalog.code == LOCAL_MODEL_CODE)
    )).scalar_one_or_none()

    allowed_codes: list[str] = [LOCAL_MODEL_CODE]

    # Role-based permissions
    role_rows = (await session.execute(
        select(ModelCatalog.code)
        .join(RoleModelPermission, RoleModelPermission.model_id == ModelCatalog.id)
        .where(
            and_(
                RoleModelPermission.role == user.role,
                ModelCatalog.is_local.is_(False),
                ModelCatalog.is_active.is_(True),
            )
        )
    )).scalars().all()
    allowed_codes.extend(role_rows)

    # Department add-ons (D19)
    dept_ids = (await session.execute(
        select(UserDepartment.department_id).where(UserDepartment.user_id == user.id)
    )).scalars().all()
    if dept_ids:
        dept_codes = (await session.execute(
            select(ModelCatalog.code)
            .join(DepartmentModelPermission, DepartmentModelPermission.model_id == ModelCatalog.id)
            .where(
                and_(
                    DepartmentModelPermission.department_id.in_(list(dept_ids)),
                    ModelCatalog.is_local.is_(False),
                    ModelCatalog.is_active.is_(True),
                )
            )
        )).scalars().all()
        allowed_codes.extend(dept_codes)

    # Deduplicate, preserving order
    seen: set[str] = set()
    unique_codes: list[str] = []
    for code in allowed_codes:
        if code not in seen:
            seen.add(code)
            unique_codes.append(code)

    return {
        "object": "list",
        "data": [
            {
                "id": code,
                "object": "model",
                "owned_by": "local" if code == LOCAL_MODEL_CODE else "api-gateway",
            }
            for code in unique_codes
        ],
    }


# ---------------------------------------------------------------------------
# POST /v1/chat/completions
# ---------------------------------------------------------------------------

@router.post("/chat/completions")
async def create_chat_completion(
    request: Request,
    body: CompatRequest,
    user: Annotated[User, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    """OpenAI-compatible chat completions with full governance.

    Identical request/response schema to https://api.openai.com/v1/chat/completions.
    Configure n8n's OpenAI Chat Model node:
      Base URL → https://api.decomplica.tech/v1
      API Key  → gw_… (service-account API key)
    """
    # Consent gate — service accounts have consent_acknowledged_at pre-set
    if user.consent_acknowledged_at is None:
        raise _openai_error("Privacy consent not acknowledged — log in to the chat UI first.", status=403)

    # ------------------------------------------------------------------
    # 1. Classify the full payload (§7.6)
    # ------------------------------------------------------------------
    text = _text_from_messages(body.messages)
    tier = detect_tier(text)
    est_tokens = max(len(text) // 4, 1)

    # Log PII events regardless of routing outcome (mirrors chat_policy.py)
    if tier.rank >= tier.__class__.TIER_3_CONFIDENTIAL.rank:  # type: ignore[attr-defined]
        await audit_svc.log(
            action="pii_detected",
            user_id=user.id,
            details={"tier": tier.value, "source": "n8n"},
        )

    # ------------------------------------------------------------------
    # 2. Resolve model + PolicyEngine gate (§7.2)
    # ------------------------------------------------------------------
    requested_model = body.model
    if requested_model == "auto" or not requested_model:
        requested_model = await classify_intent(text) or LOCAL_MODEL_CODE

    decision = await PolicyEngine(session).decide(user, requested_model, tier, est_tokens)

    if not decision.allowed:
        deny_reasons = [_r(r) for r in decision.reasons]
        audit_action = (
            "tier_blocked" if DenyReason.TIER_4_REQUIRES_L5 in decision.reasons
            else "quota_exceeded" if DenyReason.QUOTA_EXCEEDED in decision.reasons
            or DenyReason.WORKSPACE_BUDGET_EXCEEDED in decision.reasons
            else "model_blocked"
        )
        await audit_svc.log(
            action=audit_action,
            user_id=user.id,
            details={
                "model_requested": requested_model,
                "reasons": deny_reasons,
                "tier": tier.value,
                "source": "n8n",
            },
        )
        await session.commit()
        raise _openai_error(
            f"Policy denied: {', '.join(deny_reasons)}",
            error_type="policy_denied",
            status=403,
        )

    if decision.downgrade_to_local:
        await audit_svc.log(
            action="tier_blocked",
            user_id=user.id,
            details={
                "model_requested": requested_model,
                "model_used": decision.model_code,
                "reasons": [_r(r) for r in decision.reasons],
                "tier": tier.value,
                "source": "n8n",
            },
        )

    # ------------------------------------------------------------------
    # 3. Get provider client — check it supports raw passthrough
    # ------------------------------------------------------------------
    try:
        client = get_router().get(decision.model_code)
    except KeyError:
        raise _openai_error(f"Model '{decision.model_code}' is not available.", status=404)

    if not (hasattr(client, "raw_chat") and hasattr(client, "raw_streaming_chat")):
        raise _openai_error(
            f"Provider for '{decision.model_code}' does not support tool-calling "
            "passthrough (v1 supports OpenAI-compatible providers only).",
            status=400,
        )

    # Convert CompatMessage list to plain dicts for the provider
    messages = [m.model_dump(exclude_none=True) for m in body.messages]

    # ------------------------------------------------------------------
    # 4a. Streaming path
    # ------------------------------------------------------------------
    if body.stream:
        async def _sse_stream():
            tokens_input = 0
            tokens_output = 0
            try:
                async for line in client.raw_streaming_chat(
                    messages=messages,
                    tools=body.tools,
                    tool_choice=body.tool_choice,
                    temperature=body.temperature,
                    max_tokens=body.max_tokens,
                ):
                    # Best-effort usage extraction from the final OpenAI chunk
                    if line.startswith("data: ") and not line.rstrip().endswith("[DONE]"):
                        try:
                            chunk_data = json.loads(line[6:].strip())
                            usage = chunk_data.get("usage") or {}
                            if usage.get("prompt_tokens"):
                                tokens_input = usage["prompt_tokens"]
                            if usage.get("completion_tokens"):
                                tokens_output = usage["completion_tokens"]
                        except Exception:
                            pass
                    yield line
            except LLMProviderError as exc:
                err_payload = json.dumps({
                    "error": {"message": str(exc), "type": "provider_error"}
                })
                yield f"data: {err_payload}\n\n"

            # Audit + quota after stream ends
            await audit_svc.log(
                action="message_sent",
                user_id=user.id,
                details={"model_used": decision.model_code, "source": "n8n"},
            )
            await audit_svc.log(
                action="message_received",
                user_id=user.id,
                details={
                    "model_used": decision.model_code,
                    "tokens_input": tokens_input,
                    "tokens_output": tokens_output,
                    "source": "n8n",
                },
            )
            if decision.model_code != LOCAL_MODEL_CODE and (tokens_input > 0 or tokens_output > 0):
                cost = await _compute_cost(session, decision.model_code, tokens_input, tokens_output)
                await quota_svc.consume(session, user, tokens_input, tokens_output, cost)
            await session.commit()

        return StreamingResponse(_sse_stream(), media_type="text/event-stream")

    # ------------------------------------------------------------------
    # 4b. Non-streaming path (default for n8n's LangChain agent)
    # ------------------------------------------------------------------
    try:
        result = await client.raw_chat(
            messages=messages,
            tools=body.tools,
            tool_choice=body.tool_choice,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
        )
    except LLMProviderError as exc:
        raise _openai_error(str(exc), error_type="provider_error", status=502)

    usage = result.get("usage") or {}
    tokens_input = int(usage.get("prompt_tokens", 0))
    tokens_output = int(usage.get("completion_tokens", 0))

    await audit_svc.log(
        action="message_sent",
        user_id=user.id,
        details={"model_used": decision.model_code, "source": "n8n"},
    )
    await audit_svc.log(
        action="message_received",
        user_id=user.id,
        details={
            "model_used": decision.model_code,
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "source": "n8n",
        },
    )
    if decision.model_code != LOCAL_MODEL_CODE and (tokens_input > 0 or tokens_output > 0):
        cost = await _compute_cost(session, decision.model_code, tokens_input, tokens_output)
        await quota_svc.consume(session, user, tokens_input, tokens_output, cost)

    await session.commit()
    return JSONResponse(result)
