"""Create vault_connection and vault_sync_run tables; add related audit actions

Backs the admin self-service Obsidian vault connection UI: an admin enters
the vault git URL + access token + branch from the frontend instead of
editing VAULT_* env vars, and syncs are triggered + polled from the app.

Deviation from PLAN.md D13 (locked: secrets in env vars for v1), explicitly
approved by the user: vault_connection.git_url/branch/bot_email/
templates_dirname are plaintext admin-editable config, but the access token
is AES-256-GCM encrypted at rest (ciphertext/nonce/tag/key_version columns),
the same scheme already used for message content (see 0001_baseline
`messages` table). The token is never returned by any API response.

backend/scripts/sync_vault.py and app/config.py VAULT_* env vars remain a
fallback when no vault_connection row exists — this migration does not
remove or migrate existing env-based config.

Revision ID: 0028_vault_connection
Revises: 0027_obsidian_source_columns
Create Date: 2026-07-13

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0028_vault_connection"
down_revision: Union[str, None] = "0027_obsidian_source_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS vault_connection (
            id                 UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            git_url            VARCHAR(1024) NOT NULL,
            branch             VARCHAR(255)  NOT NULL DEFAULT 'main',
            bot_email          VARCHAR(320)  NOT NULL,
            templates_dirname  VARCHAR(255)  NOT NULL DEFAULT 'templates',
            token_ciphertext   BYTEA,
            token_nonce        BYTEA,
            token_tag          BYTEA,
            token_key_version  INTEGER,
            updated_by         UUID,
            created_at         TIMESTAMPTZ   NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ   NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS vault_sync_run (
            id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            status        VARCHAR(16)  NOT NULL DEFAULT 'cloning',
            added         INTEGER      NOT NULL DEFAULT 0,
            updated       INTEGER      NOT NULL DEFAULT 0,
            deleted       INTEGER      NOT NULL DEFAULT 0,
            quarantined   INTEGER      NOT NULL DEFAULT 0,
            skipped       INTEGER      NOT NULL DEFAULT 0,
            failed_count  INTEGER      NOT NULL DEFAULT 0,
            error_text    TEXT,
            dry_run       BOOLEAN      NOT NULL DEFAULT false,
            triggered_by  UUID,
            started_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
            finished_at   TIMESTAMPTZ
        )
    """)
    # Poll target + the 409 "is a run already active" guard both filter on status.
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_vault_sync_run_status_started_at
        ON vault_sync_run (status, started_at DESC)
    """)

    # New audit actions emitted by app/services/vault_connection.py and
    # app/services/vault_runner.py. ALTER TYPE ... ADD VALUE is
    # non-transactional (Gotcha #5) but safe here: this migration only adds
    # the labels, nothing in the same transaction references them.
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'vault_connection_updated'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'vault_sync_triggered'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'vault_sync_completed'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'vault_sync_failed'")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_vault_sync_run_status_started_at")
    op.execute("DROP TABLE IF EXISTS vault_sync_run")
    op.execute("DROP TABLE IF EXISTS vault_connection")
    # audit_action enum values are not removed (PG can't DROP enum values easily).
