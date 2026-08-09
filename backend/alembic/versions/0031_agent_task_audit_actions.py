"""Add audit_action enum values for Task 3.12 background agent tasks

New action strings emitted by app/services/agent_tasks.py as a task moves
through its lifecycle (submitted -> running -> succeeded/failed/cancelled).

Gotcha #5 note: ALTER TYPE ... ADD VALUE is non-transactional and cannot be
used in the same transaction as a statement that references the new value.
This repo's env.py runs the whole `alembic upgrade head` batch in a single
transaction, so that matters whenever a later migration in the same run
INSERTs a row using one of these values (see 0029_hermes_provider_enum.py,
which needs an explicit COMMIT for exactly that reason). It does NOT apply
here: this migration only adds the labels, and 0032_agent_task.py (the next
migration) only creates a table -- neither references these values in SQL.
The values are first used at application runtime, in a separate transaction
entirely. Same reasoning as 0028_vault_connection.py's enum additions.

Revision ID: 0031_agent_task_audit_actions
Revises: 0030_hermes_model_catalog
Create Date: 2026-07-13
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0031_agent_task_audit_actions"
down_revision: Union[str, None] = "0030_hermes_model_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_ACTIONS = (
    "agent_task_submitted",
    "agent_task_running",
    "agent_task_succeeded",
    "agent_task_failed",
    "agent_task_cancelled",
)


def upgrade() -> None:
    for action in _NEW_ACTIONS:
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{action}'")


def downgrade() -> None:
    # audit_action enum values are not removed (PG can't DROP enum values
    # easily; same documented no-op as 0028_vault_connection.py/downgrade).
    pass
