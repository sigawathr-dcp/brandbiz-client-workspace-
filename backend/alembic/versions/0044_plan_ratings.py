"""Create plan_ratings table (PLAN.md Task 5.10) — client NPS rating on a
saved plan, surfaced to staff on the expert leads inbox before the call.

Revision ID: 0044_plan_ratings
Revises: 0043_leads
Create Date: 2026-08-09
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0044_plan_ratings"
down_revision: Union[str, None] = "0043_leads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS plan_ratings (
            id            UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            plan_id       UUID          NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
            workspace_id  UUID          NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            user_id       UUID          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            score         INTEGER       NOT NULL CHECK (score BETWEEN 1 AND 10),
            comment       VARCHAR(2000),
            created_at    TIMESTAMPTZ   NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ   NOT NULL DEFAULT now(),
            CONSTRAINT uq_plan_ratings_plan_user UNIQUE (plan_id, user_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_plan_ratings_plan_id
        ON plan_ratings (plan_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_plan_ratings_workspace_id
        ON plan_ratings (workspace_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS plan_ratings")
