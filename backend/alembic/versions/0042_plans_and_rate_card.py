"""Create rate_card_items, plans, plan_versions tables (Phase 5 §4, D21/D22)

Structural fix for the design's budget guardrail: the model emits only
{code, qty} pairs (never a THB amount); app/services/rate_card.py::price()
looks the amount up here in Python. See app/models/rate_card.py and
app/models/plan.py for the full rationale.

Revision ID: 0042_plans_and_rate_card
Revises: 0041_client_intake
Create Date: 2026-07-30
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0042_plans_and_rate_card"
down_revision: Union[str, None] = "0041_client_intake"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS rate_card_items (
            id             UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id   UUID          REFERENCES workspaces(id) ON DELETE CASCADE,
            section        VARCHAR(16),
            code           VARCHAR(64)   NOT NULL,
            label          VARCHAR(255)  NOT NULL,
            unit           VARCHAR(64),
            unit_price     NUMERIC(12,2) NOT NULL,
            currency       VARCHAR(8)    NOT NULL DEFAULT 'THB',
            active         BOOLEAN       NOT NULL DEFAULT true,
            created_at     TIMESTAMPTZ   NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_rate_card_items_code
        ON rate_card_items (code)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_rate_card_items_workspace_id
        ON rate_card_items (workspace_id)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id                 UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id       UUID          NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            user_id            UUID          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            conversation_id    UUID          REFERENCES conversations(id) ON DELETE SET NULL,
            title              VARCHAR(500)  NOT NULL,
            version            INTEGER       NOT NULL DEFAULT 1,
            status             VARCHAR(16)   NOT NULL DEFAULT 'draft',
            body_ciphertext    BYTEA         NOT NULL,
            body_nonce         BYTEA         NOT NULL,
            body_tag           BYTEA         NOT NULL,
            key_version        INTEGER       NOT NULL DEFAULT 1,
            budget             JSONB,
            provenance         JSONB,
            share_token_hash   VARCHAR(64),
            created_at         TIMESTAMPTZ   NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ   NOT NULL DEFAULT now(),
            CONSTRAINT uq_plans_share_token_hash UNIQUE (share_token_hash)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_plans_workspace_id
        ON plans (workspace_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_plans_user_id
        ON plans (user_id)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS plan_versions (
            id                 UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            plan_id            UUID          NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
            version            INTEGER       NOT NULL,
            body_ciphertext    BYTEA         NOT NULL,
            body_nonce         BYTEA         NOT NULL,
            body_tag           BYTEA         NOT NULL,
            key_version        INTEGER       NOT NULL DEFAULT 1,
            budget             JSONB,
            created_at         TIMESTAMPTZ   NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_plan_versions_plan_id
        ON plan_versions (plan_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS plan_versions")
    op.execute("DROP TABLE IF EXISTS plans")
    op.execute("DROP TABLE IF EXISTS rate_card_items")
