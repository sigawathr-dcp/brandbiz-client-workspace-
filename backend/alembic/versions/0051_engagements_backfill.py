"""Backfill engagements + engagement_steps from client_profiles (DB redesign, stage 1)

Data migration — one `engagements` row per existing `client_profiles` row
(the old schema allowed exactly one per seat via
uq_client_profiles_workspace_user, so this is always seq=1), with 4
`engagement_steps` rows whose status is derived from the OLD per-table
signals this whole redesign replaces:

  - step 1 (interview): client_profiles.step / .completed_at
  - step 2 (market):    latest research_runs.status for that
                         (workspace_id, user_id, conversation_id)
  - step 3 (cases):     case_matches row existence, falling back to the
                         OLD audit_log 'case_matched' probe ONE LAST TIME
                         (app/routers/client.py's former
                         _bootstrap_research_and_cases) for the
                         zero-match-but-it-ran case — this is the only
                         place that probe is allowed to exist ever again;
                         after this migration, engagement_steps IS the
                         answer and the probe is gone from the app.
  - step 4 (plan):      plans row existence for (workspace_id, user_id)

All four child tables' rows are then linked to the new engagement via the
scaffolding `engagement_id` column 0050 added (permanent on plans/leads/
conversations, temporary on research_runs/case_matches — see 0050's
docstring).

Backfilled engagements are all set `status='active'`: under the old
schema every client_profiles row WAS the seat's one and only, still
current, engagement — nothing about the old data distinguishes "finished
and could start a new one" from "still going", so preserving current
behavior (the seat resumes exactly where bootstrap already left it) means
treating all of them as the seat's active engagement.

Revision ID: 0051_engagements_backfill
Revises: 0050_engagements
Create Date: 2026-08-15
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0051_engagements_backfill"
down_revision: Union[str, None] = "0050_engagements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Matches app/services/client_intake.py::total_steps() at the time this
# migration was written (len(INTAKE_SCRIPT) == 8). Not imported from the
# app package here — a future edit to INTAKE_SCRIPT must never reinterpret
# what an already-migrated engagement_steps.progress_total row means.
_INTAKE_TOTAL_STEPS = 8

# research_runs.status (old vocabulary) -> engagement_steps.status (new
# 5-state vocabulary). 'pending' cannot resolve (no background worker ever
# existed to finish it — see app/routers/client.py's old
# _RESEARCH_STATUS_OUT = {"pending": "error"}), so it maps to 'failed'.
_MARKET_STATUS_MAP = {"done": "done", "failed": "failed", "pending": "failed"}


def upgrade() -> None:
    conn = op.get_bind()

    profiles = conn.execute(text("""
        SELECT id, workspace_id, user_id, conversation_id, step, completed_at,
               created_at, updated_at
        FROM client_profiles
    """)).mappings().all()

    for p in profiles:
        engagement_id = conn.execute(text("""
            INSERT INTO engagements
                (workspace_id, user_id, seq, conversation_id, status, created_at, updated_at, completed_at)
            VALUES
                (:workspace_id, :user_id, 1, :conversation_id, 'active', :created_at, :updated_at, :completed_at)
            RETURNING id
        """), {
            "workspace_id": p["workspace_id"],
            "user_id": p["user_id"],
            "conversation_id": p["conversation_id"],
            "created_at": p["created_at"],
            "updated_at": p["updated_at"],
            "completed_at": p["completed_at"],
        }).scalar_one()

        # --- Step 1: interview -------------------------------------------------
        if p["completed_at"] is not None:
            interview_status, interview_completed_at = "done", p["completed_at"]
        elif p["step"] and p["step"] > 0:
            interview_status, interview_completed_at = "running", None
        else:
            interview_status, interview_completed_at = "idle", None

        conn.execute(text("""
            INSERT INTO engagement_steps
                (engagement_id, step_no, step_key, status, progress_current, progress_total, completed_at)
            VALUES
                (:eid, 1, 'interview', :status, :cur, :total, :completed_at)
        """), {
            "eid": engagement_id, "status": interview_status,
            "cur": p["step"] or 0, "total": _INTAKE_TOTAL_STEPS,
            "completed_at": interview_completed_at,
        })

        # --- Step 2: market scan -------------------------------------------------
        run = conn.execute(text("""
            SELECT status, completed_at FROM research_runs
            WHERE workspace_id = :ws AND user_id = :uid
              AND conversation_id IS NOT DISTINCT FROM :conv
            ORDER BY created_at DESC LIMIT 1
        """), {"ws": p["workspace_id"], "uid": p["user_id"], "conv": p["conversation_id"]}).mappings().first()
        if run is None:
            market_status, market_completed_at = "idle", None
        else:
            market_status = _MARKET_STATUS_MAP.get(run["status"], "failed")
            market_completed_at = run["completed_at"]

        conn.execute(text("""
            INSERT INTO engagement_steps (engagement_id, step_no, step_key, status, completed_at)
            VALUES (:eid, 2, 'market', :status, :completed_at)
        """), {"eid": engagement_id, "status": market_status, "completed_at": market_completed_at})

        # --- Step 3: case match ----------------------------------------------
        match_count = conn.execute(text("""
            SELECT COUNT(*) FROM case_matches
            WHERE workspace_id = :ws AND user_id = :uid
              AND conversation_id IS NOT DISTINCT FROM :conv
        """), {"ws": p["workspace_id"], "uid": p["user_id"], "conv": p["conversation_id"]}).scalar_one()
        if match_count > 0:
            cases_status = "done"
        else:
            # The old zero-match probe, run here one last time — after this
            # migration, engagement_steps.status IS the answer and this
            # audit_log query never runs again anywhere in the app.
            ran = conn.execute(text("""
                SELECT 1 FROM audit_log
                WHERE action = 'case_matched' AND resource_type = 'workspace'
                  AND resource_id = :ws AND user_id = :uid
                LIMIT 1
            """), {"ws": p["workspace_id"], "uid": p["user_id"]}).scalar_one_or_none()
            cases_status = "done" if ran is not None else "idle"

        conn.execute(text("""
            INSERT INTO engagement_steps (engagement_id, step_no, step_key, status)
            VALUES (:eid, 3, 'cases', :status)
        """), {"eid": engagement_id, "status": cases_status})

        # --- Step 4: plan & budget --------------------------------------------
        plan_count = conn.execute(text("""
            SELECT COUNT(*) FROM plans WHERE workspace_id = :ws AND user_id = :uid
        """), {"ws": p["workspace_id"], "uid": p["user_id"]}).scalar_one()
        plan_status = "done" if plan_count > 0 else "idle"

        conn.execute(text("""
            INSERT INTO engagement_steps (engagement_id, step_no, step_key, status)
            VALUES (:eid, 4, 'plan', :status)
        """), {"eid": engagement_id, "status": plan_status})

        # --- Link existing rows to this engagement ----------------------------
        conn.execute(text("""
            UPDATE research_runs SET engagement_id = :eid
            WHERE workspace_id = :ws AND user_id = :uid AND conversation_id IS NOT DISTINCT FROM :conv
        """), {"eid": engagement_id, "ws": p["workspace_id"], "uid": p["user_id"], "conv": p["conversation_id"]})
        conn.execute(text("""
            UPDATE case_matches SET engagement_id = :eid
            WHERE workspace_id = :ws AND user_id = :uid AND conversation_id IS NOT DISTINCT FROM :conv
        """), {"eid": engagement_id, "ws": p["workspace_id"], "uid": p["user_id"], "conv": p["conversation_id"]})
        conn.execute(text("""
            UPDATE plans SET engagement_id = :eid WHERE workspace_id = :ws AND user_id = :uid
        """), {"eid": engagement_id, "ws": p["workspace_id"], "uid": p["user_id"]})
        conn.execute(text("""
            UPDATE leads SET engagement_id = :eid WHERE workspace_id = :ws AND user_id = :uid
        """), {"eid": engagement_id, "ws": p["workspace_id"], "uid": p["user_id"]})
        if p["conversation_id"] is not None:
            conn.execute(text("""
                UPDATE conversations SET workspace_id = :ws, engagement_id = :eid, kind = 'client_workspace'
                WHERE id = :conv
            """), {"ws": p["workspace_id"], "eid": engagement_id, "conv": p["conversation_id"]})


def downgrade() -> None:
    # Best-effort: clears everything this migration wrote. Destructive to
    # any engagement/engagement_step created by real app usage AFTER this
    # migration ran — acceptable here (pre-production demo dataset; see
    # PROGRESS.md — migrations 0044+ have never run against a real DB) but
    # not a general-purpose reversal. Same trade-off 0047's downgrade makes
    # explicitly for the same reason.
    conn = op.get_bind()
    conn.execute(text("UPDATE conversations SET workspace_id = NULL, engagement_id = NULL, kind = 'internal'"))
    conn.execute(text("UPDATE leads SET engagement_id = NULL"))
    conn.execute(text("UPDATE plans SET engagement_id = NULL"))
    conn.execute(text("UPDATE case_matches SET engagement_id = NULL"))
    conn.execute(text("UPDATE research_runs SET engagement_id = NULL"))
    conn.execute(text("DELETE FROM engagement_steps"))
    conn.execute(text("DELETE FROM engagements"))
