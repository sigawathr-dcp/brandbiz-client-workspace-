"""Add parent_id to studio_generations for edit/regenerate lineage

Lets a generation record which prior generation it was derived from
(image edit-with-reference, or video/music regenerate-with-tweaked-prompt).
Self-referencing FK; ON DELETE SET NULL so deleting a parent never cascades
and orphans children as standalone rows instead.

Revision ID: 0026_studio_generation_parent_id
Revises: 0025_hide_truehub_branding
Create Date: 2026-07-06

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0026_studio_generation_parent_id"
down_revision: Union[str, None] = "0025_hide_truehub_branding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE studio_generations
            ADD COLUMN IF NOT EXISTS parent_id UUID
                REFERENCES studio_generations(id) ON DELETE SET NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_studio_generations_parent_id
        ON studio_generations (parent_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_studio_generations_parent_id")
    op.execute("ALTER TABLE studio_generations DROP COLUMN IF EXISTS parent_id")
