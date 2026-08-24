"""Create engagements + engagement_steps; add scaffolding columns (DB redesign, stage 1)

First stage of the "Client Workspace — Database Redesign": before this,
there was no row anywhere representing "one client's run through the
4-step funnel" (Interview -> Market scan -> Case match -> Plan & budget) —
the four step tables (client_profiles/research_runs/case_matches/plans)
were glued together only by repeating (workspace_id, user_id,
conversation_id) on each one, and the journey itself was reconstructed
from scratch in the browser (frontend-chat/components/client/journey.ts).

This migration only ADDS structure — nothing is dropped or backfilled yet
(that's 0051). `engagement_id` added here to research_runs/case_matches is
scaffolding: those two tables' FINAL shape (migration 0054/0055) points at
engagement_steps, not engagements directly, but engagement_id is needed as
an intermediate join key during backfill before engagement_steps rows
exist for those tables' rows. It is dropped again in 0057. On `plans` and
`leads`, by contrast, engagement_id is a PERMANENT column.

Revision ID: 0050_engagements
Revises: 0049_plan_version_snapshot
Create Date: 2026-08-15
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0050_engagements"
down_revision: Union[str, None] = "0049_plan_version_snapshot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS engagements (
            id                 UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id       UUID          NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            user_id            UUID          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            seq                INTEGER       NOT NULL DEFAULT 1,
            conversation_id    UUID          REFERENCES conversations(id) ON DELETE SET NULL,
            intake_script_id   UUID,
            active_plan_id     UUID,
            status             VARCHAR(16)   NOT NULL DEFAULT 'active',
            created_at         TIMESTAMPTZ   NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ   NOT NULL DEFAULT now(),
            completed_at       TIMESTAMPTZ,
            CONSTRAINT uq_engagements_workspace_user_seq UNIQUE (workspace_id, user_id, seq)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_engagements_workspace_id ON engagements (workspace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_engagements_user_id ON engagements (user_id)")
    # Partial unique index: at most one ACTIVE engagement per seat, but
    # unlimited completed/abandoned ones — replaces client_profiles' old
    # UNIQUE(workspace_id, user_id), which capped a seat at exactly one
    # intake forever.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_engagements_one_active_per_seat
        ON engagements (workspace_id, user_id)
        WHERE status = 'active'
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS engagement_steps (
            id                 UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            engagement_id      UUID          NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
            step_no            SMALLINT      NOT NULL,
            step_key           VARCHAR(16)   NOT NULL,
            status             VARCHAR(16)   NOT NULL DEFAULT 'idle',
            progress_current   SMALLINT,
            progress_total     SMALLINT,
            attempt_count      INTEGER       NOT NULL DEFAULT 0,
            started_at         TIMESTAMPTZ,
            completed_at       TIMESTAMPTZ,
            error_code         VARCHAR(64),
            error_detail       TEXT,
            CONSTRAINT uq_engagement_steps_engagement_step UNIQUE (engagement_id, step_no),
            CONSTRAINT ck_engagement_steps_step_no_range CHECK (step_no BETWEEN 1 AND 4)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_engagement_steps_engagement_id ON engagement_steps (engagement_id)")

    # Scaffolding FK on research_runs/case_matches — dropped in 0057 once
    # engagement_step_id (added in 0054/0055) supersedes it.
    op.execute("ALTER TABLE research_runs ADD COLUMN IF NOT EXISTS engagement_id UUID")
    op.execute("ALTER TABLE case_matches ADD COLUMN IF NOT EXISTS engagement_id UUID")

    # Permanent columns on plans/leads.
    op.execute("""
        ALTER TABLE plans ADD COLUMN IF NOT EXISTS engagement_id UUID
        REFERENCES engagements(id) ON DELETE SET NULL
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_plans_engagement_id ON plans (engagement_id)")
    op.execute("""
        ALTER TABLE leads ADD COLUMN IF NOT EXISTS engagement_id UUID
        REFERENCES engagements(id) ON DELETE SET NULL
    """)

    # Permanent columns on conversations — workspace_id denormalizes the
    # join through `users` (Gotcha noted in the redesign plan); engagement_id
    # + kind let a conversation identify itself as a client-workspace
    # funnel thread without inferring it from workspace_id being set.
    op.execute("""
        ALTER TABLE conversations ADD COLUMN IF NOT EXISTS workspace_id UUID
        REFERENCES workspaces(id) ON DELETE SET NULL
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_conversations_workspace_id ON conversations (workspace_id)")
    op.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS engagement_id UUID")
    op.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS kind VARCHAR(24) NOT NULL DEFAULT 'internal'")

    # Which chapter a chat turn belongs to (client-workspace threads only).
    op.execute("""
        ALTER TABLE messages ADD COLUMN IF NOT EXISTS engagement_step_id UUID
        REFERENCES engagement_steps(id) ON DELETE SET NULL
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE messages DROP COLUMN IF EXISTS engagement_step_id")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS kind")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS engagement_id")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS workspace_id")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS engagement_id")
    op.execute("ALTER TABLE plans DROP COLUMN IF EXISTS engagement_id")
    op.execute("ALTER TABLE case_matches DROP COLUMN IF EXISTS engagement_id")
    op.execute("ALTER TABLE research_runs DROP COLUMN IF EXISTS engagement_id")
    op.execute("DROP TABLE IF EXISTS engagement_steps")
    op.execute("DROP TABLE IF EXISTS engagements")
