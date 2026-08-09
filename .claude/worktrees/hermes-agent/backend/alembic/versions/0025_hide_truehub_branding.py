"""Drop "(True AI Hub)" branding from GPT Image 1 display name

Admin console should not surface the True AI Hub brand name. The model
itself (GPT-Image-1) stays active and usable; only the display label changes.

Revision ID: 0025_hide_truehub_branding
Revises: 0024_agents_local_model
Create Date: 2026-07-01

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0025_hide_truehub_branding"
down_revision: Union[str, None] = "0024_agents_local_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CODE = "GPT-Image-1"
_OLD_NAME = "GPT Image 1 (True AI Hub)"
_NEW_NAME = "GPT Image 1"


def upgrade() -> None:
    op.execute(f"""
        UPDATE model_catalog SET display_name = '{_NEW_NAME}'
        WHERE code = '{_CODE}' AND display_name = '{_OLD_NAME}'
    """)


def downgrade() -> None:
    op.execute(f"""
        UPDATE model_catalog SET display_name = '{_OLD_NAME}'
        WHERE code = '{_CODE}' AND display_name = '{_NEW_NAME}'
    """)
