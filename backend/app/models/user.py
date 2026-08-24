import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import ENUM as PgEnum, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# References the type created by Alembic 0001_baseline — do not recreate it
_role_level_pg = PgEnum(
    "L1", "L2", "L3", "L4", "L5", "L6", "ADMIN",
    name="role_level",
    create_type=False,
)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # "One seat per LINE identity" (migration 0063), as a database
        # invariant rather than an application check — a read-then-write in
        # provision_line_seat can be raced by a double-tapped login button;
        # this cannot. Partial so the many NULLs (internal staff, and every
        # seat from the older invite-redemption path) stay unconstrained.
        Index(
            "uq_users_line_user_id",
            "line_user_id",
            unique=True,
            postgresql_where=text("line_user_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    google_email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(_role_level_pg, nullable=False, server_default="L1")
    # NULL = internal staff (unchanged pre-D21/D22 behavior). Set = a client
    # workspace seat — see app/services/workspace.py::workspace_visibility_filter.
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Verified `sub` from a LINE Login id_token (0063). UNIQUE where NOT
    # NULL — this is what makes "one seat per LINE user" a database
    # invariant instead of an application check. NULL for internal staff and
    # for seats created by the older invite-redemption path.
    line_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # G-A1/G-A2/G-A3 composer selections (model, mode, reasoning_level), merged
    # on write via PATCH /auth/me/preferences — see app/routers/auth.py.
    preferences: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )
