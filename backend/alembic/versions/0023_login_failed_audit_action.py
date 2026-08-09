"""Add login_failed to audit_action enum

Revision ID: 0023_login_failed_audit_action
Revises: 0022_user_password_auth
Create Date: 2026-07-01

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0023_login_failed_audit_action"
down_revision: Union[str, None] = "0022_user_password_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'login_failed'")


def downgrade() -> None:
    pass
