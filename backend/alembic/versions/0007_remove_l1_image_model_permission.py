"""Remove anomalous L1 permission for gemini-2.5-flash-image

The baseline migration grants L1 only qwen2.5-14b-local. An extra
role_model_permissions row for L1 → gemini-2.5-flash-image was present in
the DB without a corresponding migration. This migration removes it so that
the DB matches the intended policy: L1 has local-only access.

Revision ID: 0007_remove_l1_image_model_permission
Revises: 0006_image_model_catalog
Create Date: 2026-06-08

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0007_fix_l1_perms"
down_revision: Union[str, None] = "0006_image_model_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DELETE FROM role_model_permissions
        WHERE role = 'L1'::role_level
          AND model_id = (
              SELECT id FROM model_catalog WHERE code = 'gemini-2.5-flash-image'
          )
    """)


def downgrade() -> None:
    op.execute("""
        INSERT INTO role_model_permissions (role, model_id)
        SELECT 'L1'::role_level, id FROM model_catalog WHERE code = 'gemini-2.5-flash-image'
        ON CONFLICT DO NOTHING
    """)
