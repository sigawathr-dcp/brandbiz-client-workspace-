"""Create + seed the intake question catalog (DB redesign, stage 2)

intake_scripts -> intake_questions -> intake_options replaces the Python
literal INTAKE_SCRIPT (app/services/client_intake.py) as the runtime
source of truth for the interview's 8 questions. INTAKE_SCRIPT itself
stays in that module as the SEED data this migration reads — see its
docstring for why: reordering or inserting a question in a future
INTAKE_SCRIPT edit now publishes a new `intake_scripts` version rather
than silently reinterpreting every engagement's already-stored answers
(each engagement pins the script version it was given via
engagements.intake_script_id).

Also backfills intake_script_id onto every engagement created by 0051
(that migration ran before this catalog existed).

Revision ID: 0052_intake_catalog
Revises: 0051_engagements_backfill
Create Date: 2026-08-15
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0052_intake_catalog"
down_revision: Union[str, None] = "0051_engagements_backfill"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS intake_scripts (
            id             UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            version        INTEGER       NOT NULL,
            locale         VARCHAR(8)    NOT NULL DEFAULT 'th',
            name           VARCHAR(255)  NOT NULL,
            active         BOOLEAN       NOT NULL DEFAULT true,
            published_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
            CONSTRAINT uq_intake_scripts_version_locale UNIQUE (version, locale)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS intake_questions (
            id             UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            script_id      UUID          NOT NULL REFERENCES intake_scripts(id) ON DELETE CASCADE,
            ordinal        SMALLINT      NOT NULL,
            field_key      VARCHAR(64)   NOT NULL,
            prompt         TEXT          NOT NULL,
            insight        TEXT,
            CONSTRAINT uq_intake_questions_script_ordinal UNIQUE (script_id, ordinal),
            CONSTRAINT uq_intake_questions_script_field UNIQUE (script_id, field_key)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_intake_questions_script_id ON intake_questions (script_id)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS intake_options (
            id             UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            question_id    UUID          NOT NULL REFERENCES intake_questions(id) ON DELETE CASCADE,
            ordinal        SMALLINT      NOT NULL,
            label          TEXT          NOT NULL,
            value          VARCHAR(255)  NOT NULL,
            CONSTRAINT uq_intake_options_question_ordinal UNIQUE (question_id, ordinal)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_intake_options_question_id ON intake_options (question_id)")

    op.execute("""
        ALTER TABLE engagements
        ADD CONSTRAINT fk_engagements_intake_script
        FOREIGN KEY (intake_script_id) REFERENCES intake_scripts(id) ON DELETE RESTRICT
    """)

    conn = op.get_bind()

    # Import here, not at module load time — alembic imports every version
    # file to build its graph, and INTAKE_SCRIPT should only be read at the
    # moment this specific migration actually runs.
    from app.services.client_intake import INTAKE_SCRIPT

    script_id = conn.execute(text("""
        INSERT INTO intake_scripts (version, locale, name, active)
        VALUES (1, 'th', 'Original 8-question script', true)
        RETURNING id
    """)).scalar_one()

    for ordinal, step in enumerate(INTAKE_SCRIPT):
        question_id = conn.execute(text("""
            INSERT INTO intake_questions (script_id, ordinal, field_key, prompt, insight)
            VALUES (:script_id, :ordinal, :field_key, :prompt, :insight)
            RETURNING id
        """), {
            "script_id": script_id, "ordinal": ordinal,
            "field_key": step["field"], "prompt": step["question"], "insight": step.get("insight"),
        }).scalar_one()

        for opt_ordinal, option in enumerate(step["options"]):
            conn.execute(text("""
                INSERT INTO intake_options (question_id, ordinal, label, value)
                VALUES (:question_id, :ordinal, :label, :value)
            """), {
                "question_id": question_id, "ordinal": opt_ordinal,
                "label": option["label"], "value": option["value"],
            })

    conn.execute(text("UPDATE engagements SET intake_script_id = :sid WHERE intake_script_id IS NULL"),
                 {"sid": script_id})


def downgrade() -> None:
    op.execute("ALTER TABLE engagements DROP CONSTRAINT IF EXISTS fk_engagements_intake_script")
    op.execute("UPDATE engagements SET intake_script_id = NULL")
    op.execute("DROP TABLE IF EXISTS intake_options")
    op.execute("DROP TABLE IF EXISTS intake_questions")
    op.execute("DROP TABLE IF EXISTS intake_scripts")
