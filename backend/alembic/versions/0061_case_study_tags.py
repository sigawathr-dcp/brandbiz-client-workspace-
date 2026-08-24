"""Tag the case-study corpus so the interview's weights have something to score

Interview_Details.xlsx column F ("Matching Tag") presumes each case study
carries structured dimensions to match a client's answer against. It does
not: case_studies holds only title / client_name / category / source_url /
image_url / summary, and `category` is free-text scraped from the portfolio
site ("SKINCARE - SERUM", "APPLICATION / FOOD DELIVERY") — display metadata,
never used in scoring. This adds the missing side of the join.

Many-to-many per dimension, not a column per dimension: one campaign
legitimately serves two audiences and answers three challenges at once.
Collapsing that to a single value would force a lossy pick at tagging time
and make every multi-purpose case score badly against clients it genuinely
fits.

`confidence` records how the tag was arrived at (1.00 = a human asserted it,
lower = a model proposed it and a human let it stand). It is stored rather
than thresholded here so the eval harness can ask whether low-confidence
tags are pulling ranks around before anyone decides to trust them.

Tags are NOT generated in this migration. scripts/tag_case_studies.py
proposes them from each case's narrative for human review, and the reviewed
result is committed to backend/eval/case_match/case_tags.csv — the same
review-then-commit shape as corpus_manifest.csv. Seeding reads only that
file (scripts/seed_case_tags.py), so a model can never silently rewrite the
corpus's meaning as part of a deploy.

Also adds case_matches.score_breakdown: the per-dimension contributions
behind a stored score. Without it a persisted match is an unexplainable
float, and "why did this case rank first for that client" is unanswerable
after the fact.

Revision ID: 0061_case_study_tags
Revises: 0060_intake_script_v2
Create Date: 2026-08-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0061_case_study_tags"
down_revision: Union[str, None] = "0060_intake_script_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS case_study_tags (
            id             UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            case_study_id  UUID          NOT NULL REFERENCES case_studies(id) ON DELETE CASCADE,
            tag_type       VARCHAR(32)   NOT NULL,
            tag_value      VARCHAR(64)   NOT NULL,
            confidence     NUMERIC(3,2)  NOT NULL DEFAULT 1.00,
            created_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
            CONSTRAINT uq_case_study_tags_case_type_value
                UNIQUE (case_study_id, tag_type, tag_value),
            CONSTRAINT ck_case_study_tags_confidence
                CHECK (confidence > 0 AND confidence <= 1)
        )
    """)
    # The scorer's read path is "all tags for these candidate cases", so the
    # index leads with case_study_id; tag_type is included because every
    # lookup groups by dimension.
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_case_study_tags_case_type
        ON case_study_tags (case_study_id, tag_type)
    """)
    # Reverse lookup — "which cases address low_retention" — for the tagging
    # review script and corpus-coverage reporting.
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_case_study_tags_type_value
        ON case_study_tags (tag_type, tag_value)
    """)
    # No CHECK on tag_type/tag_value: the vocabulary lives in
    # app/services/case_taxonomy.py and is derived from the active intake
    # script, so pinning it into a database constraint would mean a migration
    # every time a question gains an option. Enforcement is at ingest
    # (case_taxonomy.validate_tag) plus a unit test over the committed CSV.

    op.execute("ALTER TABLE case_matches ADD COLUMN IF NOT EXISTS score_breakdown JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE case_matches DROP COLUMN IF EXISTS score_breakdown")
    op.execute("DROP INDEX IF EXISTS ix_case_study_tags_type_value")
    op.execute("DROP INDEX IF EXISTS ix_case_study_tags_case_type")
    op.execute("DROP TABLE IF EXISTS case_study_tags")
