"""Carry the interview sheet's Matching Tag / Weight columns into the catalog

Interview_Details.xlsx describes each question with two dev-facing columns
the schema had nowhere to put: `Matching Tag` (which case-study dimension
this answer scores against) and `Weight` (its share of the match score).
Both belong on `intake_questions`, not in code, so that reweighting is a new
`intake_scripts` version rather than a deploy — and so an engagement pinned
to an old script keeps the weights it was actually matched under.

The sheet's `Weight` column is type-confused: six rows hold a number and two
hold the string "Feasibility". That splits here into `weight NUMERIC` (NULL
for non-scoring questions) plus `use_mode` ('match' | 'feasibility'), so the
scorer can sum weights without parsing strings.

`intake_options.tag_value` gives an option stable identity independent of its
ordinal and its Thai label. Matching keys off the token, so reordering or
rewording the sheet's column D in a future script version can never silently
reinterpret an answer already stored against the old numbering.

Nothing is backfilled onto script v1: it predates the tag model, was never
matched by weight, and must stay exactly as its engagements experienced it.
v1 rows therefore keep weight = NULL / tag_value = NULL and take the
'match' server default for use_mode. Only 0060's v2 rows carry real values.

Revision ID: 0059_intake_weights
Revises: 0058_engagement_started_action
Create Date: 2026-08-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0059_intake_weights"
down_revision: Union[str, None] = "0058_engagement_started_action"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE intake_questions
            ADD COLUMN IF NOT EXISTS match_tag VARCHAR(64),
            ADD COLUMN IF NOT EXISTS weight    NUMERIC(4,3),
            ADD COLUMN IF NOT EXISTS use_mode  VARCHAR(16) NOT NULL DEFAULT 'match',
            ADD COLUMN IF NOT EXISTS dev_note  TEXT
    """)
    op.execute("""
        ALTER TABLE intake_questions
        ADD CONSTRAINT ck_intake_questions_use_mode
        CHECK (use_mode IN ('match', 'feasibility'))
    """)
    # weight and use_mode must agree: a scoring question needs a weight, a
    # feasibility question must not carry one. Without this, a question could
    # silently drop out of the score by having use_mode='match' and no weight.
    op.execute("""
        ALTER TABLE intake_questions
        ADD CONSTRAINT ck_intake_questions_weight_use_mode
        CHECK (
            (use_mode = 'feasibility' AND weight IS NULL)
            OR (use_mode = 'match' AND (weight IS NULL OR (weight > 0 AND weight <= 1)))
        )
    """)
    op.execute("""
        ALTER TABLE intake_options
            ADD COLUMN IF NOT EXISTS tag_value VARCHAR(64)
    """)
    # Two options on the same question may not share a token — the scorer
    # resolves an answer to exactly one tag.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_intake_options_question_tag
        ON intake_options (question_id, tag_value)
        WHERE tag_value IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_intake_options_question_tag")
    op.execute("ALTER TABLE intake_options DROP COLUMN IF EXISTS tag_value")
    op.execute(
        "ALTER TABLE intake_questions "
        "DROP CONSTRAINT IF EXISTS ck_intake_questions_weight_use_mode"
    )
    op.execute(
        "ALTER TABLE intake_questions DROP CONSTRAINT IF EXISTS ck_intake_questions_use_mode"
    )
    op.execute("""
        ALTER TABLE intake_questions
            DROP COLUMN IF EXISTS dev_note,
            DROP COLUMN IF EXISTS use_mode,
            DROP COLUMN IF EXISTS weight,
            DROP COLUMN IF EXISTS match_tag
    """)
