from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# References type created by Alembic 0001_baseline — do not recreate it
_role_level_pg = PgEnum(
    "L1", "L2", "L3", "L4", "L5", "L6", "ADMIN",
    name="role_level",
    create_type=False,
)


class RoleModelPermission(Base):
    __tablename__ = "role_model_permissions"

    role: Mapped[str] = mapped_column(_role_level_pg, primary_key=True, nullable=False)
    model_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("model_catalog.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )


class DepartmentModelPermission(Base):
    __tablename__ = "department_model_permissions"

    department_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("departments.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    model_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("model_catalog.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
