"""Add source/source_path to files for Obsidian vault sync

Lets a `files` row be traced back to its origin: a user upload
(source='upload', the existing default) or a synced Obsidian vault note
(source='obsidian', source_path=<vault-relative path>). The vault sync
service upserts by (source='obsidian', source_path) so re-syncing a note
updates its existing row instead of duplicating it.

Also adds the audit_action values the vault sync service emits.

Revision ID: 0027_obsidian_source_columns
Revises: 0026_studio_generation_parent_id
Create Date: 2026-07-09

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0027_obsidian_source_columns"
down_revision: Union[str, None] = "0026_studio_generation_parent_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE files
            ADD COLUMN IF NOT EXISTS source VARCHAR(32) NOT NULL DEFAULT 'upload'
    """)
    op.execute("""
        ALTER TABLE files
            ADD COLUMN IF NOT EXISTS source_path VARCHAR(500)
    """)
    # Partial index — only vault rows need lookup by (source, source_path);
    # keeps the index small and is exactly the upsert key vault_sync uses.
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_files_source_source_path
        ON files (source, source_path)
        WHERE source = 'obsidian'
    """)
    # New audit actions emitted by app/services/vault_sync.py.
    # ALTER TYPE ... ADD VALUE is non-transactional (Gotcha #5) but safe here:
    # this migration only adds the labels, nothing in the same transaction
    # references them.
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'vault_note_ingested'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'vault_note_updated'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'vault_note_deleted'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'vault_note_quarantined'")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_files_source_source_path")
    op.execute("ALTER TABLE files DROP COLUMN IF EXISTS source_path")
    op.execute("ALTER TABLE files DROP COLUMN IF EXISTS source")
    # audit_action enum values are not removed (PG can't DROP enum values easily).
