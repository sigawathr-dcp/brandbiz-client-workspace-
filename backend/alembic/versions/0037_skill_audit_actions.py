"""Add skill audit_action enum values

Revision ID: 0037_skill_audit_actions
Revises: 0036_skills
Create Date: 2026-07-17
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0037_skill_audit_actions"
down_revision: Union[str, None] = "0036_skills"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'skill_created'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'skill_updated'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'skill_deleted'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'skill_invoked'")


def downgrade() -> None:
    # Postgres does not support removing enum values; residual labels are harmless.
    pass
