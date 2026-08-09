"""Create workspaces table; add workspace_id to users/files/skills/agents

Client Workspaces (D21/D22, Phase 5) — a bounded, tenant-isolated
client-facing surface sharing this single gateway instance with internal
staff. Internal users keep users.workspace_id IS NULL and are byte-identical
to pre-D21/D22 behavior; a client seat has workspace_id set and is scoped by
app/services/workspace.py::workspace_visibility_filter, applied on top of the
existing org/public visibility predicate in rag_search.py, skill.py, and
agent.py.

kind, workspace_id nullability follow the house style: no PG enum for `kind`
(Gotcha #5); workspace_id is nullable everywhere and defaults to NULL so
existing rows (all internal) require no backfill.

Revision ID: 0038_client_workspaces
Revises: 0037_skill_audit_actions
Create Date: 2026-07-30
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0038_client_workspaces"
down_revision: Union[str, None] = "0037_skill_audit_actions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS workspaces (
            id                    UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            name                  VARCHAR(255)  NOT NULL,
            slug                  VARCHAR(64)   NOT NULL,
            kind                  VARCHAR(16)   NOT NULL DEFAULT 'demo',
            line_user_id          VARCHAR(64),
            contact_name          VARCHAR(255),
            contact_email         VARCHAR(255),
            contact_phone         VARCHAR(64),
            monthly_token_limit   BIGINT,
            token_budget_limit    BIGINT,
            token_budget_used     BIGINT        NOT NULL DEFAULT 0,
            created_at            TIMESTAMPTZ   NOT NULL DEFAULT now(),
            archived_at           TIMESTAMPTZ,
            CONSTRAINT uq_workspaces_slug UNIQUE (slug)
        )
    """)

    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS workspace_id UUID
        REFERENCES workspaces(id) ON DELETE SET NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_users_workspace_id
        ON users (workspace_id)
    """)

    op.execute("""
        ALTER TABLE files
        ADD COLUMN IF NOT EXISTS workspace_id UUID
        REFERENCES workspaces(id) ON DELETE SET NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_files_workspace_id
        ON files (workspace_id)
    """)

    op.execute("""
        ALTER TABLE skills
        ADD COLUMN IF NOT EXISTS workspace_id UUID
        REFERENCES workspaces(id) ON DELETE SET NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_skills_workspace_id
        ON skills (workspace_id)
    """)

    op.execute("""
        ALTER TABLE agents
        ADD COLUMN IF NOT EXISTS workspace_id UUID
        REFERENCES workspaces(id) ON DELETE SET NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_agents_workspace_id
        ON agents (workspace_id)
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE agents DROP COLUMN IF EXISTS workspace_id")
    op.execute("ALTER TABLE skills DROP COLUMN IF EXISTS workspace_id")
    op.execute("ALTER TABLE files DROP COLUMN IF EXISTS workspace_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS workspace_id")
    op.execute("DROP TABLE IF EXISTS workspaces")
