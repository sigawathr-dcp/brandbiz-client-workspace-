"""Multi-select intake answers for the six scoring questions

Two changes, one feature: a client may now answer the six "match" questions
(industry, stage, audience, challenge, asset_channel, objective) with MORE
than one chip.

1. `intake_questions.multi_select` — per-question flag, default false. Set
   true for the six scoring field_keys across every published script
   version. This deliberately touches published rows, which the versioning
   rule normally forbids — but the rule's purpose is that a stored answer
   must never be REINTERPRETED against a vocabulary it was not collected
   under, and multi_select changes no question text, option, tag or weight.
   An existing single answer stays exactly as valid under multi-select; the
   flag only widens what NEW answers may look like, including profile edits
   on engagements pinned to older scripts. Feasibility (timeframe, budget)
   and solution-trigger (own_commerce) questions stay single-pick: a budget
   band or a platform-dependency level is one fact, not a set.

2. `intake_answers` live-row invariant. 0053's uq_intake_answers_live_field
   ("exactly one live answer per field") cannot hold a multi answer, so it
   splits in two: a field's live answer is EITHER one free-text row OR a set
   of chip rows with distinct option_ids. The either/or itself (no mixing
   chips with free text for one field) is application-level, enforced by
   routers/client.py::_record_answer superseding ALL live rows for the field
   before inserting the new answer's rows in one transaction.

Revision ID: 0064_intake_multi_select
Revises: 0063_line_login
Create Date: 2026-08-24
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0064_intake_multi_select"
down_revision: Union[str, None] = "0063_line_login"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The six scoring questions — kept as an explicit literal (not derived from
# the live INTAKE_SCRIPT) so this migration means the same thing forever.
_MULTI_FIELDS = "('industry', 'stage', 'audience', 'challenge', 'asset_channel', 'objective')"


def upgrade() -> None:
    op.execute("""
        ALTER TABLE intake_questions
        ADD COLUMN IF NOT EXISTS multi_select BOOLEAN NOT NULL DEFAULT false
    """)
    op.execute(f"""
        UPDATE intake_questions SET multi_select = true
        WHERE field_key IN {_MULTI_FIELDS}
    """)

    op.execute("DROP INDEX IF EXISTS uq_intake_answers_live_field")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_intake_answers_live_option
        ON intake_answers (engagement_step_id, field_key, option_id)
        WHERE superseded_at IS NULL AND option_id IS NOT NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_intake_answers_live_freetext
        ON intake_answers (engagement_step_id, field_key)
        WHERE superseded_at IS NULL AND option_id IS NULL
    """)


def downgrade() -> None:
    # Collapse any multi answers back to one live row per field (keep the
    # lowest-ordinal pick) so the old single-answer index can be rebuilt.
    op.execute("""
        UPDATE intake_answers a SET superseded_at = now()
        FROM intake_options o
        WHERE a.option_id = o.id AND a.superseded_at IS NULL
          AND EXISTS (
            SELECT 1 FROM intake_answers a2
            JOIN intake_options o2 ON o2.id = a2.option_id
            WHERE a2.engagement_step_id = a.engagement_step_id
              AND a2.field_key = a.field_key
              AND a2.superseded_at IS NULL
              AND o2.ordinal < o.ordinal
          )
    """)
    op.execute("DROP INDEX IF EXISTS uq_intake_answers_live_option")
    op.execute("DROP INDEX IF EXISTS uq_intake_answers_live_freetext")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_intake_answers_live_field
        ON intake_answers (engagement_step_id, field_key)
        WHERE superseded_at IS NULL
    """)
    op.execute("ALTER TABLE intake_questions DROP COLUMN IF EXISTS multi_select")
