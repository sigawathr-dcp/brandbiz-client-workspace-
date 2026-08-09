"""Add scope column to files table

Revision ID: 0008_file_scope
Revises: 0007_fix_l1_perms
Create Date: 2026-06-08

Note: tables ``files`` and ``file_chunks`` were already created by 0001_baseline.
This migration only adds the ``scope`` column (VARCHAR, not a PG enum — see
PLAN.md Gotcha #5: PG enum values are painful to alter).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0008_file_scope"
down_revision: Union[str, None] = "0007_fix_l1_perms"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE files
        ADD COLUMN IF NOT EXISTS scope VARCHAR(16) NOT NULL DEFAULT 'personal'
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE files DROP COLUMN IF EXISTS scope")
