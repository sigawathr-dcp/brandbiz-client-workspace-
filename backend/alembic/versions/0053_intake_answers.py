"""Create intake_answers; backfill from client_profiles.fields_ciphertext (DB redesign, stage 2)

The core fix for the "all 8 answers in one opaque encrypted blob" problem:
client_profiles.fields_ciphertext was one AES-256-GCM blob holding
json.dumps({field: value}) for every answered field — no per-answer
timestamps, no edit history, every read decrypted all 8, and zero
queryability. Each answer becomes its own row here. A chip pick resolves
to intake_options.value and is stored as a plain FK (option_id) — no
ciphertext at all, so "how many attendees picked Food & beverage" becomes
a GROUP BY. Only free-text answers (the "Skip" affordance) are encrypted,
which is still §7.1-correct: free text is client-authored prose exactly
like a chat message.

Needs ENCRYPTION_KEY in the migration's environment (same key the running
app uses — see app/crypto.py) to decrypt client_profiles.fields_ciphertext
and re-encrypt any free-text answers found inside it. This mirrors
app/main.py's normal boot path, which already runs `alembic upgrade head`
in-process with the app's own environment loaded.

client_profiles itself is NOT dropped here — that happens in 0057, once
the new tables have been verified against the running app.

Revision ID: 0053_intake_answers
Revises: 0052_intake_catalog
Create Date: 2026-08-15
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0053_intake_answers"
down_revision: Union[str, None] = "0052_intake_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS intake_answers (
            id                  UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            engagement_step_id  UUID          NOT NULL REFERENCES engagement_steps(id) ON DELETE CASCADE,
            question_id         UUID          NOT NULL REFERENCES intake_questions(id) ON DELETE RESTRICT,
            field_key           VARCHAR(64)   NOT NULL,
            option_id           UUID          REFERENCES intake_options(id) ON DELETE RESTRICT,
            value_ciphertext    BYTEA,
            value_nonce         BYTEA,
            value_tag           BYTEA,
            key_version         INTEGER       NOT NULL DEFAULT 1,
            source              VARCHAR(16)   NOT NULL,
            answered_at         TIMESTAMPTZ   NOT NULL DEFAULT now(),
            superseded_at       TIMESTAMPTZ,
            CONSTRAINT ck_intake_answers_has_value CHECK (
                option_id IS NOT NULL OR value_ciphertext IS NOT NULL
            )
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_intake_answers_engagement_step_id ON intake_answers (engagement_step_id)")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_intake_answers_live_field
        ON intake_answers (engagement_step_id, field_key)
        WHERE superseded_at IS NULL
    """)

    conn = op.get_bind()
    from app import crypto

    profiles = conn.execute(text("""
        SELECT cp.id, cp.workspace_id, cp.user_id, cp.updated_at,
               cp.fields_ciphertext, cp.fields_nonce, cp.fields_tag, cp.key_version,
               e.id AS engagement_id, e.intake_script_id
        FROM client_profiles cp
        JOIN engagements e ON e.workspace_id = cp.workspace_id AND e.user_id = cp.user_id AND e.seq = 1
    """)).mappings().all()

    for p in profiles:
        if not p["fields_ciphertext"]:
            continue
        raw = crypto.decrypt(p["fields_ciphertext"], p["fields_nonce"], p["fields_tag"], p["key_version"])
        import json
        fields: dict = json.loads(raw) if raw else {}
        if not fields:
            continue

        step_id = conn.execute(text("""
            SELECT id FROM engagement_steps WHERE engagement_id = :eid AND step_no = 1
        """), {"eid": p["engagement_id"]}).scalar_one()

        questions = {
            row["field_key"]: row["id"]
            for row in conn.execute(text("""
                SELECT id, field_key FROM intake_questions WHERE script_id = :sid
            """), {"sid": p["intake_script_id"]}).mappings().all()
        }

        for field_key, value in fields.items():
            question_id = questions.get(field_key)
            if question_id is None:
                continue  # answer for a field the seeded script no longer has

            option_id = conn.execute(text("""
                SELECT id FROM intake_options WHERE question_id = :qid AND value = :val LIMIT 1
            """), {"qid": question_id, "val": value}).scalar_one_or_none()

            if option_id is not None:
                conn.execute(text("""
                    INSERT INTO intake_answers
                        (engagement_step_id, question_id, field_key, option_id, source, answered_at)
                    VALUES (:step_id, :qid, :field_key, :oid, 'chip', :answered_at)
                """), {
                    "step_id": step_id, "qid": question_id, "field_key": field_key,
                    "oid": option_id, "answered_at": p["updated_at"],
                })
            else:
                ct, nonce, tag, kv = crypto.encrypt(str(value))
                conn.execute(text("""
                    INSERT INTO intake_answers
                        (engagement_step_id, question_id, field_key, value_ciphertext, value_nonce,
                         value_tag, key_version, source, answered_at)
                    VALUES (:step_id, :qid, :field_key, :ct, :nonce, :tag, :kv, 'free_text', :answered_at)
                """), {
                    "step_id": step_id, "qid": question_id, "field_key": field_key,
                    "ct": ct, "nonce": nonce, "tag": tag, "kv": kv, "answered_at": p["updated_at"],
                })


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS intake_answers")
