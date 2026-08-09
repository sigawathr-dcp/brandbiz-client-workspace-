"""Seed veo-2.0-generate-001 into model_catalog and wire role/department permissions

Adds the Veo 2.0 catalog row and grants access to Marketing department (MKT)
and roles L5/L6/ADMIN — mirroring the permission matrix for the image model
(gemini-3.1-flash-image, migration 0010).

Revision ID: 0013_veo_video_model
Revises: 0012_studio_output_ref_text
Create Date: 2026-06-22

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0013_veo_video_model"
down_revision: Union[str, None] = "0012_studio_output_ref_text"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Insert catalog row (idempotent guard via WHERE NOT EXISTS)
    op.execute("""
        INSERT INTO model_catalog
            (code, display_name, provider, is_local,
             cost_per_1k_input_tokens, cost_per_1k_output_tokens,
             max_context_tokens, supports_images, is_active)
        SELECT
            'veo-2.0-generate-001', 'Veo 2.0', 'google'::model_provider, FALSE,
            NULL, NULL, NULL, FALSE, TRUE
        WHERE NOT EXISTS (
            SELECT 1 FROM model_catalog WHERE code = 'veo-2.0-generate-001'
        )
    """)

    # Role permissions: L5, L6, ADMIN
    op.execute("""
        INSERT INTO role_model_permissions (role, model_id)
        SELECT r.role::role_level, m.id
        FROM (VALUES ('L5'), ('L6'), ('ADMIN')) AS r(role)
        CROSS JOIN model_catalog m
        WHERE m.code = 'veo-2.0-generate-001'
        ON CONFLICT DO NOTHING
    """)

    # Department permission: MKT
    op.execute("""
        INSERT INTO department_model_permissions (department_id, model_id)
        SELECT d.id, m.id
        FROM departments d, model_catalog m
        WHERE d.code = 'MKT' AND m.code = 'veo-2.0-generate-001'
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM department_model_permissions
        WHERE model_id = (SELECT id FROM model_catalog WHERE code = 'veo-2.0-generate-001')
    """)
    op.execute("""
        DELETE FROM role_model_permissions
        WHERE model_id = (SELECT id FROM model_catalog WHERE code = 'veo-2.0-generate-001')
    """)
    op.execute("DELETE FROM model_catalog WHERE code = 'veo-2.0-generate-001'")
