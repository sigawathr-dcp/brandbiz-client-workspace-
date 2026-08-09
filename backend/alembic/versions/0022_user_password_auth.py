"""Add username + password_hash columns for mock email/username+password login

Revision ID: 0022_user_password_auth
Revises: 0021_veo_3_1_lite_video_model
Create Date: 2026-07-01

Google OAuth (D11) remains the intended production auth path. These columns
back a local/mock login (see scripts/seed_mock_users.py, app/routers/auth.py
POST /auth/login) used only while GOOGLE_OAUTH_CLIENT_ID is unset.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0022_user_password_auth"
down_revision: Union[str, None] = "0021_veo_3_1_lite_video_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS username VARCHAR(255) UNIQUE,
        ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE users
        DROP COLUMN IF EXISTS username,
        DROP COLUMN IF EXISTS password_hash
        """
    )
