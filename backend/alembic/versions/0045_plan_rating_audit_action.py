"""Add 'plan_rated' audit_action enum value (PLAN.md Task 5.10)

Gotcha #5 note: no explicit COMMIT needed — nothing in this upgrade run
references the new value in SQL; it is first used at application runtime.
Same reasoning as 0034_hermes_setup_audit_action.py / 0039_client_audit_actions.py.

Revision ID: 0045_plan_rating_audit_action
Revises: 0044_plan_ratings
Create Date: 2026-08-09
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0045_plan_rating_audit_action"
down_revision: Union[str, None] = "0044_plan_ratings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'plan_rated'")


def downgrade() -> None:
    # Postgres does not support removing enum values; residual label is harmless.
    pass
