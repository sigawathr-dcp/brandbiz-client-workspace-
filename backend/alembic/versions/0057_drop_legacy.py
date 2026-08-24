"""Contract: drop legacy columns/tables, enforce final constraints (DB redesign, stage 6)

Final stage of the "Client Workspace — Database Redesign". Everything
dropped here has already been superseded by a normalized replacement in
0050-0056 and verified against the running application:

  - client_profiles          -> engagements + engagement_steps + intake_answers
  - research_runs.{query,findings,citations,workspace_id,user_id,conversation_id}
                              -> research_runs.query_ciphertext/* + engagement_step_id
                                 + research_findings/research_citations
  - case_matches.{workspace_id,user_id,conversation_id,filename}
                              -> case_match_run_id + case_study_id
  - plans.{title,version,body_*,budget,provenance}
                              -> plan_versions (title/body_*/budget-as-rows/
                                 provenance-as-rows), plans.current_version_id

This is the only migration in the redesign with no working downgrade — by
design (matches 0048's precedent: some structural changes, like dropping
columns whose replacement is now the only writer, cannot be cleanly
un-dropped without also reversing every migration that ran after them).
Roll back to 0056 by restoring from a pre-0057 backup, not `alembic
downgrade`.

Revision ID: 0057_drop_legacy
Revises: 0056_plan_head_split
Create Date: 2026-08-15
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0057_drop_legacy"
down_revision: Union[str, None] = "0056_plan_head_split"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- research_runs: finish becoming engagement_step_id-scoped ------------
    op.execute("""
        ALTER TABLE research_runs
        ADD CONSTRAINT fk_research_runs_engagement_step
        FOREIGN KEY (engagement_step_id) REFERENCES engagement_steps(id) ON DELETE CASCADE
    """)
    op.execute("ALTER TABLE research_runs ALTER COLUMN engagement_step_id SET NOT NULL")
    op.execute("ALTER TABLE research_runs ALTER COLUMN query_ciphertext SET NOT NULL")
    op.execute("ALTER TABLE research_runs ALTER COLUMN query_nonce SET NOT NULL")
    op.execute("ALTER TABLE research_runs ALTER COLUMN query_tag SET NOT NULL")
    op.execute("ALTER TABLE research_runs ALTER COLUMN status SET DEFAULT 'running'")
    op.execute("CREATE INDEX IF NOT EXISTS ix_research_runs_engagement_step_id ON research_runs (engagement_step_id)")
    op.execute("ALTER TABLE research_runs DROP COLUMN IF EXISTS query")
    op.execute("ALTER TABLE research_runs DROP COLUMN IF EXISTS findings")
    op.execute("ALTER TABLE research_runs DROP COLUMN IF EXISTS citations")
    op.execute("ALTER TABLE research_runs DROP COLUMN IF EXISTS workspace_id")
    op.execute("ALTER TABLE research_runs DROP COLUMN IF EXISTS user_id")
    op.execute("ALTER TABLE research_runs DROP COLUMN IF EXISTS conversation_id")
    op.execute("ALTER TABLE research_runs DROP COLUMN IF EXISTS engagement_id")

    # --- case_matches: finish becoming case_match_run_id/case_study_id-scoped -
    op.execute("""
        ALTER TABLE case_matches
        ADD CONSTRAINT fk_case_matches_run
        FOREIGN KEY (case_match_run_id) REFERENCES case_match_runs(id) ON DELETE CASCADE
    """)
    op.execute("""
        ALTER TABLE case_matches
        ADD CONSTRAINT fk_case_matches_case_study
        FOREIGN KEY (case_study_id) REFERENCES case_studies(id) ON DELETE RESTRICT
    """)
    op.execute("ALTER TABLE case_matches ALTER COLUMN case_match_run_id SET NOT NULL")
    op.execute("ALTER TABLE case_matches ALTER COLUMN case_study_id SET NOT NULL")
    op.execute("ALTER TABLE case_matches ALTER COLUMN rank SET NOT NULL")
    op.execute("""
        ALTER TABLE case_matches
        ADD CONSTRAINT uq_case_matches_run_case UNIQUE (case_match_run_id, case_study_id)
    """)
    op.execute("""
        ALTER TABLE case_matches
        ADD CONSTRAINT ck_case_matches_rank_nonneg CHECK (rank >= 0)
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_case_matches_run_id ON case_matches (case_match_run_id)")
    op.execute("ALTER TABLE case_matches DROP COLUMN IF EXISTS workspace_id")
    op.execute("ALTER TABLE case_matches DROP COLUMN IF EXISTS user_id")
    op.execute("ALTER TABLE case_matches DROP COLUMN IF EXISTS conversation_id")
    op.execute("ALTER TABLE case_matches DROP COLUMN IF EXISTS filename")
    op.execute("ALTER TABLE case_matches DROP COLUMN IF EXISTS file_id")
    op.execute("ALTER TABLE case_matches DROP COLUMN IF EXISTS engagement_id")

    # --- plans: finish becoming a head-only row -------------------------------
    op.execute("ALTER TABLE plans DROP COLUMN IF EXISTS title")
    op.execute("ALTER TABLE plans DROP COLUMN IF EXISTS version")
    op.execute("ALTER TABLE plans DROP COLUMN IF EXISTS body_ciphertext")
    op.execute("ALTER TABLE plans DROP COLUMN IF EXISTS body_nonce")
    op.execute("ALTER TABLE plans DROP COLUMN IF EXISTS body_tag")
    op.execute("ALTER TABLE plans DROP COLUMN IF EXISTS key_version")
    op.execute("ALTER TABLE plans DROP COLUMN IF EXISTS budget")
    op.execute("ALTER TABLE plans DROP COLUMN IF EXISTS provenance")

    # --- client_profiles: fully superseded ------------------------------------
    op.execute("DROP TABLE IF EXISTS client_profiles")


def downgrade() -> None:
    raise RuntimeError(
        "0057_drop_legacy has no downgrade — restore from a pre-0057 backup "
        "instead (see this migration's docstring)."
    )
