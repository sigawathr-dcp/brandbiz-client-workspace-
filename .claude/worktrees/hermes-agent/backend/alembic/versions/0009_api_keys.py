"""Add api_keys table for service-account authentication (n8n integration).

Revision ID: 0009_api_keys
Revises: 0008_file_scope
Create Date: 2026-06-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0009_api_keys"
down_revision: Union[str, None] = "0008_file_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extend audit_action enum with n8n integration event
    # (Postgres ADD VALUE cannot run inside a transaction — execute outside)
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'n8n_triggered'")

    op.create_table(
        "api_keys",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True, comment="SHA-256 hex of the raw secret"),
        sa.Column(
            "service_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_api_keys_service_user_id", "api_keys", ["service_user_id"])


def downgrade() -> None:
    op.drop_index("ix_api_keys_service_user_id", table_name="api_keys")
    op.drop_table("api_keys")
