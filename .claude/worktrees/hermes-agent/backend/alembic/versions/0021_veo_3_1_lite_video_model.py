"""Switch studio video model from Veo 3.1 to Veo 3.1 Lite

Seeds veo-3.1-lite-generate-preview into model_catalog with L5/L6/ADMIN + MKT
permissions, and deactivates the veo-3.1-generate-preview entry.

Revision ID: 0021_veo_3_1_lite_video_model
Revises: 0020_truehub_model_catalog
Create Date: 2026-06-24

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0021_veo_3_1_lite_video_model"
down_revision: Union[str, None] = "0020_truehub_model_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Insert Veo 3.1 Lite catalog row (idempotent guard)
    op.execute("""
        INSERT INTO model_catalog
            (code, display_name, provider, is_local,
             cost_per_1k_input_tokens, cost_per_1k_output_tokens,
             max_context_tokens, supports_images, is_active)
        SELECT
            'veo-3.1-lite-generate-preview', 'Veo 3.1 Lite', 'google'::model_provider, FALSE,
            NULL, NULL, NULL, FALSE, TRUE
        WHERE NOT EXISTS (
            SELECT 1 FROM model_catalog WHERE code = 'veo-3.1-lite-generate-preview'
        )
    """)

    # Role permissions: L5, L6, ADMIN
    op.execute("""
        INSERT INTO role_model_permissions (role, model_id)
        SELECT r.role::role_level, m.id
        FROM (VALUES ('L5'), ('L6'), ('ADMIN')) AS r(role)
        CROSS JOIN model_catalog m
        WHERE m.code = 'veo-3.1-lite-generate-preview'
        ON CONFLICT DO NOTHING
    """)

    # Department permission: MKT
    op.execute("""
        INSERT INTO department_model_permissions (department_id, model_id)
        SELECT d.id, m.id
        FROM departments d, model_catalog m
        WHERE d.code = 'MKT' AND m.code = 'veo-3.1-lite-generate-preview'
        ON CONFLICT DO NOTHING
    """)

    # Deactivate the old Veo 3.1 entry
    op.execute("""
        UPDATE model_catalog SET is_active = FALSE
        WHERE code = 'veo-3.1-generate-preview'
    """)


def downgrade() -> None:
    # Reactivate Veo 3.1
    op.execute("""
        UPDATE model_catalog SET is_active = TRUE
        WHERE code = 'veo-3.1-generate-preview'
    """)
    # Remove Veo 3.1 Lite permissions and catalog row
    op.execute("""
        DELETE FROM department_model_permissions
        WHERE model_id = (SELECT id FROM model_catalog WHERE code = 'veo-3.1-lite-generate-preview')
    """)
    op.execute("""
        DELETE FROM role_model_permissions
        WHERE model_id = (SELECT id FROM model_catalog WHERE code = 'veo-3.1-lite-generate-preview')
    """)
    op.execute("DELETE FROM model_catalog WHERE code = 'veo-3.1-lite-generate-preview'")
