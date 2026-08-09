"""Create studio_generations table

Revision ID: 0011_studio_generations
Revises: 0010_gemini_image_model
Create Date: 2026-06-19
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0011_studio_generations"
down_revision: Union[str, None] = "0010_gemini_image_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: CREATE TABLE IF NOT EXISTS + IF NOT EXISTS index
    op.execute("""
        CREATE TABLE IF NOT EXISTS studio_generations (
            id          UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            type        VARCHAR(16)   NOT NULL,
            model_label VARCHAR(100)  NOT NULL,
            prompt_ciphertext BYTEA   NOT NULL,
            prompt_nonce      BYTEA   NOT NULL,
            prompt_tag        BYTEA   NOT NULL,
            key_version INTEGER       NOT NULL DEFAULT 1,
            settings    JSONB,
            status      VARCHAR(16)   NOT NULL DEFAULT 'mocked',
            output_ref  VARCHAR(4000),
            token_cost  INTEGER,
            created_at  TIMESTAMPTZ   NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_studio_generations_user_id
        ON studio_generations (user_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS studio_generations")
