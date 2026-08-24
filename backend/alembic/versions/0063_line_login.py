"""Replace single-use invite links with LINE Login as the client entry point

The invite flow (`client_invites` + POST /public/redeem) made "one client,
one run" a property of the LINK: a `try_…` token, mailed or messaged out,
that `redeem_invite` marked spent via `redeemed_at`. That has two problems
the booth surfaced. A link can be forwarded, so "one use" bound the token,
not the person. And a link is single-use in the harshest sense — an
attendee who closed the tab was locked out with no recovery path, because
nothing tied the spent invite back to a person who could be re-identified.

LINE Login moves the constraint from the link to the identity.
`users.line_user_id` carries the verified `sub` claim from the id_token, and
the UNIQUE index below makes "one seat per LINE user" a database invariant
rather than an application check — it cannot be raced by two concurrent
logins the way a `redeemed_at IS NULL` read-then-write can. A returning
user re-logs into the SAME seat (see workspace.py::provision_line_seat),
which is what makes the rule enforceable without being a trap.

The column is nullable and non-unique-for-NULLs (Postgres UNIQUE permits
repeated NULLs), so every internal staff row and every existing
invite-redeemed seat is untouched. `client_invites` is deliberately NOT
dropped: /public/redeem stays as the break-glass path for when LINE login
fails in front of a live client.

`sub` is scoped to the LINE *provider*, not the channel — so a seat created
by the Login channel and a future Messaging API bot under the same provider
resolve to the same person. Under a different provider they never
reconcile. VARCHAR(64) matches the existing client_invites.line_user_id and
workspaces.line_user_id seam columns (0039).

Revision ID: 0063_line_login
Revises: 0062_intake_script_v3
Create Date: 2026-08-24
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0063_line_login"
down_revision: Union[str, None] = "0062_intake_script_v3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS line_user_id VARCHAR(64)")
    # The whole point of the change: one seat per LINE identity, enforced by
    # the database. provision_line_seat() also checks before inserting, but
    # that check is advisory — this is the one that holds under concurrency
    # (a double-tap on the LIFF login button is two in-flight requests).
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_users_line_user_id
        ON users (line_user_id)
        WHERE line_user_id IS NOT NULL
    """)
    # Distinct from client_redeemed (invite -> first seat): this records a
    # LINE identity being bound to a seat, and is re-emitted on every
    # returning login so the audit trail shows repeat visits. Same
    # one-value-per-migration pattern as 0058.
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'client_line_login'")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_users_line_user_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS line_user_id")
    # Postgres can't remove enum values — same as 0048/0058.
