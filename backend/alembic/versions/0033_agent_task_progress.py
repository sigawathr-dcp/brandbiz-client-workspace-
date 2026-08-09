"""Add agent_task progress columns (live activity log for background tasks)

Task 3.12 follow-on: the Tasks page shows Hermes's live activity log and
partial output while a task is still running, not just the terminal result.
The worker throttled-flushes an AES-256-GCM encrypted snapshot of the
accumulated log to these columns every ~2s while status == "running"
(app/services/agent_tasks.py), then clears them once the task reaches a
terminal state -- result_ciphertext / error_text become the durable record
at that point.

Same encrypted-quad pattern as prompt_*/result_* on this table (0032) and
message content (0001_baseline) -- see 0032's docstring for the general
VARCHAR-status / encryption conventions this table follows.

All new columns are nullable -- no backfill needed, no COMMIT needed (VARCHAR/
BYTEA, no PG enum touched).

Revision ID: 0033_agent_task_progress
Revises: 0032_agent_task
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0033_agent_task_progress"
down_revision: Union[str, None] = "0032_agent_task"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE agent_task
            ADD COLUMN IF NOT EXISTS progress_ciphertext  BYTEA,
            ADD COLUMN IF NOT EXISTS progress_nonce        BYTEA,
            ADD COLUMN IF NOT EXISTS progress_tag          BYTEA,
            ADD COLUMN IF NOT EXISTS progress_key_version  INTEGER
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE agent_task
            DROP COLUMN IF EXISTS progress_ciphertext,
            DROP COLUMN IF EXISTS progress_nonce,
            DROP COLUMN IF EXISTS progress_tag,
            DROP COLUMN IF EXISTS progress_key_version
    """)
