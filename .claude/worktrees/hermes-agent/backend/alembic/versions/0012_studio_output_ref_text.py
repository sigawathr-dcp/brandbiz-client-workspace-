"""Widen studio_generations.output_ref from VARCHAR(4000) to TEXT

Image data URLs from Gemini can exceed 1 MB (base64-encoded PNG/JPEG),
which overflows the original VARCHAR(4000) limit and causes a
StringDataRightTruncationError on INSERT.  TEXT is unbounded and is a
metadata-only change in PostgreSQL (no table rewrite required).

Revision ID: 0012_studio_output_ref_text
Revises: 0011_studio_generations
Create Date: 2026-06-21

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0012_studio_output_ref_text"
down_revision: Union[str, None] = "0011_studio_generations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE studio_generations
            ALTER COLUMN output_ref TYPE TEXT
    """)


def downgrade() -> None:
    # NOTE: this will fail if any rows contain output_ref > 4000 chars.
    op.execute("""
        ALTER TABLE studio_generations
            ALTER COLUMN output_ref TYPE VARCHAR(4000)
    """)
