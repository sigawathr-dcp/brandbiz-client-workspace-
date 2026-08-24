"""Add 'intake_edited' audit_action enum value (PLAN.md Task 5.11)

Backs PATCH /client/intake/fields — a client correcting an already-answered
intake field. This is intentionally a distinct action from 'intake_answered'
(§7.3: audit_log rows are append-only, and an edit must never mutate or be
confused with the original answer's audit row).

Gotcha #5 note: no explicit COMMIT needed — nothing in this upgrade run
references the new value in SQL; it is first used at application runtime.
Same reasoning as 0039_client_audit_actions.py / 0045_plan_rating_audit_action.py
/ 0047_message_retention.py.

Revision ID: 0048_intake_edited_audit_action
Revises: 0047_message_retention
Create Date: 2026-08-11
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0048_intake_edited_audit_action"
down_revision: Union[str, None] = "0047_message_retention"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'intake_edited'")


def downgrade() -> None:
    # Postgres does not support removing enum values; residual label is harmless.
    pass
