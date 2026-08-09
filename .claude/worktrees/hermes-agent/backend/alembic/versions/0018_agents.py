"""Create agents and agent_files tables; add agent_id to conversations

Revision ID: 0018_agents
Revises: 0017_music_audit_actions
Create Date: 2026-06-22
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0018_agents"
down_revision: Union[str, None] = "0017_music_audit_actions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         UUID          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name            VARCHAR(100)  NOT NULL,
            description     TEXT,
            instructions    TEXT,
            provider        VARCHAR(32)   NOT NULL,
            model           VARCHAR(64)   NOT NULL,
            capabilities    JSONB,
            creativity_level INTEGER      NOT NULL DEFAULT 0,
            visibility      VARCHAR(16)   NOT NULL DEFAULT 'public',
            status          VARCHAR(16)   NOT NULL DEFAULT 'published',
            avatar_color    VARCHAR(16),
            category        VARCHAR(32),
            created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_agents_user_id
        ON agents (user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_agents_visibility_status
        ON agents (visibility, status)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_files (
            agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
            file_id  UUID NOT NULL REFERENCES files(id)  ON DELETE CASCADE,
            PRIMARY KEY (agent_id, file_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_agent_files_agent_id
        ON agent_files (agent_id)
    """)

    op.execute("""
        ALTER TABLE conversations
        ADD COLUMN IF NOT EXISTS agent_id UUID REFERENCES agents(id) ON DELETE SET NULL
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS agent_id")
    op.execute("DROP TABLE IF EXISTS agent_files")
    op.execute("DROP TABLE IF EXISTS agents")
