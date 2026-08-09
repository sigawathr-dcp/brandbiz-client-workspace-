"""Add studio audit_action enum values

Adds actions used by the studio service (image/video generation events)
that were missing from the baseline audit_action enum.

Revision ID: 0014_studio_audit_actions
Revises: 0013_veo_video_model
Create Date: 2026-06-22

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0014_studio_audit_actions"
down_revision: Union[str, None] = "0013_veo_video_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'studio_image_denied'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'studio_generate_requested'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'studio_image_generated'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'studio_video_denied'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'studio_video_generated'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'studio_video_failed'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'studio_generate_mocked'")


def downgrade() -> None:
    # Postgres does not support removing enum values; residual labels are harmless.
    pass
