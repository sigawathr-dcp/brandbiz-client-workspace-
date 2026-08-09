"""Add Thai National ID (compact) classification rule — detects dash-less 13-digit IDs

The existing Thai National ID rule requires dashes (1-xxxx-xxxxx-xx-x format).
Users frequently type the number without separators, e.g. 1234567890121, which was
not detected as TIER_3_CONFIDENTIAL.

This migration adds a companion rule that matches any 13-digit run and relies on the
existing Mod-11 checksum validator (registered in classifier._VALIDATORS under the
rule name "Thai National ID (compact)") to eliminate false positives.

Note: data_classification_rules.name has no unique index, so we use WHERE NOT EXISTS
instead of ON CONFLICT to guard against re-runs.

Revision ID: 0004_thai_id_compact
Revises: 0003_audit_partitions
Create Date: 2026-06-06

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004_thai_id_compact"
down_revision: Union[str, None] = "0002_consent_acknowledged"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Raw string to avoid Python \d escape warnings in the docstring + SQL pattern.
    op.execute(r"""
        INSERT INTO data_classification_rules
            (name, pattern_type, pattern, detected_tier, description)
        SELECT
            'Thai National ID (compact)',
            'regex',
            '\d{13}',
            'TIER_3_CONFIDENTIAL'::data_tier,
            'เลขบัตรประชาชนไทย 13 หลัก (ไม่มีขีด) — ต้องผ่าน Mod-11 checksum'
        WHERE NOT EXISTS (
            SELECT 1 FROM data_classification_rules
            WHERE name = 'Thai National ID (compact)'
        )
    """)


def downgrade() -> None:
    op.execute(
        "DELETE FROM data_classification_rules WHERE name = 'Thai National ID (compact)'"
    )
