"""Normalize research_runs; encrypt query; split findings/citations into tables (DB redesign, stage 3)

Three fixes to step 2 (market scan):

  1. research_runs.query was plaintext `Text` — a plaintext copy of the
     client's intake answers, which are encrypted two tables over
     (client_profiles.fields_ciphertext, now intake_answers). Replaced
     with query_ciphertext/nonce/tag, same AES-256-GCM treatment §7.1
     already requires for the answers themselves.
  2. findings/citations were JSONB with fake structure: findings was
     literally `full_text.split("\n")` re-packaged as
     `[{"text": s}, ...]`, and the model's own docstring promised
     `citation_indexes`/`title` keys that app/routers/client.py's writer
     never actually populated. Both become real tables
     (research_findings, research_citations); the promised-but-never-
     written link between them becomes research_finding_citations, a
     real many-to-many join — trivially empty on backfill, since the old
     data never had the indexes to begin with.
  3. workspace_id/user_id/conversation_id drop in favor of
     engagement_step_id (via the scaffolding engagement_id column 0050/
     0051 populated) — all three were reachable via
     engagement_step -> engagement anyway.

`status`'s vocabulary changes from {pending, done, failed} to engagement_
steps' uniform {idle, running, done, failed, skipped}: existing 'pending'
rows become 'failed' — there has never been a background worker to finish
a stuck run, which is exactly why app/routers/client.py's old
_RESEARCH_STATUS_OUT already mapped 'pending' to the user-facing 'error'.

Old columns (query/findings/citations/workspace_id/user_id/conversation_id)
are NOT dropped here — that's 0057, once the new columns are verified.

Revision ID: 0054_research_normalized
Revises: 0053_intake_answers
Create Date: 2026-08-15
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0054_research_normalized"
down_revision: Union[str, None] = "0053_intake_answers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE research_runs ADD COLUMN IF NOT EXISTS engagement_step_id UUID")
    op.execute("ALTER TABLE research_runs ADD COLUMN IF NOT EXISTS query_ciphertext BYTEA")
    op.execute("ALTER TABLE research_runs ADD COLUMN IF NOT EXISTS query_nonce BYTEA")
    op.execute("ALTER TABLE research_runs ADD COLUMN IF NOT EXISTS query_tag BYTEA")
    op.execute(
        "ALTER TABLE research_runs ADD COLUMN IF NOT EXISTS "
        "key_version INTEGER NOT NULL DEFAULT 1"
    )
    op.execute("ALTER TABLE research_runs ADD COLUMN IF NOT EXISTS tokens_input INTEGER")
    op.execute("ALTER TABLE research_runs ADD COLUMN IF NOT EXISTS tokens_output INTEGER")
    op.execute("ALTER TABLE research_runs ADD COLUMN IF NOT EXISTS error_detail TEXT")

    op.execute("""
        CREATE TABLE IF NOT EXISTS research_findings (
            id                 UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            research_run_id    UUID          NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE,
            ordinal            SMALLINT      NOT NULL,
            text               TEXT          NOT NULL,
            CONSTRAINT uq_research_findings_run_ordinal UNIQUE (research_run_id, ordinal)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_research_findings_run_id ON research_findings (research_run_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS research_citations (
            id                 UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            research_run_id    UUID          NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE,
            ordinal            SMALLINT      NOT NULL,
            url                TEXT          NOT NULL,
            title              TEXT,
            source_domain      VARCHAR(255),
            CONSTRAINT uq_research_citations_run_ordinal UNIQUE (research_run_id, ordinal)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_research_citations_run_id ON research_citations (research_run_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS research_finding_citations (
            finding_id  UUID NOT NULL REFERENCES research_findings(id) ON DELETE CASCADE,
            citation_id UUID NOT NULL REFERENCES research_citations(id) ON DELETE CASCADE,
            PRIMARY KEY (finding_id, citation_id)
        )
    """)

    conn = op.get_bind()
    from app import crypto

    op.execute("UPDATE research_runs SET status = 'failed' WHERE status = 'pending'")
    op.execute("""
        UPDATE research_runs r
        SET engagement_step_id = es.id
        FROM engagement_steps es
        WHERE es.engagement_id = r.engagement_id AND es.step_no = 2
    """)

    runs = conn.execute(text("""
        SELECT id, query, findings, citations FROM research_runs WHERE query IS NOT NULL
    """)).mappings().all()

    for run in runs:
        ct, nonce, tag, kv = crypto.encrypt(run["query"])
        conn.execute(text("""
            UPDATE research_runs
            SET query_ciphertext = :ct, query_nonce = :nonce, query_tag = :tag, key_version = :kv
            WHERE id = :id
        """), {"ct": ct, "nonce": nonce, "tag": tag, "kv": kv, "id": run["id"]})

        for i, f in enumerate(run["findings"] or []):
            conn.execute(text("""
                INSERT INTO research_findings (research_run_id, ordinal, text) VALUES (:rid, :ord, :text)
            """), {"rid": run["id"], "ord": i, "text": f.get("text", "")})

        for i, c in enumerate(run["citations"] or []):
            conn.execute(text("""
                INSERT INTO research_citations (research_run_id, ordinal, url, title)
                VALUES (:rid, :ord, :url, :title)
            """), {"rid": run["id"], "ord": i, "url": c.get("source", ""), "title": c.get("title")})


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS research_finding_citations")
    op.execute("DROP TABLE IF EXISTS research_citations")
    op.execute("DROP TABLE IF EXISTS research_findings")
    op.execute("ALTER TABLE research_runs DROP COLUMN IF EXISTS error_detail")
    op.execute("ALTER TABLE research_runs DROP COLUMN IF EXISTS tokens_output")
    op.execute("ALTER TABLE research_runs DROP COLUMN IF EXISTS tokens_input")
    op.execute("ALTER TABLE research_runs DROP COLUMN IF EXISTS query_tag")
    op.execute("ALTER TABLE research_runs DROP COLUMN IF EXISTS key_version")
    op.execute("ALTER TABLE research_runs DROP COLUMN IF EXISTS query_nonce")
    op.execute("ALTER TABLE research_runs DROP COLUMN IF EXISTS query_ciphertext")
    op.execute("ALTER TABLE research_runs DROP COLUMN IF EXISTS engagement_step_id")
    # Deliberately NOT reverting status='failed' back to 'pending' — once
    # collapsed, a genuinely-failed run and an originally-'pending' one are
    # indistinguishable. Same trade-off 0047's downgrade makes explicitly.
