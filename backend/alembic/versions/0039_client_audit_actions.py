"""Add client-workspace audit_action enum values (Phase 5, D21/D22)

Gotcha #5 note: no explicit COMMIT needed — nothing in this upgrade run
references the new values in SQL; they are first used at application
runtime. Same reasoning as 0034_hermes_setup_audit_action.py.

Revision ID: 0039_client_audit_actions
Revises: 0038_client_workspaces
Create Date: 2026-07-30
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0039_client_audit_actions"
down_revision: Union[str, None] = "0038_client_workspaces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'client_invited'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'client_redeemed'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'intake_answered'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'research_run'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'case_matched'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'plan_created'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'plan_updated'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'plan_shared'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'plan_exported'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'lead_submitted'")


def downgrade() -> None:
    # Postgres does not support removing enum values; residual labels are harmless.
    pass
