"""Add users.preferences JSONB column (Gap Closure §A, preference persistence)

Revision ID: 0046_user_preferences
Revises: 0045_plan_rating_audit_action
Create Date: 2026-08-10
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0046_user_preferences"
down_revision: Union[str, None] = "0045_plan_rating_audit_action"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS preferences JSONB NOT NULL DEFAULT '{}'::jsonb
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS preferences")
