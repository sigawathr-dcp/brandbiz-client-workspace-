"""Publish intake script v3 — the DSME interview, with the owned-commerce trigger

Questions for DSMEs.xlsx adds a ninth question, `own_commerce`, between
`challenge` and `asset_channel`: how much of the client's revenue depends on
external platforms that charge GP / commission. Everything else — every
question, option, tag and weight — is byte-identical to v2, so this is an
insert, not a rewrite.

The new question needs a `use_mode` the schema does not have. Migration 0059
split the sheet's type-confused Weight column into `weight NUMERIC` plus
`use_mode IN ('match', 'feasibility')`, because at the time the column held
either a number or the string "Feasibility". This sheet introduces a third
value, "Solution Trigger", whose note is explicit that it must not reach the
matcher: "ไม่ใช้คำนวณ Similarity Score / Case Matching โดยตรง ใช้เป็น Trigger
หลัง Diagnosis". So the CHECK constraint widens to three modes and the
weight/use_mode agreement constraint widens with it — a trigger question
carries no weight, exactly like a feasibility one.

Widening rather than reusing 'feasibility' is deliberate. Both are unweighted
and neither ranks cases, but they are consumed by different code at different
moments: feasibility answers size the scope and budget of a plan that already
exists, while a trigger decides that a plan must contain a workstream at all
(app/services/solution_trigger.py). Collapsing them would leave nothing in the
schema to select the trigger rows by.

The six scoring weights are unchanged and still sum to 1.000 — asserted below
before anything is written, because a v3 that silently reweighted the matcher
would move every case ranking shown to a client.

Publishing follows 0060 exactly: insert as version 3, flip v2 to
active = false, and do NOT touch engagements.intake_script_id. An engagement
mid-interview keeps answering the script it started; a finished one keeps the
vocabulary its answers were recorded under. Only new engagements get v3, via
services/engagement.py::get_active_script_id.

Unlike 0060 as originally written, this migration reads
app.services.client_intake.INTAKE_SCRIPT, because that literal currently IS
v3. The moment a v4 is authored, this file must be frozen the same way 0052
froze v1 and 0060 now freezes v2 — inline the v3 literal here and drop the
import.

Revision ID: 0062_intake_script_v3
Revises: 0061_case_study_tags
Create Date: 2026-08-23
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0062_intake_script_v3"
down_revision: Union[str, None] = "0061_case_study_tags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCRIPT_NAME = "DSME 9-question script"

_USE_MODES_V3 = "('match', 'feasibility', 'solution_trigger')"
_USE_MODES_V2 = "('match', 'feasibility')"


def _set_use_mode_constraints(modes: str) -> None:
    """Rewrite both use_mode constraints to admit `modes`.

    They travel together: ck_..._use_mode names the legal set, and
    ck_..._weight_use_mode says which of those may carry a weight. Widening
    one without the other would either reject the new rows or let a trigger
    question quietly acquire a weight and start ranking cases.
    """
    op.execute("ALTER TABLE intake_questions DROP CONSTRAINT IF EXISTS ck_intake_questions_use_mode")
    op.execute(f"""
        ALTER TABLE intake_questions
        ADD CONSTRAINT ck_intake_questions_use_mode
        CHECK (use_mode IN {modes})
    """)
    op.execute("ALTER TABLE intake_questions DROP CONSTRAINT IF EXISTS ck_intake_questions_weight_use_mode")
    op.execute(f"""
        ALTER TABLE intake_questions
        ADD CONSTRAINT ck_intake_questions_weight_use_mode
        CHECK (
            (use_mode <> 'match' AND weight IS NULL)
            OR (use_mode = 'match' AND (weight IS NULL OR (weight > 0 AND weight <= 1)))
        )
    """)


def upgrade() -> None:
    conn = op.get_bind()

    # Imported at run time, not module load: alembic imports every version
    # file to build its graph, and the script should only be read when this
    # migration actually executes.
    from app.services.client_intake import INTAKE_SCRIPT

    weights = [s["weight"] for s in INTAKE_SCRIPT if s["use_mode"] == "match" and s["weight"]]
    total = round(sum(weights), 6)
    if total != 1.0:
        raise RuntimeError(f"v3 scoring weights must sum to 1.000, got {total}")

    # A trigger question that arrived carrying a weight would be a
    # transcription error from the sheet, and would silently enter
    # SCORING_WEIGHTS. Fail the migration rather than publish it.
    for step in INTAKE_SCRIPT:
        if step["use_mode"] != "match" and step["weight"] is not None:
            raise RuntimeError(
                f"{step['field']}: use_mode={step['use_mode']!r} must not carry a weight"
            )

    _set_use_mode_constraints(_USE_MODES_V3)

    conn.execute(text("UPDATE intake_scripts SET active = false WHERE locale = 'th'"))

    script_id = conn.execute(text("""
        INSERT INTO intake_scripts (version, locale, name, active)
        VALUES (3, 'th', :name, true)
        RETURNING id
    """), {"name": _SCRIPT_NAME}).scalar_one()

    for ordinal, step in enumerate(INTAKE_SCRIPT):
        question_id = conn.execute(text("""
            INSERT INTO intake_questions
                (script_id, ordinal, field_key, prompt, insight,
                 match_tag, weight, use_mode, dev_note)
            VALUES
                (:script_id, :ordinal, :field_key, :prompt, :insight,
                 :match_tag, :weight, :use_mode, :dev_note)
            RETURNING id
        """), {
            "script_id": script_id, "ordinal": ordinal,
            "field_key": step["field"], "prompt": step["question"],
            "insight": step.get("insight"),
            "match_tag": step.get("match_tag"), "weight": step.get("weight"),
            "use_mode": step.get("use_mode", "match"), "dev_note": step.get("dev_note"),
        }).scalar_one()

        for opt_ordinal, option in enumerate(step["options"]):
            conn.execute(text("""
                INSERT INTO intake_options (question_id, ordinal, label, value, tag_value)
                VALUES (:question_id, :ordinal, :label, :value, :tag_value)
            """), {
                "question_id": question_id, "ordinal": opt_ordinal,
                "label": option["label"], "value": option["value"],
                "tag_value": option.get("tag"),
            })


def downgrade() -> None:
    conn = op.get_bind()
    # Refuse to delete a script any engagement is pinned to — dropping it
    # would orphan real answers (intake_answers.question_id is ON DELETE
    # RESTRICT, but engagements.intake_script_id is not, so check explicitly).
    in_use = conn.execute(text("""
        SELECT count(*) FROM engagements e
        JOIN intake_scripts s ON s.id = e.intake_script_id
        WHERE s.version = 3 AND s.locale = 'th'
    """)).scalar_one()
    if in_use:
        raise RuntimeError(
            f"cannot drop intake script v3: {in_use} engagement(s) are pinned to it"
        )
    conn.execute(text("DELETE FROM intake_scripts WHERE version = 3 AND locale = 'th'"))
    conn.execute(text("UPDATE intake_scripts SET active = true WHERE version = 2 AND locale = 'th'"))
    # Narrow the constraints only once the rows that need the third mode are
    # gone. Any other script still holding a 'solution_trigger' row would make
    # this fail loudly, which is the correct outcome — it would mean a v4
    # exists and this downgrade is being run out of order.
    _set_use_mode_constraints(_USE_MODES_V2)
