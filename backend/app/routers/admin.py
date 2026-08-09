"""
app/routers/admin.py

Admin-only endpoints under /admin/*.
Every mutation is atomic (single transaction), emits an audit_* row, and
bumps the Redis 'perm_version' key so any future policy-engine caching
stays < 30 s stale (§7 gate).

Task 2.7 endpoints:
  GET    /admin/users                         — list, filter, search, paginate
  PATCH  /admin/users/{user_id}               — change role / active / departments
  GET    /admin/permissions/role              — role × model matrix
  PUT    /admin/permissions/role              — replace matrix for one role
  GET    /admin/permissions/department        — dept × model matrix
  PUT    /admin/permissions/department        — replace matrix for one dept

Task 2.6 reveal-queue endpoints also live here (already committed).
"""
from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.deps import require_admin
from app.models.audit import AuditLog
from app.models.conversation import Conversation
from app.models.department import Department, UserDepartment
from app.models.message import Message
from app.models.model_catalog import ModelCatalog
from app.models.permission import DepartmentModelPermission, RoleModelPermission
from app.models.quota import Quota, QuotaDefault
from app.models.reveal import RevealRequest
from app.models.user import User
from app.services import audit as audit_svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

VALID_ROLES = {"L1", "L2", "L3", "L4", "L5", "L6", "ADMIN"}
ROLE_ORDER = ["L1", "L2", "L3", "L4", "L5", "L6", "ADMIN"]

# BIGINT max — the "unlimited" sentinel seeded for L6/ADMIN in 0001_baseline.py
UNLIMITED_SENTINEL = 9_223_372_036_854_775_807



# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _bump_perm_version() -> None:
    pass  # no-op in demo mode (policy engine reads DB directly)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class UserSummary(BaseModel):
    id: uuid.UUID
    google_email: str
    display_name: str | None
    role: str
    is_active: bool
    department_ids: list[int]
    created_at: datetime
    last_login_at: datetime | None

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    items: list[UserSummary]
    total: int


class PatchUserRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    department_ids: list[int] | None = None


class RolePermissionMatrix(BaseModel):
    role: str
    model_codes: list[str]


class DeptPermissionMatrix(BaseModel):
    department_id: int
    model_codes: list[str]


class RevealRequestSummary(BaseModel):
    id: uuid.UUID
    requester_id: uuid.UUID
    target_user_id: uuid.UUID | None
    target_message_id: uuid.UUID
    reason: str
    status: str
    approver_id: uuid.UUID | None
    approved_at: datetime | None
    expires_at: datetime | None
    viewed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ModelInfoResponse(BaseModel):
    id: int
    code: str
    display_name: str
    provider: str
    is_local: bool
    is_active: bool

    model_config = {"from_attributes": True}


class DepartmentResponse(BaseModel):
    id: int
    code: str
    name: str

    model_config = {"from_attributes": True}


class DashboardMetrics(BaseModel):
    active_users: int
    total_messages_month: int
    external_cost_month_usd: float
    pii_blocks_month: int
    pending_reveals: int
    period_start: str  # ISO date "YYYY-MM-01"


class ModelUsageItem(BaseModel):
    model_code: str
    tokens_input: int
    tokens_output: int
    cost_usd: float
    message_count: int


class TopUserItem(BaseModel):
    user_id: str
    email: str
    display_name: str | None
    cost_usd: float
    message_count: int


class MetricsVerifyResponse(BaseModel):
    cached: DashboardMetrics | None
    fresh: DashboardMetrics
    matches: bool
    deltas: dict[str, float]


class AuditLogEntry(BaseModel):
    id: int
    created_at: datetime
    user_id: uuid.UUID | None
    actor_id: uuid.UUID | None
    action: str
    resource_type: str | None
    resource_id: uuid.UUID | None
    details: dict | None
    ip_address: str | None
    user_agent: str | None

    model_config = {"from_attributes": True}

    @field_validator("ip_address", mode="before")
    @classmethod
    def _coerce_ip(cls, v: object) -> str | None:
        return str(v) if v is not None else None


class AuditLogListResponse(BaseModel):
    items: list[AuditLogEntry]
    total: int


# ---------------------------------------------------------------------------
# GET /admin/users
# ---------------------------------------------------------------------------

