"""Move the case-study corpus to the shared "library" file scope (ADR 0002)

Every LINE-minted client workspace is its own tenant (D24), while the case
studies were seeded as scope="org" rows stamped to the brandbiz-demo
workspace. Under D21/D22's `files.workspace_id IS NOT DISTINCT FROM
<tenant>` visibility rule that made the entire corpus invisible to every
real client — POST /client/cases retrieved zero chunks and the UI reported
"no case studies matched closely enough", which was false: nothing was
ever scored.

Files with scope="library" are readable by every tenant (client seats and
staff alike), independent of CLIENT_INTERNAL_ACCESS_ENABLED — which must
stay off for a public LINE entry point (line_plan.md, Risks #2) and would
in any case not have helped, since it opens the workspace_id IS NULL pool
and these rows were not in it.

Data-only migration: no schema change (scope is a VARCHAR, Gotcha #5).
Case-study files are identified the same way scripts/seed_case_studies.py
identifies them — `filename LIKE 'case-study_%'` — and their catalog rows
(case_studies.workspace_id) are un-stamped to match.

Revision ID: 0065_case_library_scope
Revises: 0064_intake_multi_select
Create Date: 2026-08-25
"""
from __future__ import annotations

from alembic import op

revision = "0065_case_library_scope"
down_revision = "0064_intake_multi_select"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE files
           SET scope = 'library', workspace_id = NULL
         WHERE filename LIKE 'case-study\\_%' ESCAPE '\\'
           AND scope = 'org'
        """
    )
    op.execute(
        """
        UPDATE case_studies cs
           SET workspace_id = NULL
          FROM files f
         WHERE f.id = cs.file_id
           AND f.scope = 'library'
        """
    )


def downgrade() -> None:
    # Re-stamp to the demo workspace — the only tenant the corpus was ever
    # seeded into before this revision. If that workspace is gone the rows
    # become internal-shared org files (workspace_id NULL), which is the
    # pre-D21 meaning and still a valid state.
    op.execute(
        """
        UPDATE files
           SET scope = 'org',
               workspace_id = (SELECT id FROM workspaces WHERE slug = 'brandbiz-demo' LIMIT 1)
         WHERE scope = 'library'
        """
    )
    op.execute(
        """
        UPDATE case_studies cs
           SET workspace_id = f.workspace_id
          FROM files f
         WHERE f.id = cs.file_id
           AND f.filename LIKE 'case-study\\_%' ESCAPE '\\'
        """
    )
