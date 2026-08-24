"""Create case_studies catalog + case_match_runs; normalize case_matches (DB redesign, stage 4)

Two fixes to step 3 (case matching):

  1. case_studies is the case-library catalog, parsed ONCE from each
     file's chunks via app/services/case_card.py::parse_case_card()
     (backfilled here) instead of on every /client/cases or
     /client/bootstrap request — see app/services/case_match.py::
     cards_for_file_ids, which re-ran this parse on every read.
  2. case_match_runs gives step 3 a run record that exists even at zero
     matches, so bootstrap can tell "never ran" from "ran, found nothing"
     without querying audit_log as application state (the old
     _bootstrap_research_and_cases probe — see 0051's docstring for why
     that probe ran exactly once more, during backfill, and never again).

The old schema deleted-and-reinserted a seat's case_matches rows on every
POST /client/cases, so there is no real "run" boundary to recover from
history. This migration approximates one run per (engagement, calendar
day) group of existing rows — the best a backfill can do — and gives it a
placeholder encrypted query (the original per-run query text was never
persisted anywhere in the old schema). Every run created by the app AFTER
this migration has its real query, verbatim.

Revision ID: 0055_case_studies
Revises: 0054_research_normalized
Create Date: 2026-08-15
"""
import hashlib
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0055_case_studies"
down_revision: Union[str, None] = "0054_research_normalized"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PLACEHOLDER_QUERY = (
    "(query text unavailable — this run was reconstructed from legacy "
    "case_matches rows during the 0055 backfill; the original per-run "
    "query was never persisted in the pre-redesign schema)"
)


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS case_studies (
            id                 UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id       UUID          REFERENCES workspaces(id) ON DELETE CASCADE,
            file_id            UUID          NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            title              VARCHAR(500),
            client_name        VARCHAR(255),
            category           VARCHAR(255),
            source_url         TEXT,
            image_url          TEXT,
            summary            TEXT,
            content_sha256     VARCHAR(64),
            parser_version     SMALLINT      NOT NULL DEFAULT 1,
            parsed_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
            CONSTRAINT uq_case_studies_file_id UNIQUE (file_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_case_studies_workspace_id ON case_studies (workspace_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS case_match_runs (
            id                  UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            engagement_step_id  UUID          NOT NULL REFERENCES engagement_steps(id) ON DELETE CASCADE,
            query_ciphertext    BYTEA         NOT NULL,
            query_nonce         BYTEA         NOT NULL,
            query_tag           BYTEA         NOT NULL,
            key_version         INTEGER       NOT NULL DEFAULT 1,
            top_k               SMALLINT,
            status              VARCHAR(16)   NOT NULL DEFAULT 'running',
            match_count         SMALLINT      NOT NULL DEFAULT 0,
            error_detail        TEXT,
            created_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
            completed_at        TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_case_match_runs_engagement_step_id ON case_match_runs (engagement_step_id)")

    op.execute("ALTER TABLE case_matches ADD COLUMN IF NOT EXISTS case_match_run_id UUID")
    op.execute("ALTER TABLE case_matches ADD COLUMN IF NOT EXISTS case_study_id UUID")
    op.execute("ALTER TABLE case_matches ADD COLUMN IF NOT EXISTS rank SMALLINT")

    conn = op.get_bind()
    from app import crypto
    from app.services.case_card import parse_case_card

    # --- case_studies: parse each distinct matched file once -----------------
    file_rows = conn.execute(text("""
        SELECT DISTINCT cm.file_id, f.workspace_id
        FROM case_matches cm JOIN files f ON f.id = cm.file_id
    """)).mappings().all()

    case_study_id_by_file: dict = {}
    for row in file_rows:
        chunks = conn.execute(text("""
            SELECT content FROM file_chunks WHERE file_id = :fid ORDER BY chunk_index
        """), {"fid": row["file_id"]}).scalars().all()
        full_text = "".join(chunks)
        card = parse_case_card(full_text)
        sha = hashlib.sha256(full_text.encode("utf-8")).hexdigest() if full_text else None

        cs_id = conn.execute(text("""
            INSERT INTO case_studies
                (workspace_id, file_id, title, client_name, category, source_url, image_url, summary, content_sha256)
            VALUES (:ws, :fid, :title, :client, :category, :source, :image, :summary, :sha)
            RETURNING id
        """), {
            "ws": row["workspace_id"], "fid": row["file_id"],
            "title": card.title, "client": card.client, "category": card.category,
            "source": card.source_url, "image": card.image_url, "summary": card.summary, "sha": sha,
        }).scalar_one()
        case_study_id_by_file[str(row["file_id"])] = cs_id

    # --- case_match_runs: one per (engagement, calendar day) of legacy rows --
    groups = conn.execute(text("""
        SELECT engagement_id, (created_at AT TIME ZONE 'UTC')::date AS day,
               MAX(created_at) AS last_at, COUNT(*) AS n
        FROM case_matches
        WHERE engagement_id IS NOT NULL
        GROUP BY engagement_id, (created_at AT TIME ZONE 'UTC')::date
    """)).mappings().all()

    for g in groups:
        step_id = conn.execute(text("""
            SELECT id FROM engagement_steps WHERE engagement_id = :eid AND step_no = 3
        """), {"eid": g["engagement_id"]}).scalar_one()

        ct, nonce, tag, kv = crypto.encrypt(_PLACEHOLDER_QUERY)
        run_id = conn.execute(text("""
            INSERT INTO case_match_runs
                (engagement_step_id, query_ciphertext, query_nonce, query_tag, key_version,
                 status, match_count, completed_at)
            VALUES (:step_id, :ct, :nonce, :tag, :kv, 'done', :n, :completed_at)
            RETURNING id
        """), {
            "step_id": step_id, "ct": ct, "nonce": nonce, "tag": tag, "kv": kv,
            "n": g["n"], "completed_at": g["last_at"],
        }).scalar_one()

        rows = conn.execute(text("""
            SELECT id, file_id FROM case_matches
            WHERE engagement_id = :eid AND (created_at AT TIME ZONE 'UTC')::date = :day
            ORDER BY score DESC, filename
        """), {"eid": g["engagement_id"], "day": g["day"]}).mappings().all()

        for rank, r in enumerate(rows):
            conn.execute(text("""
                UPDATE case_matches SET case_match_run_id = :run_id, case_study_id = :cs_id, rank = :rank
                WHERE id = :id
            """), {
                "run_id": run_id, "cs_id": case_study_id_by_file[str(r["file_id"])],
                "rank": rank, "id": r["id"],
            })


def downgrade() -> None:
    op.execute("ALTER TABLE case_matches DROP COLUMN IF EXISTS rank")
    op.execute("ALTER TABLE case_matches DROP COLUMN IF EXISTS case_study_id")
    op.execute("ALTER TABLE case_matches DROP COLUMN IF EXISTS case_match_run_id")
    op.execute("DROP TABLE IF EXISTS case_match_runs")
    op.execute("DROP TABLE IF EXISTS case_studies")
