"""Create leads table (Phase 5 §5, D21/D22) — expert handoff CTA

Revision ID: 0043_leads
Revises: 0042_plans_and_rate_card
Create Date: 2026-07-30
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0043_leads"
down_revision: Union[str, None] = "0042_plans_and_rate_card"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id                     UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id           UUID          NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            user_id                UUID          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            plan_id                UUID          REFERENCES plans(id) ON DELETE SET NULL,
            contact_name           VARCHAR(255),
            contact_phone_or_line  VARCHAR(64),
            best_time              VARCHAR(255),
            status                 VARCHAR(16)   NOT NULL DEFAULT 'new',
            assigned_to            UUID          REFERENCES users(id) ON DELETE SET NULL,
            n8n_response           JSONB,
            n8n_error              VARCHAR(500),
            created_at             TIMESTAMPTZ   NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_leads_workspace_id
        ON leads (workspace_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_leads_status
        ON leads (status)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS leads")
