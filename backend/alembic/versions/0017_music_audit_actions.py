"""Add music studio audit_action enum values

Adds actions used by the music generation path in the studio service
(studio_music_denied, studio_music_generated, studio_music_failed).

Revision ID: 0017_music_audit_actions
Revises: 0016_lyria_music_model
Create Date: 2026-06-22

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0017_music_audit_actions"
down_revision: Union[str, None] = "0016_lyria_music_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'studio_music_denied'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'studio_music_generated'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'studio_music_failed'")


def downgrade() -> None:
    # Postgres does not support removing enum values; residual labels are harmless.
    pass
