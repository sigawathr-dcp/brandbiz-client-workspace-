"""Create hermes_host_job table + audit actions (Task 3.14 -- one-click native setup)

Backs the Tasks-page "Set up Hermes now" button: an ADMIN click enqueues a
job row; a host helper (polling outbound with a service-account API key)
claims it, runs its single hardcoded install/start-Hermes routine, and
reports progress into log_text. The row is a trigger + status record only —
it never carries anything executable, and the helper never writes secrets
into the log. status is a plain VARCHAR enforced in the service layer
(Gotcha #5), same as agent_task.

Also adds two audit_action values. No explicit COMMIT needed: nothing in this
upgrade run references the new enum values in SQL (first used at app runtime)
— same reasoning as 0031/0034.

Revision ID: 0035_hermes_host_job
Revises: 0034_hermes_setup_audit_action
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0035_hermes_host_job"
down_revision: Union[str, None] = "0034_hermes_setup_audit_action"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_ACTIONS = (
    "hermes_host_job_created",
    "hermes_helper_script_downloaded",
)


def upgrade() -> None:
    for action in _NEW_ACTIONS:
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{action}'")
    op.execute("""
        CREATE TABLE IF NOT EXISTS hermes_host_job (
            id           UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            kind         VARCHAR(30)   NOT NULL DEFAULT 'setup',
            status       VARCHAR(30)   NOT NULL DEFAULT 'queued',
            created_by   UUID          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            log_text     TEXT,
            created_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
            updated_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
            claimed_at   TIMESTAMPTZ,
            finished_at  TIMESTAMPTZ
        )
    """)
    # The helper's claim query and the banner's "latest" query both filter by
    # status / order by recency on a table that will only ever hold a handful
    # of rows — one composite index covers both.
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_hermes_host_job_status_created_at
        ON hermes_host_job (status, created_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_hermes_host_job_status_created_at")
    op.execute("DROP TABLE IF EXISTS hermes_host_job")
    # audit_action enum values are not removed (PG can't DROP enum values
    # easily; same documented no-op as 0031/0034).