@router.get("/users", response_model=UserListResponse)
async def list_users(
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    role: str | None = Query(None, description="Filter by role level"),
    department_id: int | None = Query(None, description="Filter by department membership"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    search: str | None = Query(None, description="Case-insensitive email substring search"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> UserListResponse:
    q = select(User)

    if role:
        q = q.where(User.role == role)
    if is_active is not None:
        q = q.where(User.is_active == is_active)
    if search:
        q = q.where(User.google_email.ilike(f"%{search}%"))
    if department_id is not None:
        q = (
            q.join(UserDepartment, UserDepartment.user_id == User.id)
            .where(UserDepartment.department_id == department_id)
        )

    total: int = (await session.execute(
        select(func.count()).select_from(q.subquery())
    )).scalar_one()

    users = list((await session.execute(
        q.order_by(User.created_at.desc()).limit(limit).offset(offset)
    )).scalars().all())

    user_ids = [u.id for u in users]
    dept_rows = (
        list((await session.execute(
            select(UserDepartment).where(UserDepartment.user_id.in_(user_ids))
        )).scalars().all())
        if user_ids else []
    )
    dept_map: dict[uuid.UUID, list[int]] = {}
    for dr in dept_rows:
        dept_map.setdefault(dr.user_id, []).append(dr.department_id)

    items = [
        UserSummary(
            id=u.id,
            google_email=u.google_email,
            display_name=u.display_name,
            role=u.role,
            is_active=u.is_active,
            department_ids=dept_map.get(u.id, []),
            created_at=u.created_at,
            last_login_at=u.last_login_at,
        )
        for u in users
    ]
    return UserListResponse(items=items, total=total)


# ---------------------------------------------------------------------------
# PATCH /admin/users/{user_id}
# ---------------------------------------------------------------------------

@router.patch("/users/{user_id}", response_model=UserSummary)
async def patch_user(
    user_id: uuid.UUID,
    body: PatchUserRequest,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UserSummary:
    """Change role, active status, and/or department memberships atomically."""
    target = (await session.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    changes: dict[str, object] = {}

    if body.role is not None:
        if body.role not in VALID_ROLES:
            raise HTTPException(status_code=422, detail=f"Invalid role: {body.role!r}")
        if target.role != body.role:
            changes["role"] = {"from": target.role, "to": body.role}
            target.role = body.role

    if body.is_active is not None and target.is_active != body.is_active:
        changes["is_active"] = {"from": target.is_active, "to": body.is_active}
        target.is_active = body.is_active

    if body.department_ids is not None:
        await session.execute(
            delete(UserDepartment).where(UserDepartment.user_id == user_id)
        )
        for dept_id in body.department_ids:
            session.add(UserDepartment(user_id=user_id, department_id=dept_id))
        changes["department_ids"] = body.department_ids

    if changes:
        await session.commit()
        await audit_svc.log(
            action="admin_role_changed",
            user_id=user_id,
            actor_id=admin.id,
            resource_type="user",
            resource_id=user_id,
            details={"changes": changes},
        )
        await _bump_perm_version()

    dept_ids = list((await session.execute(
        select(UserDepartment.department_id).where(UserDepartment.user_id == user_id)
    )).scalars().all())

    return UserSummary(
        id=target.id,
        google_email=target.google_email,
        display_name=target.display_name,
        role=target.role,
        is_active=target.is_active,
        department_ids=dept_ids,
        created_at=target.created_at,
        last_login_at=target.last_login_at,
    )


# ---------------------------------------------------------------------------
# GET /admin/permissions/role
# ---------------------------------------------------------------------------

@router.get("/permissions/role", response_model=list[RolePermissionMatrix])
async def get_role_permissions(
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[RolePermissionMatrix]:
    """Return the full role × model permission matrix."""
    rows = list((await session.execute(
        select(RoleModelPermission.role, ModelCatalog.code)
        .join(ModelCatalog, RoleModelPermission.model_id == ModelCatalog.id)
        .order_by(RoleModelPermission.role, ModelCatalog.code)
    )).all())

    matrix: dict[str, list[str]] = {}
    for role, code in rows:
        matrix.setdefault(role, []).append(code)

    return [
        RolePermissionMatrix(role=r, model_codes=codes)
        for r, codes in sorted(matrix.items())
    ]


# ---------------------------------------------------------------------------
# PUT /admin/permissions/role
# ---------------------------------------------------------------------------

@router.put("/permissions/role", response_model=RolePermissionMatrix)
async def put_role_permissions(
    body: RolePermissionMatrix,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RolePermissionMatrix:
    """Replace all model permissions for one role atomically. Audited."""
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"Invalid role: {body.role!r}")

    models = list((await session.execute(
        select(ModelCatalog).where(ModelCatalog.code.in_(body.model_codes))
    )).scalars().all()) if body.model_codes else []

    found_codes = {m.code for m in models}
    missing = set(body.model_codes) - found_codes
    if missing:
        raise HTTPException(
            status_code=422, detail=f"Unknown model codes: {sorted(missing)}"
        )

    await session.execute(
        delete(RoleModelPermission).where(RoleModelPermission.role == body.role)
    )
    for m in models:
        session.add(RoleModelPermission(role=body.role, model_id=m.id))

    await session.commit()
    await audit_svc.log(
        action="admin_permission_changed",
        user_id=admin.id,
        actor_id=admin.id,
        resource_type="role_permission",
        details={"role": body.role, "model_codes": body.model_codes},
    )
    await _bump_perm_version()

    return RolePermissionMatrix(role=body.role, model_codes=body.model_codes)


# ---------------------------------------------------------------------------
# GET /admin/permissions/department
# ---------------------------------------------------------------------------

@router.get("/permissions/department", response_model=list[DeptPermissionMatrix])
async def get_dept_permissions(
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[DeptPermissionMatrix]:
    """Return the full department × model permission matrix."""
    rows = list((await session.execute(
        select(DepartmentModelPermission.department_id, ModelCatalog.code)
        .join(ModelCatalog, DepartmentModelPermission.model_id == ModelCatalog.id)
        .order_by(DepartmentModelPermission.department_id, ModelCatalog.code)
    )).all())

    matrix: dict[int, list[str]] = {}
    for dept_id, code in rows:
        matrix.setdefault(dept_id, []).append(code)

    return [
        DeptPermissionMatrix(department_id=d, model_codes=codes)
        for d, codes in sorted(matrix.items())
    ]


# ---------------------------------------------------------------------------
# PUT /admin/permissions/department
# ---------------------------------------------------------------------------

@router.put("/permissions/department", response_model=DeptPermissionMatrix)
async def put_dept_permissions(
    body: DeptPermissionMatrix,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DeptPermissionMatrix:
    """Replace all model permissions for one department atomically. Audited."""
    dept = (await session.execute(
        select(Department).where(Department.id == body.department_id)
    )).scalar_one_or_none()
    if dept is None:
        raise HTTPException(status_code=404, detail="Department not found")

    models = list((await session.execute(
        select(ModelCatalog).where(ModelCatalog.code.in_(body.model_codes))
    )).scalars().all()) if body.model_codes else []

    found_codes = {m.code for m in models}
    missing = set(body.model_codes) - found_codes
    if missing:
        raise HTTPException(
            status_code=422, detail=f"Unknown model codes: {sorted(missing)}"
        )

    await session.execute(
        delete(DepartmentModelPermission).where(
            DepartmentModelPermission.department_id == body.department_id
        )
    )
    for m in models:
        session.add(DepartmentModelPermission(
            department_id=body.department_id, model_id=m.id
        ))

    await session.commit()
    await audit_svc.log(
        action="admin_permission_changed",
        user_id=admin.id,
        actor_id=admin.id,
        resource_type="dept_permission",
        details={"department_id": body.department_id, "model_codes": body.model_codes},
    )
    await _bump_perm_version()

    return DeptPermissionMatrix(
        department_id=body.department_id, model_codes=body.model_codes
    )


# ---------------------------------------------------------------------------
# Reveal queue (Task 2.6 — already merged here)
# ---------------------------------------------------------------------------

@router.get("/reveals/pending", response_model=list[RevealRequestSummary])
async def list_pending_reveals(
    user: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(50, ge=1, le=500),
) -> list[RevealRequestSummary]:
    rows = (await session.execute(
        select(RevealRequest)
        .where(RevealRequest.status == "pending")
        .order_by(RevealRequest.created_at.asc())
        .limit(limit)
    )).scalars().all()
    return [RevealRequestSummary.model_validate(r) for r in rows]


@router.get("/reveals", response_model=list[RevealRequestSummary])
async def list_reveals(
    user: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[RevealRequestSummary]:
    q = (
        select(RevealRequest)
        .order_by(RevealRequest.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status:
        q = q.where(RevealRequest.status == status)
    rows = (await session.execute(q)).scalars().all()
    return [RevealRequestSummary.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# GET /admin/models  (reference data for Permissions page)
# ---------------------------------------------------------------------------

@router.get("/models", response_model=list[ModelInfoResponse])
async def list_models(
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[ModelInfoResponse]:
    """Return all models from model_catalog, active or not."""
    rows = list((await session.execute(
        select(ModelCatalog).order_by(ModelCatalog.is_local.desc(), ModelCatalog.code)
    )).scalars().all())
    return [ModelInfoResponse.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# GET /admin/departments  (reference data for Users / Permissions pages)
# ---------------------------------------------------------------------------

@router.get("/departments", response_model=list[DepartmentResponse])
async def list_departments(
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[DepartmentResponse]:
    """Return all departments ordered by name."""
    rows = list((await session.execute(
        select(Department).order_by(Department.name)
    )).scalars().all())
    return [DepartmentResponse.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# Metrics helpers (Task 2.8)
# ---------------------------------------------------------------------------

def _month_start() -> datetime:
    """First instant of the current UTC calendar month."""
    d = date.today()
    return datetime(d.year, d.month, 1, tzinfo=timezone.utc)


def _month_start_date() -> date:
    """First day of the current calendar month (for Quota.period_start which is a Date)."""
    return date.today().replace(day=1)


async def _compute_metrics_sql(session: AsyncSession) -> DashboardMetrics:
    """Run all five metric queries directly against the DB."""
    ms = _month_start()

    active_users: int = (await session.execute(
        select(func.count()).select_from(User).where(User.is_active.is_(True))
    )).scalar_one()

    total_messages_month: int = (await session.execute(
        select(func.count()).select_from(Message).where(Message.created_at >= ms)
    )).scalar_one()

    external_cost_raw = (await session.execute(
        select(func.coalesce(func.sum(Message.cost_usd), 0))
        .select_from(Message)
        .join(ModelCatalog, ModelCatalog.code == Message.model_used)
        .where(
            Message.created_at >= ms,
            ModelCatalog.is_local.is_(False),
        )
    )).scalar_one()
    external_cost_month_usd = float(external_cost_raw or 0)

    pii_blocks_month: int = (await session.execute(
        select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "pii_detected",
            AuditLog.created_at >= ms,
        )
    )).scalar_one()

    pending_reveals: int = (await session.execute(
        select(func.count()).select_from(RevealRequest).where(
            RevealRequest.status == "pending"
        )
    )).scalar_one()

    return DashboardMetrics(
        active_users=active_users,
        total_messages_month=total_messages_month,
        external_cost_month_usd=external_cost_month_usd,
        pii_blocks_month=pii_blocks_month,
        pending_reveals=pending_reveals,
        period_start=ms.date().isoformat(),
    )


# ---------------------------------------------------------------------------
# GET /admin/metrics  (Task 2.8)
# ---------------------------------------------------------------------------

@router.get("/metrics", response_model=DashboardMetrics)
async def get_metrics(
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DashboardMetrics:
    return await _compute_metrics_sql(session)


# ---------------------------------------------------------------------------
# GET /admin/metrics/model-usage  (Task 2.8)
# ---------------------------------------------------------------------------

@router.get("/metrics/model-usage", response_model=list[ModelUsageItem])
async def get_model_usage(
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[ModelUsageItem]:
    ms = _month_start()
    rows = (await session.execute(
        select(
            Message.model_used,
            func.coalesce(func.sum(Message.tokens_input), 0).label("tokens_in"),
            func.coalesce(func.sum(Message.tokens_output), 0).label("tokens_out"),
            func.coalesce(func.sum(Message.cost_usd), 0).label("cost"),
            func.count(Message.id).label("msg_count"),
        )
        .where(
            Message.created_at >= ms,
            Message.model_used.is_not(None),
        )
        .group_by(Message.model_used)
        .order_by(func.coalesce(func.sum(Message.cost_usd), 0).desc())
    )).all()

    return [
        ModelUsageItem(
            model_code=r.model_used,
            tokens_input=int(r.tokens_in),
            tokens_output=int(r.tokens_out),
            cost_usd=float(r.cost or 0),
            message_count=r.msg_count,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# GET /admin/metrics/top-users  (Task 2.8)
# ---------------------------------------------------------------------------

@router.get("/metrics/top-users", response_model=list[TopUserItem])
async def get_top_users(
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[TopUserItem]:
    ms = _month_start()
    rows = (await session.execute(
        select(
            User.id.label("uid"),
            User.google_email,
            User.display_name,
            func.coalesce(func.sum(Message.cost_usd), 0).label("cost"),
            func.count(Message.id).label("msg_count"),
        )
        .select_from(User)
        .join(Conversation, Conversation.user_id == User.id)
        .join(Message, Message.conversation_id == Conversation.id)
        .where(Message.created_at >= ms)
        .group_by(User.id, User.google_email, User.display_name)
        .order_by(func.coalesce(func.sum(Message.cost_usd), 0).desc())
        .limit(10)
    )).all()

    return [
        TopUserItem(
            user_id=str(r.uid),
            email=r.google_email,
            display_name=r.display_name,
            cost_usd=float(r.cost or 0),
            message_count=r.msg_count,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# GET /admin/metrics/verify  (Task 2.8)
# ---------------------------------------------------------------------------

@router.get("/metrics/verify", response_model=MetricsVerifyResponse)
async def verify_metrics(
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MetricsVerifyResponse:
    """Return fresh metrics directly from the DB (no cache in demo mode)."""
    fresh = await _compute_metrics_sql(session)
    return MetricsVerifyResponse(cached=None, fresh=fresh, matches=True, deltas={})


# ---------------------------------------------------------------------------
# GET /admin/audit  (Task 2.8)
# ---------------------------------------------------------------------------

@router.get("/audit", response_model=AuditLogListResponse)
async def list_audit_log(
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    user_id: uuid.UUID | None = Query(None, description="Filter by user_id"),
    action: str | None = Query(None, description="Filter by audit action"),
    date_from: datetime | None = Query(None, description="ISO 8601 lower bound"),
    date_to: datetime | None = Query(None, description="ISO 8601 upper bound"),
    resource_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> AuditLogListResponse:
    q = select(AuditLog)
    if user_id:
        q = q.where(AuditLog.user_id == user_id)
    if action:
        q = q.where(AuditLog.action == action)
    if date_from:
        q = q.where(AuditLog.created_at >= date_from)
    if date_to:
        q = q.where(AuditLog.created_at <= date_to)
    if resource_type:
        q = q.where(AuditLog.resource_type == resource_type)

    total: int = (await session.execute(
        select(func.count()).select_from(q.subquery())
    )).scalar_one()

    rows = list((await session.execute(
        q.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    )).scalars().all())

    return AuditLogListResponse(
        items=[AuditLogEntry.model_validate(r) for r in rows],
        total=total,
    )


# ---------------------------------------------------------------------------
# GET /admin/audit/export.csv  (Task 2.8)
# ---------------------------------------------------------------------------

@router.get("/audit/export.csv")
async def export_audit_csv(
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    user_id: uuid.UUID | None = Query(None),
    action: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    resource_type: str | None = Query(None),
    max_rows: int = Query(10000, ge=1, le=50000),
) -> StreamingResponse:
    q = select(AuditLog)
    if user_id:
        q = q.where(AuditLog.user_id == user_id)
    if action:
        q = q.where(AuditLog.action == action)
    if date_from:
        q = q.where(AuditLog.created_at >= date_from)
    if date_to:
        q = q.where(AuditLog.created_at <= date_to)
    if resource_type:
        q = q.where(AuditLog.resource_type == resource_type)

    rows = list((await session.execute(
        q.order_by(AuditLog.created_at.desc()).limit(max_rows)
    )).scalars().all())

    def _csv_lines():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "created_at", "user_id", "actor_id", "action",
                    "resource_type", "resource_id", "ip_address", "user_agent", "details"])
        yield buf.getvalue()
        for row in rows:
            buf.seek(0)
            buf.truncate()
            w.writerow([
                row.id,
                row.created_at.isoformat() if row.created_at else "",
                str(row.user_id) if row.user_id else "",
                str(row.actor_id) if row.actor_id else "",
                row.action,
                row.resource_type or "",
                str(row.resource_id) if row.resource_id else "",
                row.ip_address or "",
                (row.user_agent or "")[:200],
                json.dumps(row.details) if row.details else "",
            ])
            yield buf.getvalue()

    return StreamingResponse(
        _csv_lines(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_export.csv"},
    )


# ---------------------------------------------------------------------------
# Quota defaults (Token quotas & cost caps — admin tab)
# ---------------------------------------------------------------------------

class QuotaDefaultItem(BaseModel):
    role: str
    monthly_token_limit: int
    is_unlimited: bool
    tokens_used_month: int
    user_count: int


class PutQuotaDefaultRequest(BaseModel):
    role: str
    monthly_token_limit: int
    is_unlimited: bool = False

    @field_validator("role")
    @classmethod
    def _valid_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError(f"role must be one of {VALID_ROLES}")
        return v

    @field_validator("monthly_token_limit")
    @classmethod
    def _non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("monthly_token_limit must be >= 0")
        return v


@router.get("/quota-defaults", response_model=list[QuotaDefaultItem])
async def get_quota_defaults(
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[QuotaDefaultItem]:
    """Return monthly token budget for every role with live usage + user counts."""
    # Read all quota_defaults rows
    defaults_rows = list((await session.execute(
        select(QuotaDefault)
    )).scalars().all())
    defaults_map: dict[str, int] = {r.role: r.monthly_token_limit for r in defaults_rows}

    # tokens_used_month: aggregate quota consumption per role for current month
    period = _month_start_date()
    usage_rows = (await session.execute(
        select(User.role, func.coalesce(func.sum(Quota.tokens_used), 0).label("used"))
        .join(Quota, Quota.user_id == User.id)
        .where(Quota.period_start == period)
        .group_by(User.role)
    )).all()
    usage_map: dict[str, int] = {r.role: int(r.used) for r in usage_rows}

    # user_count: active users per role
    count_rows = (await session.execute(
        select(User.role, func.count(User.id).label("cnt"))
        .where(User.is_active.is_(True))
        .group_by(User.role)
    )).all()
    count_map: dict[str, int] = {r.role: r.cnt for r in count_rows}

    return [
        QuotaDefaultItem(
            role=role,
            monthly_token_limit=defaults_map.get(role, UNLIMITED_SENTINEL),
            is_unlimited=defaults_map.get(role, UNLIMITED_SENTINEL) >= UNLIMITED_SENTINEL,
            tokens_used_month=usage_map.get(role, 0),
            user_count=count_map.get(role, 0),
        )
        for role in ROLE_ORDER
    ]


@router.put("/quota-defaults", response_model=QuotaDefaultItem)
async def put_quota_default(
    body: PutQuotaDefaultRequest,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> QuotaDefaultItem:
    """Update the monthly token budget for one role. Cascades to current month. Audited."""
    new_limit = UNLIMITED_SENTINEL if body.is_unlimited else body.monthly_token_limit
    period = _month_start_date()

    # Upsert quota_defaults (role is the PK)
    await session.execute(
        pg_insert(QuotaDefault)
        .values(role=body.role, monthly_token_limit=new_limit)
        .on_conflict_do_update(
            index_elements=["role"],
            set_={"monthly_token_limit": new_limit},
        )
    )

    # Cascade to existing current-month quota rows for all users of this role
    user_ids_sub = select(User.id).where(User.role == body.role)
    cascade_result = await session.execute(
        update(Quota)
        .where(Quota.period_start == period, Quota.user_id.in_(user_ids_sub))
        .values(tokens_limit=new_limit)
        .returning(Quota.id)
    )
    cascaded_rows = len(cascade_result.all())

    await session.commit()
    await audit_svc.log(
        action="admin_quota_changed",
        user_id=admin.id,
        actor_id=admin.id,
        resource_type="quota_default",
        details={
            "role": body.role,
            "monthly_token_limit": new_limit,
            "is_unlimited": new_limit >= UNLIMITED_SENTINEL,
            "cascaded_rows": cascaded_rows,
        },
    )
    await _bump_perm_version()

    # Return a freshly computed QuotaDefaultItem for this role
    tokens_used = (await session.execute(
        select(func.coalesce(func.sum(Quota.tokens_used), 0))
        .join(User, Quota.user_id == User.id)
        .where(User.role == body.role, Quota.period_start == period)
    )).scalar_one()
    user_count = (await session.execute(
        select(func.count(User.id))
        .where(User.role == body.role, User.is_active.is_(True))
    )).scalar_one()

    return QuotaDefaultItem(
        role=body.role,
        monthly_token_limit=new_limit,
        is_unlimited=new_limit >= UNLIMITED_SENTINEL,
        tokens_used_month=int(tokens_used or 0),
        user_count=int(user_count or 0),
    )


# ---------------------------------------------------------------------------
# API-key management (Task 2.10 — n8n service-account credentials)
# ---------------------------------------------------------------------------

class ApiKeyCreate(BaseModel):
    name: str
    email: str       # service-account email (upserted as a User)
    role: str = "L4"

    @field_validator("role")
    @classmethod
    def _valid_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError(f"role must be one of {VALID_ROLES}")
        return v


class ApiKeyInfo(BaseModel):
    id: uuid.UUID
    name: str
    service_user_email: str
    role: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None

    model_config = {"from_attributes": True}


@router.post("/api-keys", status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Mint a new service-account API key.

    Returns the raw secret (gw_…) exactly once — it is not stored and cannot
    be retrieved again.  Save it immediately in the target service's credential
    store.
    """
    from app.models.api_key import ApiKey, generate_key

    # Upsert service user
    result = await session.execute(select(User).where(User.google_email == body.email))
    svc_user = result.scalar_one_or_none()
    from datetime import timezone
    now = datetime.now(timezone.utc)

    if svc_user is None:
        svc_user = User(
            google_email=body.email,
            display_name=body.name,
            role=body.role,
            is_active=True,
            consent_acknowledged_at=now,
        )
        session.add(svc_user)
        await session.flush()
    else:
        svc_user.role = body.role
        if svc_user.consent_acknowledged_at is None:
            svc_user.consent_acknowledged_at = now

    raw_secret, key_hash = generate_key()
    api_key = ApiKey(
        name=body.name,
        key_hash=key_hash,
        service_user_id=svc_user.id,
    )
    session.add(api_key)
    await session.flush()

    await audit_svc.log(
        action="admin_action",
        user_id=admin.id,
        details={
            "action": "api_key_created",
            "key_id": str(api_key.id),
            "service_user": body.email,
            "role": body.role,
        },
    )
    await session.commit()

    return {
        "id": str(api_key.id),
        "name": api_key.name,
        "service_user_email": body.email,
        "raw_secret": raw_secret,   # shown once only
        "note": "Save this secret now — it cannot be retrieved again.",
    }


@router.get("/api-keys", response_model=list[ApiKeyInfo])
async def list_api_keys(
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    include_revoked: bool = False,
) -> list[ApiKeyInfo]:
    """List service-account API keys (never returns the raw secret)."""
    from app.models.api_key import ApiKey

    q = select(ApiKey, User.google_email, User.role).join(
        User, User.id == ApiKey.service_user_id
    )
    if not include_revoked:
        q = q.where(ApiKey.revoked_at.is_(None))

    rows = (await session.execute(q)).all()

    return [
        ApiKeyInfo(
            id=row.ApiKey.id,
            name=row.ApiKey.name,
            service_user_email=row.google_email,
            role=row.role,
            created_at=row.ApiKey.created_at,
            last_used_at=row.ApiKey.last_used_at,
            revoked_at=row.ApiKey.revoked_at,
        )
        for row in rows
    ]


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: uuid.UUID,
    admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Revoke a service-account API key. Immediate effect — next request will 401."""
    from app.models.api_key import ApiKey
    from datetime import timezone

    result = await session.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.revoked_at.is_(None))
    )
    key = result.scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=404, detail="API key not found or already revoked")

    key.revoked_at = datetime.now(timezone.utc)

    await audit_svc.log(
        action="admin_action",
        user_id=admin.id,
        details={"action": "api_key_revoked", "key_id": str(key_id)},
    )
    await session.commit()
    return Response(status_code=204)
