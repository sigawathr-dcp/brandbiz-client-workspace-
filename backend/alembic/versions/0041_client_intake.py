"""Create client_profiles, research_runs, case_matches tables (Phase 5 §3)

Backs the client-workspace intake pipeline — see
app/services/client_intake.py and app/routers/client.py.

Revision ID: 0041_client_intake
Revises: 0040_client_invites
Create Date: 2026-07-30
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0041_client_intake"
down_revision: Union[str, None] = "0040_client_invites"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # workspace_id + user_id (not workspace_id alone): a single workspace can
    # have more than one redeemed seat (an event "demo" workspace with many
    # attendee invites), and each seat gets its own independent intake/
    # research/cases — never another attendee's.
    op.execute("""
        CREATE TABLE IF NOT EXISTS client_profiles (
            id                 UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id       UUID          NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            user_id            UUID          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            conversation_id    UUID          REFERENCES conversations(id) ON DELETE SET NULL,
            step               INTEGER       NOT NULL DEFAULT 0,
            completed_at       TIMESTAMPTZ,
            fields_ciphertext  BYTEA         NOT NULL,
            fields_nonce       BYTEA         NOT NULL,
            fields_tag         BYTEA         NOT NULL,
            key_version        INTEGER       NOT NULL DEFAULT 1,
            created_at         TIMESTAMPTZ   NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ   NOT NULL DEFAULT now(),
            CONSTRAINT uq_client_profiles_workspace_user UNIQUE (workspace_id, user_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_client_profiles_workspace_id
        ON client_profiles (workspace_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_client_profiles_user_id
        ON client_profiles (user_id)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS research_runs (
            id                 UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id       UUID          NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            user_id            UUID          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            conversation_id    UUID          REFERENCES conversations(id) ON DELETE SET NULL,
            query              TEXT          NOT NULL,
            findings           JSONB,
            citations          JSONB,
            model_used         VARCHAR(100),
            status             VARCHAR(16)   NOT NULL DEFAULT 'pending',
            created_at         TIMESTAMPTZ   NOT NULL DEFAULT now(),
            completed_at       TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_research_runs_workspace_id
        ON research_runs (workspace_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_research_runs_user_id
        ON research_runs (user_id)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS case_matches (
            id                 UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id       UUID          NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            user_id            UUID          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            conversation_id    UUID          REFERENCES conversations(id) ON DELETE SET NULL,
            file_id            UUID          NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            filename           VARCHAR(500)  NOT NULL,
            score              DOUBLE PRECISION NOT NULL,
            rationale          TEXT,
            created_at         TIMESTAMPTZ   NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_case_matches_workspace_id
        ON case_matches (workspace_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_case_matches_user_id
        ON case_matches (user_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS case_matches")
    op.execute("DROP TABLE IF EXISTS research_runs")
    op.execute("DROP TABLE IF EXISTS client_profiles")
