"""Split plans into head + versions; normalize budget/provenance into rows (DB redesign, stage 5)

Three fixes to step 4 (plan & budget):

  1. `plans` used to be BOTH the container and the current version (title/
     body_*/budget/provenance/version all lived there), and plan_versions
     duplicated most of the same columns — title/provenance were even
     bolted on later, nullable, by migration 0049. `plans` becomes a head
     row only; `plan_versions` (renamed `version` -> `version_no`,
     `title` backfilled NOT NULL) carries all content, with
     UNIQUE(plan_id, version_no) replacing the old
     "no unique constraint, compensate with
     ORDER BY created_at DESC LIMIT 1" workaround
     (app/services/plan.py::get_version).
  2. plans.budget / plan_versions.budget (JSONB, money as strings) explode
     into plan_budget_lines (NUMERIC, a real FK to rate_card_items,
     needs_expert as a DB invariant instead of a parallel JSON array that
     could drift from `lines`).
  3. plans.provenance / plan_versions.provenance (JSONB, whose own
     docstring never matched what app/services/plan.py::draft_plan()
     actually wrote) explodes into plan_sources.

Pre-0049 plan_versions rows have NULL title/provenance (that migration
added both nullable and explicitly did not backfill them — see its
docstring: "callers must not fall back to the parent Plan's current
title/provenance"). This migration backfills a synthesized
`'Version ' || version_no` title (the real historical title is
unrecoverable) so `title NOT NULL` can be enforced, and — correctly —
does NOT synthesize provenance rows for those versions at all: the
Versions rail already renders "Provenance wasn't recorded for this
version" for them, and that stays true after this migration.

engagements.active_plan_id is backfilled to each engagement's most
recently created plan, if any — the best a one-time migration can do to
approximate what the old `bb:activePlan:*` localStorage key would have
held; going forward the server, not the browser, is the source of truth.

Revision ID: 0056_plan_head_split
Revises: 0055_case_studies
Create Date: 2026-08-15
"""
import json
from decimal import Decimal, InvalidOperation
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0056_plan_head_split"
down_revision: Union[str, None] = "0055_case_studies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _dec(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def upgrade() -> None:
    op.execute("ALTER TABLE plan_versions RENAME COLUMN version TO version_no")
    op.execute("ALTER TABLE plan_versions ADD COLUMN IF NOT EXISTS subtotal_amount NUMERIC(12,2)")
    op.execute("ALTER TABLE plan_versions ADD COLUMN IF NOT EXISTS contingency_rate NUMERIC(5,4)")
    op.execute("ALTER TABLE plan_versions ADD COLUMN IF NOT EXISTS contingency_amount NUMERIC(12,2)")
    op.execute("ALTER TABLE plan_versions ADD COLUMN IF NOT EXISTS total_amount NUMERIC(12,2)")
    op.execute("ALTER TABLE plan_versions ADD COLUMN IF NOT EXISTS currency VARCHAR(8)")
    op.execute("""
        ALTER TABLE plan_versions ADD COLUMN IF NOT EXISTS created_by UUID
        REFERENCES users(id) ON DELETE SET NULL
    """)
    op.execute("ALTER TABLE plan_versions ADD COLUMN IF NOT EXISTS note TEXT")

    op.execute("""
        ALTER TABLE plans ADD COLUMN IF NOT EXISTS current_version_id UUID
        REFERENCES plan_versions(id) ON DELETE SET NULL
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS plan_budget_lines (
            id                 UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            plan_version_id    UUID          NOT NULL REFERENCES plan_versions(id) ON DELETE CASCADE,
            ordinal            SMALLINT      NOT NULL,
            rate_card_item_id  UUID          REFERENCES rate_card_items(id) ON DELETE SET NULL,
            code               VARCHAR(64)   NOT NULL,
            label              VARCHAR(255),
            section            VARCHAR(16),
            unit               VARCHAR(64),
            qty                NUMERIC(10,2) NOT NULL DEFAULT 1,
            unit_price         NUMERIC(12,2),
            amount             NUMERIC(12,2),
            currency           VARCHAR(8),
            needs_expert       BOOLEAN       NOT NULL DEFAULT false
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_plan_budget_lines_plan_version_id ON plan_budget_lines (plan_version_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS plan_sources (
            id                 UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            plan_version_id    UUID          NOT NULL REFERENCES plan_versions(id) ON DELETE CASCADE,
            ordinal            SMALLINT      NOT NULL,
            kind               VARCHAR(24)   NOT NULL,
            ref_id             UUID,
            label_snapshot     TEXT,
            score_snapshot     DOUBLE PRECISION
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_plan_sources_plan_version_id ON plan_sources (plan_version_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS plan_drafts (
            id                  UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            engagement_step_id  UUID          NOT NULL REFERENCES engagement_steps(id) ON DELETE CASCADE,
            body_ciphertext     BYTEA         NOT NULL,
            body_nonce          BYTEA         NOT NULL,
            body_tag            BYTEA         NOT NULL,
            key_version         INTEGER       NOT NULL DEFAULT 1,
            budget_json         JSONB,
            created_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
            discarded_at        TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_plan_drafts_engagement_step_id ON plan_drafts (engagement_step_id)")

    conn = op.get_bind()

    # --- Any plans head missing a version row entirely (defensive — save_plan
    #     always writes v1, so this should be a no-op in practice) --------------
    orphans = conn.execute(text("""
        SELECT p.id, p.title, p.version, p.body_ciphertext, p.body_nonce, p.body_tag, p.key_version,
               p.budget, p.provenance
        FROM plans p
        WHERE NOT EXISTS (SELECT 1 FROM plan_versions v WHERE v.plan_id = p.id)
    """)).mappings().all()
    for p in orphans:
        conn.execute(text("""
            INSERT INTO plan_versions
                (plan_id, version_no, title, body_ciphertext, body_nonce, body_tag, key_version, budget, provenance)
            VALUES (:pid, :vno, :title, :ct, :nonce, :tag, :kv, :budget, :provenance)
        """), {
            "pid": p["id"], "vno": p["version"] or 1, "title": p["title"],
            "ct": p["body_ciphertext"], "nonce": p["body_nonce"], "tag": p["body_tag"], "kv": p["key_version"],
            "budget": json.dumps(p["budget"]) if p["budget"] is not None else None,
            "provenance": json.dumps(p["provenance"]) if p["provenance"] is not None else None,
        })

    # --- Backfill missing titles (pre-0049 rows) — real title unrecoverable --
    conn.execute(text("""
        UPDATE plan_versions SET title = 'Version ' || version_no WHERE title IS NULL
    """))
    op.execute("ALTER TABLE plan_versions ALTER COLUMN title SET NOT NULL")

    # --- Explode budget/provenance JSONB into rows ---------------------------
    versions = conn.execute(text("""
        SELECT v.id, v.budget, v.provenance, p.workspace_id
        FROM plan_versions v JOIN plans p ON p.id = v.plan_id
    """)).mappings().all()

    for v in versions:
        budget = v["budget"]
        if budget:
            subtotal, contingency, total = _dec(budget.get("subtotal")), _dec(budget.get("contingency")), _dec(budget.get("total"))
            currency = budget.get("currency")
            contingency_rate = (contingency / subtotal) if subtotal and contingency is not None and subtotal != 0 else None
            conn.execute(text("""
                UPDATE plan_versions
                SET subtotal_amount = :sub, contingency_rate = :rate, contingency_amount = :cont,
                    total_amount = :tot, currency = :cur
                WHERE id = :id
            """), {"sub": subtotal, "rate": contingency_rate, "cont": contingency, "tot": total, "cur": currency, "id": v["id"]})

            ordinal = 0
            for line in budget.get("lines") or []:
                code = str(line.get("code", "")).strip()
                rc_id = conn.execute(text("""
                    SELECT id FROM rate_card_items
                    WHERE code = :code AND (workspace_id = :ws OR workspace_id IS NULL)
                    ORDER BY workspace_id NULLS LAST LIMIT 1
                """), {"code": code, "ws": v["workspace_id"]}).scalar_one_or_none()
                conn.execute(text("""
                    INSERT INTO plan_budget_lines
                        (plan_version_id, ordinal, rate_card_item_id, code, label, section, unit,
                         qty, unit_price, amount, currency, needs_expert)
                    VALUES (:vid, :ord, :rcid, :code, :label, :section, :unit, :qty, :price, :amount, :cur, :needs_expert)
                """), {
                    "vid": v["id"], "ord": ordinal, "rcid": rc_id, "code": code,
                    "label": line.get("label"), "section": line.get("section"), "unit": line.get("unit"),
                    "qty": _dec(line.get("qty")) or Decimal("1"),
                    "price": _dec(line.get("unit_price")), "amount": _dec(line.get("amount")), "cur": currency,
                    "needs_expert": rc_id is None,
                })
                ordinal += 1
            for item in budget.get("needs_expert") or []:
                conn.execute(text("""
                    INSERT INTO plan_budget_lines (plan_version_id, ordinal, code, qty, needs_expert)
                    VALUES (:vid, :ord, :code, :qty, true)
                """), {
                    "vid": v["id"], "ord": ordinal,
                    "code": str(item.get("code", "")).strip(), "qty": _dec(item.get("qty")) or Decimal("1"),
                })
                ordinal += 1

        provenance = v["provenance"]
        if provenance:
            ordinal = 0
            for code in provenance.get("rate_card_codes") or []:
                conn.execute(text("""
                    INSERT INTO plan_sources (plan_version_id, ordinal, kind, label_snapshot)
                    VALUES (:vid, :ord, 'rate_card', :label)
                """), {"vid": v["id"], "ord": ordinal, "label": code})
                ordinal += 1
            for case in provenance.get("case_files") or []:
                conn.execute(text("""
                    INSERT INTO plan_sources (plan_version_id, ordinal, kind, ref_id, label_snapshot, score_snapshot)
                    VALUES (:vid, :ord, 'case_study', :ref, :label, :score)
                """), {
                    "vid": v["id"], "ord": ordinal, "ref": case.get("file_id"),
                    "label": case.get("filename"), "score": case.get("score"),
                })
                ordinal += 1
            rrid = provenance.get("research_run_id")
            for src in provenance.get("research_sources") or []:
                conn.execute(text("""
                    INSERT INTO plan_sources (plan_version_id, ordinal, kind, ref_id, label_snapshot)
                    VALUES (:vid, :ord, 'research_citation', :ref, :label)
                """), {
                    "vid": v["id"], "ord": ordinal,
                    "ref": rrid, "label": src.get("source") if isinstance(src, dict) else str(src),
                })
                ordinal += 1

    # --- plans.current_version_id ---------------------------------------------
    conn.execute(text("""
        UPDATE plans p
        SET current_version_id = v.id
        FROM plan_versions v
        WHERE v.plan_id = p.id AND v.version_no = p.version
    """))
    # Any plan whose old `version` didn't match a version_no 1:1 (shouldn't
    # happen) falls back to its newest version.
    conn.execute(text("""
        UPDATE plans p
        SET current_version_id = (
            SELECT v.id FROM plan_versions v WHERE v.plan_id = p.id ORDER BY v.version_no DESC LIMIT 1
        )
        WHERE p.current_version_id IS NULL
    """))

    # --- engagements.active_plan_id best-effort default -----------------------
    conn.execute(text("""
        UPDATE engagements e
        SET active_plan_id = (
            SELECT p.id FROM plans p WHERE p.engagement_id = e.id ORDER BY p.created_at DESC LIMIT 1
        )
        WHERE EXISTS (SELECT 1 FROM plans p WHERE p.engagement_id = e.id)
    """))


def downgrade() -> None:
    op.execute("UPDATE engagements SET active_plan_id = NULL")
    op.execute("ALTER TABLE plans DROP COLUMN IF EXISTS current_version_id")
    op.execute("DROP TABLE IF EXISTS plan_drafts")
    op.execute("DROP TABLE IF EXISTS plan_sources")
    op.execute("DROP TABLE IF EXISTS plan_budget_lines")
    op.execute("ALTER TABLE plan_versions ALTER COLUMN title DROP NOT NULL")
    op.execute("ALTER TABLE plan_versions DROP COLUMN IF EXISTS note")
    op.execute("ALTER TABLE plan_versions DROP COLUMN IF EXISTS created_by")
    op.execute("ALTER TABLE plan_versions DROP COLUMN IF EXISTS currency")
    op.execute("ALTER TABLE plan_versions DROP COLUMN IF EXISTS total_amount")
    op.execute("ALTER TABLE plan_versions DROP COLUMN IF EXISTS contingency_amount")
    op.execute("ALTER TABLE plan_versions DROP COLUMN IF EXISTS contingency_rate")
    op.execute("ALTER TABLE plan_versions DROP COLUMN IF EXISTS subtotal_amount")
    op.execute("ALTER TABLE plan_versions RENAME COLUMN version_no TO version")
