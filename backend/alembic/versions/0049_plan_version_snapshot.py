"""Snapshot title/provenance on plan_versions (PLAN.md Task 5.12)

Backs the readable version-history rail: revise_plan() (PUT
/client/plans/{id}) already overwrites plans.title/plans.provenance
wholesale on every resubmit, but plan_versions never captured either, so
a v1's real title and the research run / case files it actually cited
were destroyed the moment v2 was saved. Both new columns are nullable and
NOT backfilled — rows written before this migration legitimately have no
snapshot; the API/UI say so explicitly rather than inventing one from the
(now-different) parent Plan row.

No enum changes in this migration, so no audit-enum-sync mirroring needed
(compare 0045/0047/0048, which did add enum values).

Revision ID: 0049_plan_version_snapshot
Revises: 0048_intake_edited_audit_action
Create Date: 2026-08-11
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0049_plan_version_snapshot"
down_revision: Union[str, None] = "0048_intake_edited_audit_action"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE plan_versions ADD COLUMN IF NOT EXISTS title VARCHAR(500)")
    op.execute("ALTER TABLE plan_versions ADD COLUMN IF NOT EXISTS provenance JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE plan_versions DROP COLUMN IF EXISTS provenance")
    op.execute("ALTER TABLE plan_versions DROP COLUMN IF EXISTS title")
