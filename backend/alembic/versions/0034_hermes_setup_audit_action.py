"""Add audit_action enum value for Task 3.13 Hermes setup-script downloads

The downloadable install-hermes.ps1 embeds HERMES_API_KEY (it becomes
Hermes's own API_SERVER_KEY), so every download is audit-logged by
app/routers/hermes.py as 'hermes_setup_script_downloaded'.

Gotcha #5 note: no explicit COMMIT needed — nothing in this upgrade run
references the new value in SQL; it is first used at application runtime.
Same reasoning as 0031_agent_task_audit_actions.py.

Revision ID: 0034_hermes_setup_audit_action
Revises: 0033_agent_task_progress
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0034_hermes_setup_audit_action"
down_revision: Union[str, None] = "0033_agent_task_progress"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'hermes_setup_script_downloaded'"
    )


def downgrade() -> None:
    # audit_action enum values are not removed (PG can't DROP enum values
    # easily; same documented no-op as 0031_agent_task_audit_actions.py).
    pass
