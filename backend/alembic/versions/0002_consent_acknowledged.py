"""Add consent_acknowledged_at to users and consent_acknowledged to audit_action

Revision ID: 0002_consent_acknowledged
Revises: 0001_baseline
Create Date: 2026-06-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_consent_acknowledged"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PG 16 allows ALTER TYPE ... ADD VALUE inside a transaction.
    # IF NOT EXISTS prevents errors on re-run (e.g., partial upgrades).
    op.execute(
        "ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'consent_acknowledged'"
    )

    op.add_column(
        "users",
        sa.Column("consent_acknowledged_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "consent_acknowledged_at")
    # Postgres does not support removing enum values; the residual label is harmless.
