"""Create agent_task table (Task 3.12 -- Cowork-style background tasks)

Backs unattended task execution via Hermes Agent: a task is submitted,
runs server-side via FastAPI BackgroundTasks (no Celery in demo mode -- D9),
and is polled for status until it reaches a terminal state. Mirrors the
vault_sync_run / studio_generations pattern: status is a plain VARCHAR
enforced in the service layer (Gotcha #5), not a PG enum.

Prompt and result are AES-256-GCM encrypted at rest (ciphertext/nonce/tag/
key_version columns), the same scheme used for message content (0001_baseline
`messages` table) and studio prompts (0014).

schedule_cron / next_run_at / last_run_at are nullable placeholders for a
future Phase 2 (recurring tasks) -- unused, never written by Phase 1 code.

Revision ID: 0032_agent_task
Revises: 0031_agent_task_audit_actions
Create Date: 2026-07-13
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0032_agent_task"
down_revision: Union[str, None] = "0031_agent_task_audit_actions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_task (
            id                   UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id              UUID          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            conversation_id      UUID          REFERENCES conversations(id) ON DELETE SET NULL,
            title                VARCHAR(500),
            prompt_ciphertext    BYTEA         NOT NULL,
            prompt_nonce         BYTEA         NOT NULL,
            prompt_tag           BYTEA         NOT NULL,
            key_version          INTEGER       NOT NULL DEFAULT 1,
            result_ciphertext    BYTEA,
            result_nonce         BYTEA,
            result_tag           BYTEA,
            result_key_version   INTEGER,
            status               VARCHAR(24)   NOT NULL DEFAULT 'queued',
            downgrade_to_local   BOOLEAN       NOT NULL DEFAULT false,
            model_used           VARCHAR(100),
            tokens_input         INTEGER,
            tokens_output        INTEGER,
            cost_usd             NUMERIC(10,6),
            error_text           TEXT,
            schedule_cron        VARCHAR(100),
            next_run_at          TIMESTAMPTZ,
            last_run_at          TIMESTAMPTZ,
            created_at           TIMESTAMPTZ   NOT NULL DEFAULT now(),
            updated_at           TIMESTAMPTZ   NOT NULL DEFAULT now(),
            finished_at          TIMESTAMPTZ
        )
    """)
    # List/poll views filter by owner + recency; the composite index also serves
    # a plain user_id lookup via its leftmost prefix, so a separate single-column
    # index on user_id is unnecessary.
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_agent_task_user_id_created_at
        ON agent_task (user_id, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_agent_task_status ON agent_task (status)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_agent_task_status")
    op.execute("DROP INDEX IF EXISTS ix_agent_task_user_id_created_at")
    op.execute("DROP INDEX IF EXISTS ix_agent_task_user_id")
    op.execute("DROP TABLE IF EXISTS agent_task")
