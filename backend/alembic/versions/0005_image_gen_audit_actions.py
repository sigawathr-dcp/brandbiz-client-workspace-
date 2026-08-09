"""Add image_requested and image_generated to audit_action enum

Revision ID: 0005_image_gen_audit_actions
Revises: 0004_thai_id_compact
Create Date: 2026-06-07

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005_image_gen_audit_actions"
down_revision: Union[str, None] = "0004_thai_id_compact"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'image_requested'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'image_generated'")


def downgrade() -> None:
    # Postgres does not support removing enum values; residual labels are harmless.
    pass
