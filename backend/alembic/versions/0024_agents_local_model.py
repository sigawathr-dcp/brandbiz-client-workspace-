"""Switch every agent to the local model (gemma4:26b)

Bulk-updates all rows in `agents` to provider='local', model='gemma4:26b' —
the LOCAL_MODEL_CODE constant in app/llm/router.py, which every routing,
policy, and permission check in the backend compares against. Requested
as a one-time reset of all agents to the local model.

Lossy: original per-agent provider/model values are not preserved, so
downgrade() cannot restore them.

Revision ID: 0024_agents_local_model
Revises: 0023_login_failed_audit_action
Create Date: 2026-07-01
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0024_agents_local_model"
down_revision: Union[str, None] = "0023_login_failed_audit_action"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE agents
        SET provider = 'local', model = 'gemma4:26b', updated_at = now()
    """)


def downgrade() -> None:
    # No-op: original per-agent provider/model values are not recoverable.
    pass
