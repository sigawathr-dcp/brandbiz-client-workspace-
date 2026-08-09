"""
app/services/policy_engine.py

Policy Engine — decides whether a user's request can use the requested model,
and falls back to local LLM when external is blocked by tier/permission.

Decision inputs:
    - User (role, departments, current month's quota state)
    - Requested model code (or 'auto' → orchestrator picks)
    - Detected data tier (from classifier.py)
    - Estimated input tokens (for quota pre-check)

Decision output:
    PolicyDecision(allowed, model_code, reasons, downgrade_to_local)

Key rules:
    1. Local model is ALWAYS allowed (no quota, no tier block).
    2. Tier 3/4 data NEVER leaves to external API → silently downgrade to local.
    3. Tier 4 data requires role L5+ even for local.
    4. External model requires role-based or department-based permission.
    5. External call must fit within remaining monthly quota.

When a request is downgraded (not denied), the orchestrator gets a usable
model_code back and the audit log records the downgrade reason. This means
users never see a hard "denied" for tier reasons — the system just routes
their request safely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, RoleLevel
from app.models.permission import RoleModelPermission, DepartmentModelPermission
from app.models.model_catalog import ModelCatalog
from app.models.quota import Quota, QuotaDefault
from app.models.classification import DataTier


LOCAL_MODEL_CODE = "qwen2.5-14b-local"
L5_AND_ABOVE = {RoleLevel.L5, RoleLevel.L6, RoleLevel.ADMIN}


class DenyReason(str, Enum):
    ROLE_NOT_ALLOWED      = "role_not_allowed"
    TIER_BLOCKS_EXTERNAL  = "tier_blocks_external"
    TIER_4_REQUIRES_L5    = "tier_4_requires_L5"
    QUOTA_EXCEEDED        = "quota_exceeded"
    MODEL_INACTIVE        = "model_inactive"
    UNKNOWN_MODEL         = "unknown_model"


@dataclass
class PolicyDecision:
    allowed: bool
    model_code: str
    reasons: list[str] = field(default_factory=list)
    downgrade_to_local: bool = False
    quota_remaining: Optional[int] = None


class PolicyEngine:
    """Stateless decision engine. Reads DB; no caching here — caller may cache."""

    def __init__(self, session: AsyncSession):
        self.db = session

    async def decide(
        self,
        user: User,
        requested_model: str,
        detected_tier: DataTier,
        estimated_input_tokens: int,
    ) -> PolicyDecision:
        # ---- Rule 1: Local model is always allowed (modulo Tier 4 role check) ----
        if requested_model == LOCAL_MODEL_CODE:
            if detected_tier == DataTier.TIER_4_RESTRICTED and user.role not in L5_AND_ABOVE:
                return PolicyDecision(
                    allowed=False,
                    model_code="",
                    reasons=[DenyReason.TIER_4_REQUIRES_L5],
                )
            return PolicyDecision(
                allowed=True,
                model_code=LOCAL_MODEL_CODE,
                reasons=["local_always_allowed"],
            )

        # ---- Validate model exists & is active ----
        model = await self._get_model(requested_model)
        if model is None:
            return PolicyDecision(False, "", [DenyReason.UNKNOWN_MODEL])
        if not model.is_active:
            return PolicyDecision(False, "", [DenyReason.MODEL_INACTIVE])

        # ---- Rule 2: Tier 3/4 must stay local (silent downgrade) ----
        if detected_tier in (DataTier.TIER_3_CONFIDENTIAL, DataTier.TIER_4_RESTRICTED):
            if detected_tier == DataTier.TIER_4_RESTRICTED and user.role not in L5_AND_ABOVE:
                return PolicyDecision(False, "", [DenyReason.TIER_4_REQUIRES_L5])
            return PolicyDecision(
                allowed=True,
                model_code=LOCAL_MODEL_CODE,
                reasons=[DenyReason.TIER_BLOCKS_EXTERNAL],
                downgrade_to_local=True,
            )

        # ---- Rule 3: Role / Department permission for external model ----
        allowed_models = await self._allowed_external_models(user)
        if requested_model not in allowed_models:
            return PolicyDecision(
                allowed=True,
                model_code=LOCAL_MODEL_CODE,
                reasons=[DenyReason.ROLE_NOT_ALLOWED],
                downgrade_to_local=True,
            )

        # ---- Rule 4: Monthly quota check ----
        quota = await self._get_or_create_current_quota(user)
        remaining = quota.tokens_limit - quota.tokens_used
        if remaining < estimated_input_tokens:
            return PolicyDecision(
                allowed=False,
                model_code="",
                reasons=[DenyReason.QUOTA_EXCEEDED],
                quota_remaining=remaining,
            )

        # ---- All checks passed ----
        return PolicyDecision(
            allowed=True,
            model_code=requested_model,
            reasons=["all_checks_passed"],
            quota_remaining=remaining,
        )

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    async def _get_model(self, code: str) -> Optional[ModelCatalog]:
        stmt = select(ModelCatalog).where(ModelCatalog.code == code)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _allowed_external_models(self, user: User) -> set[str]:
        """Union of role-based and department-based permissions, external models only."""
        # Role-based
        role_stmt = (
            select(ModelCatalog.code)
            .join(RoleModelPermission, RoleModelPermission.model_id == ModelCatalog.id)
            .where(
                and_(
                    RoleModelPermission.role == user.role,
                    ModelCatalog.is_local.is_(False),
                    ModelCatalog.is_active.is_(True),
                )
            )
        )
        role_models = set((await self.db.execute(role_stmt)).scalars().all())

        # Department add-ons (Marketing → Gemini Image, etc.)
        dept_ids = [d.id for d in user.departments]
        dept_models: set[str] = set()
        if dept_ids:
            dept_stmt = (
                select(ModelCatalog.code)
                .join(DepartmentModelPermission, DepartmentModelPermission.model_id == ModelCatalog.id)
                .where(
                    and_(
                        DepartmentModelPermission.department_id.in_(dept_ids),
                        ModelCatalog.is_local.is_(False),
                        ModelCatalog.is_active.is_(True),
                    )
                )
            )
            dept_models = set((await self.db.execute(dept_stmt)).scalars().all())

        return role_models | dept_models

    async def _get_or_create_current_quota(self, user: User) -> Quota:
        period_start = date.today().replace(day=1)
        stmt = select(Quota).where(
            and_(Quota.user_id == user.id, Quota.period_start == period_start)
        )
        quota = (await self.db.execute(stmt)).scalar_one_or_none()
        if quota is not None:
            return quota

        # First request this month → create with role-based default limit
        default_stmt = select(QuotaDefault.monthly_token_limit).where(
            QuotaDefault.role == user.role
        )
        default_limit = (await self.db.execute(default_stmt)).scalar_one()

        quota = Quota(
            user_id=user.id,
            period_start=period_start,
            tokens_limit=default_limit,
            tokens_used=0,
        )
        self.db.add(quota)
        await self.db.flush()
        return quota


# =============================================================================
# Usage example (from the orchestrator)
# =============================================================================
"""
async def handle_chat_message(user, message, requested_model="auto"):
    tier = await classifier.detect(message)
    estimated_tokens = await tokenizer.count(message)

    if requested_model == "auto":
        requested_model = pick_default_model(user)  # e.g. claude-sonnet-4 for L3+

    policy = PolicyEngine(db_session)
    decision = await policy.decide(user, requested_model, tier, estimated_tokens)

    if not decision.allowed:
        await audit.log("model_blocked", user, details=decision.reasons)
        raise PermissionError(decision.reasons)

    # If downgraded, tell the user transparently (or silently route)
    if decision.downgrade_to_local:
        await audit.log("tier_blocked", user, details=decision.reasons)

    # Actual LLM call
    client = llm_router.get(decision.model_code)
    response = await client.chat(message)

    # Decrement quota only for external calls
    if decision.model_code != LOCAL_MODEL_CODE:
        await quota_service.consume(user, response.tokens_total)

    return response
"""
