"""
app/services/policy_engine.py

Policy Engine — decides whether a user's request can use the requested model,
and falls back to local LLM when external is blocked by tier/permission.

Decision inputs:
    - User (role, departments resolved via user_departments join, current quota state)
    - Requested model code (must be a concrete code; "auto" is resolved before calling)
    - Detected data tier (from classifier.py)
    - Estimated input tokens (for quota pre-check; stubbed until Task 2.3)

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

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.router import DEFAULT_MODEL_CODE
from app.models.classification import DataTier
from app.models.department import UserDepartment
from app.models.model_catalog import ModelCatalog
from app.models.permission import DepartmentModelPermission, RoleModelPermission
from app.models.quota import Quota
from app.models.user import User
from app.models.workspace import Workspace
from app.services.quota import resolve_monthly_token_limit


L5_AND_ABOVE = {"L5", "L6", "ADMIN"}


class DenyReason(str, Enum):
    ROLE_NOT_ALLOWED           = "role_not_allowed"
    TIER_BLOCKS_EXTERNAL       = "tier_blocks_external"
    TIER_4_REQUIRES_L5         = "tier_4_requires_L5"
    QUOTA_EXCEEDED             = "quota_exceeded"
    MODEL_INACTIVE             = "model_inactive"
    UNKNOWN_MODEL              = "unknown_model"
    # D21/D22 — pooled hard cap shared by every seat in a client workspace.
    # Distinct from QUOTA_EXCEEDED (a per-seat monthly ceiling) so an event
    # can size seats generously but still cap the whole booth's spend.
    WORKSPACE_BUDGET_EXCEEDED  = "workspace_budget_exceeded"


@dataclass
class PolicyDecision:
    allowed: bool
    model_code: str
    reasons: list[str] = field(default_factory=list)
    downgrade_to_local: bool = False
    quota_remaining: Optional[int] = None


class PolicyEngine:
    """Stateless decision engine. Reads DB; no caching here — caller may cache."""

    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    async def decide(
        self,
        user: User,
        requested_model: str,
        detected_tier: DataTier,
        estimated_input_tokens: int,
    ) -> PolicyDecision:
        # ---- Rule 1: Default model is always allowed (modulo Tier 4 role check) ----
        # D25: the default is the hosted OpenAI model, not the on-prem one, and
        # the owner accepted Tier 3/4 data going to it. Quota is still consumed
        # after the call (orchestrator.call_llm); it is not pre-checked here so
        # the baseline model can never be "quota-denied" — only exotic models are.
        if requested_model == DEFAULT_MODEL_CODE:
            if detected_tier == DataTier.TIER_4_RESTRICTED and user.role not in L5_AND_ABOVE:
                return PolicyDecision(
                    allowed=False,
                    model_code="",
                    reasons=[DenyReason.TIER_4_REQUIRES_L5],
                )
            return PolicyDecision(
                allowed=True,
                model_code=DEFAULT_MODEL_CODE,
                reasons=["local_always_allowed"],
            )

        # ---- Validate model exists & is active ----
        model = await self._get_model(requested_model)
        if model is None:
            return PolicyDecision(False, "", [DenyReason.UNKNOWN_MODEL])
        if not model.is_active:
            return PolicyDecision(False, "", [DenyReason.MODEL_INACTIVE])

        # ---- Rule 2: Tier 3/4 stay on the default model (silent downgrade) ----
        # Non-default vendors (Claude, Gemini, Perplexity, Hermes) never see
        # confidential/restricted data; the downgrade target is DEFAULT_MODEL_CODE.
        if detected_tier in (DataTier.TIER_3_CONFIDENTIAL, DataTier.TIER_4_RESTRICTED):
            if detected_tier == DataTier.TIER_4_RESTRICTED and user.role not in L5_AND_ABOVE:
                return PolicyDecision(False, "", [DenyReason.TIER_4_REQUIRES_L5])
            return PolicyDecision(
                allowed=True,
                model_code=DEFAULT_MODEL_CODE,
                reasons=[DenyReason.TIER_BLOCKS_EXTERNAL],
                downgrade_to_local=True,
            )

        # ---- Rule 3: Role / Department permission for external model ----
        allowed_models = await self._allowed_external_models(user)
        if requested_model not in allowed_models:
            return PolicyDecision(
                allowed=True,
                model_code=DEFAULT_MODEL_CODE,
                reasons=[DenyReason.ROLE_NOT_ALLOWED],
                downgrade_to_local=True,
            )

        # ---- Rule 4: Monthly quota pre-check (§7.5 — read-only at decision time) ----
        quota = await self._get_or_create_current_quota(user)
        remaining = quota.tokens_limit - quota.tokens_used
        if remaining < estimated_input_tokens:
            return PolicyDecision(
                allowed=False,
                model_code="",
                reasons=[DenyReason.QUOTA_EXCEEDED],
            )

        # ---- Rule 5 (D21/D22): pooled workspace budget, client seats only ----
        # Per-seat quota above already caps one attendee; this caps the whole
        # workspace so N attendees hammering the booth can't add up to an
        # unbounded bill. NULL token_budget_limit = no pooled cap configured.
        if user.workspace_id is not None:
            ws_remaining = await self._workspace_budget_remaining(user.workspace_id)
            if ws_remaining is not None and ws_remaining < estimated_input_tokens:
                return PolicyDecision(
                    allowed=False,
                    model_code="",
                    reasons=[DenyReason.WORKSPACE_BUDGET_EXCEEDED],
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

        dept_ids = await self._department_ids(user.id)
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

    async def _department_ids(self, user_id: uuid.UUID) -> list[int]:
        stmt = select(UserDepartment.department_id).where(
            UserDepartment.user_id == user_id
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def _workspace_budget_remaining(self, workspace_id: uuid.UUID) -> Optional[int]:
        """Pooled token budget remaining for a client workspace, or None if
        no pooled cap is configured (token_budget_limit IS NULL)."""
        ws = (await self.db.execute(
            select(Workspace).where(Workspace.id == workspace_id)
        )).scalar_one_or_none()
        if ws is None or ws.token_budget_limit is None:
            return None
        return ws.token_budget_limit - ws.token_budget_used

    async def _get_or_create_current_quota(self, user: User) -> Quota:
        period_start = date.today().replace(day=1)

        # Single source of truth for the precedence (workspace override,
        # else role default) — see app/services/quota.py::resolve_monthly_token_limit.
        default_limit = await resolve_monthly_token_limit(self.db, user)

        # Race-safe upsert: concurrent first-callers serialise on the UNIQUE
        # constraint; ON CONFLICT DO NOTHING means only one INSERT wins.
        await self.db.execute(
            pg_insert(Quota)
            .values(
                user_id=user.id,
                period_start=period_start,
                tokens_limit=default_limit,
                tokens_used=0,
                cost_used_usd=Decimal("0"),
            )
            .on_conflict_do_nothing(index_elements=["user_id", "period_start"])
        )
        await self.db.flush()

        return (await self.db.execute(
            select(Quota).where(
                and_(Quota.user_id == user.id, Quota.period_start == period_start)
            )
        )).scalar_one()
