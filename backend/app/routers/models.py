from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.llm.router import LOCAL_MODEL_CODE, get_router
from app.models.department import UserDepartment
from app.models.model_catalog import ModelCatalog
from app.models.permission import DepartmentModelPermission, RoleModelPermission
from app.models.user import User

router = APIRouter(prefix="/models", tags=["models"])


class ModelOption(BaseModel):
    code: str
    display_name: str
    provider: str
    is_local: bool
    # G-A2: whether this model can honor a reasoning-level request, so the
    # frontend can grey out the control per model. Computed from the live
    # LLMClient rather than a model_catalog column — see app.llm.tuning
    # module docstring for why a DB column would be wrong for aliased codes
    # (e.g. "Gemini 2.5 Pro" -> gemini-2.5-flash under the hood).
    supports_reasoning: bool = False


def _supports_reasoning(code: str) -> bool:
    try:
        return get_router().get(code).supports_reasoning
    except KeyError:
        return False


@router.get("/available", response_model=list[ModelOption])
async def available_models(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[ModelOption]:
    """Return models the current user is allowed to request.

    Local model is always included first. External models are the union of
    role-based and department-based permissions (D19).
    """
    # Local model — always available (Policy rule 1)
    local_row = (await session.execute(
        select(ModelCatalog).where(ModelCatalog.code == LOCAL_MODEL_CODE)
    )).scalar_one_or_none()

    local = ModelOption(
        code=LOCAL_MODEL_CODE,
        display_name=local_row.display_name if local_row else "Local (Qwen)",
        provider="local",
        is_local=True,
        supports_reasoning=_supports_reasoning(LOCAL_MODEL_CODE),
    )

    # Role-level external permissions
    role_rows = (await session.execute(
        select(ModelCatalog)
        .join(RoleModelPermission, RoleModelPermission.model_id == ModelCatalog.id)
        .where(
            and_(
                RoleModelPermission.role == user.role,
                ModelCatalog.is_local.is_(False),
                ModelCatalog.is_active.is_(True),
            )
        )
        .order_by(ModelCatalog.provider, ModelCatalog.display_name)
    )).scalars().all()

    # Department-level add-on permissions (D19: additive)
    dept_ids_rows = (await session.execute(
        select(UserDepartment.department_id).where(UserDepartment.user_id == user.id)
    )).scalars().all()
    dept_ids = list(dept_ids_rows)

    dept_rows: list[ModelCatalog] = []
    if dept_ids:
        dept_rows = (await session.execute(
            select(ModelCatalog)
            .join(DepartmentModelPermission, DepartmentModelPermission.model_id == ModelCatalog.id)
            .where(
                and_(
                    DepartmentModelPermission.department_id.in_(dept_ids),
                    ModelCatalog.is_local.is_(False),
                    ModelCatalog.is_active.is_(True),
                )
            )
            .order_by(ModelCatalog.provider, ModelCatalog.display_name)
        )).scalars().all()

    seen: set[str] = set()
    external: list[ModelOption] = []
    for row in list(role_rows) + list(dept_rows):
        if row.code not in seen:
            seen.add(row.code)
            external.append(ModelOption(
                code=row.code,
                display_name=row.display_name,
                provider=row.provider,
                is_local=row.is_local,
                supports_reasoning=_supports_reasoning(row.code),
            ))

    return [local] + external
