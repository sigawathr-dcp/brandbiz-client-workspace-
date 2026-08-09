"""Add 'hermes' to model_provider enum

Split into its own migration (see Gotcha #5 in PLAN.md): ALTER TYPE ... ADD
VALUE cannot be used in the same transaction as a statement that references
the new value, so the catalog row + permissions insert live in the next
migration (0030_hermes_model_catalog). This repo's env.py runs the whole
`alembic upgrade head` batch in a single transaction (no
transaction_per_migration), so a plain file split isn't enough on its own —
this migration explicitly COMMITs so the new value is visible to 0030.

Revision ID: 0029_hermes_provider_enum
Revises: 0028_vault_connection
Create Date: 2026-07-13
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0029_hermes_provider_enum"
down_revision: Union[str, None] = "0028_vault_connection"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE model_provider ADD VALUE IF NOT EXISTS 'hermes'")
    op.execute("COMMIT")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE; removing an enum value requires
    # rebuilding the type. Left as a no-op — the value stays but nothing uses it
    # once 0030's downgrade removes the only row that references it.
    pass
