"""Create client_invites table (Phase 5 §2, D21/D22)

Invite links that redeem into a client-workspace seat User. Hash-only
storage mirrors api_keys (0001_baseline) — see app/models/client_invite.py.

Revision ID: 0040_client_invites
Revises: 0039_client_audit_actions
Create Date: 2026-07-30
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0040_client_invites"
down_revision: Union[str, None] = "0039_client_audit_actions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS client_invites (
            id                 UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id       UUID          NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            token_hash         VARCHAR(64)   NOT NULL,
            expires_at         TIMESTAMPTZ   NOT NULL,
            redeemed_at        TIMESTAMPTZ,
            redeemed_user_id   UUID          REFERENCES users(id) ON DELETE SET NULL,
            created_by         UUID          REFERENCES users(id) ON DELETE SET NULL,
            line_user_id       VARCHAR(64),
            contact_name       VARCHAR(255),
            created_at         TIMESTAMPTZ   NOT NULL DEFAULT now(),
            CONSTRAINT uq_client_invites_token_hash UNIQUE (token_hash)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_client_invites_workspace_id
        ON client_invites (workspace_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS client_invites")
