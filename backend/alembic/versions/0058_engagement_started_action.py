"""Add engagement_started to audit_action (DB redesign — POST /client/engagements)

A returning client starting a fresh engagement (app/services/engagement.py
::start_new) is audited distinctly from the original client_redeemed
(invite -> first seat) event. Same one-value-per-migration pattern as 0045
(plan_rated) and 0048 (intake_edited).

Revision ID: 0058_engagement_started_action
Revises: 0057_drop_legacy
Create Date: 2026-08-15
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0058_engagement_started_action"
down_revision: Union[str, None] = "0057_drop_legacy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'engagement_started'")


def downgrade() -> None:
    pass  # Postgres can't remove enum values — same as 0048.
