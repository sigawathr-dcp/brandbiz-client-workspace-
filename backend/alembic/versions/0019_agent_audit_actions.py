"""Add agent audit_action enum values

Revision ID: 0019_agent_audit_actions
Revises: 0018_agents
Create Date: 2026-06-22
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0019_agent_audit_actions"
down_revision: Union[str, None] = "0018_agents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'agent_created'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'agent_updated'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'agent_deleted'")


def downgrade() -> None:
    # Postgres does not support removing enum values; residual labels are harmless.
    pass
