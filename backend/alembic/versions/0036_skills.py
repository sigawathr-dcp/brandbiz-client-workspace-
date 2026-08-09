"""Create skills and agent_skills tables

Skills are reusable instruction fragments (name/slug + description + body)
injected into the chat system prompt: auto-matched by description, forced by
/slug, or pinned to an Agent via agent_skills. Mirrors 0018_agents.py.

status/visibility stored as VARCHAR, enabled as BOOLEAN — no PG enum
(Gotcha #5).

Revision ID: 0036_skills
Revises: 0035_hermes_host_job
Create Date: 2026-07-17
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0036_skills"
down_revision: Union[str, None] = "0035_hermes_host_job"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         UUID          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name            VARCHAR(64)   NOT NULL,
            description     TEXT,
            instructions    TEXT,
            source_markdown TEXT,
            enabled         BOOLEAN       NOT NULL DEFAULT true,
            visibility      VARCHAR(16)   NOT NULL DEFAULT 'personal',
            category        VARCHAR(32),
            created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
            CONSTRAINT uq_skills_user_id_name UNIQUE (user_id, name)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_skills_user_id
        ON skills (user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_skills_visibility_enabled
        ON skills (visibility, enabled)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_skills (
            agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
            skill_id UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
            PRIMARY KEY (agent_id, skill_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_agent_skills_agent_id
        ON agent_skills (agent_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_skills")
    op.execute("DROP TABLE IF EXISTS skills")
