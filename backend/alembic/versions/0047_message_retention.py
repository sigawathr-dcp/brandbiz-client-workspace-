"""D14 — 30-day message content retention (PLAN.md Decisions D14)

Makes messages.content_ciphertext/content_nonce/content_tag nullable and
adds content_purged_at, so app/services/retention.py::purge_expired_messages
can null out a message's content 30 days after created_at while keeping the
row (role, model_used, tokens, cost, timestamps) indefinitely for
audit/analytics — see app/models/message.py.

Gotcha #5 note: the new audit_action value is not referenced by any SQL in
this same migration, so no explicit COMMIT is needed — same reasoning as
0039_client_audit_actions.py / 0045_plan_rating_audit_action.py.

Revision ID: 0047_message_retention
Revises: 0046_user_preferences
Create Date: 2026-08-10
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0047_message_retention"
down_revision: Union[str, None] = "0046_user_preferences"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE messages ALTER COLUMN content_ciphertext DROP NOT NULL")
    op.execute("ALTER TABLE messages ALTER COLUMN content_nonce DROP NOT NULL")
    op.execute("ALTER TABLE messages ALTER COLUMN content_tag DROP NOT NULL")
    op.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS content_purged_at TIMESTAMPTZ")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'messages_purged'")


def downgrade() -> None:
    op.execute("ALTER TABLE messages DROP COLUMN IF EXISTS content_purged_at")
    # NOT NULL is intentionally not restored: a downgrade run after any
    # purge has occurred would fail on existing NULL rows. Postgres also
    # does not support removing enum values; the residual audit_action
    # label is harmless.
