"""Seed Lyria 3 Clip music model into model_catalog

Seeds lyria-3-clip-preview into model_catalog with L5/L6/ADMIN + MKT
permissions, matching the authorization gate used by image and video generation.

Revision ID: 0016_lyria_music_model
Revises: 0015_veo_3_1_video_model
Create Date: 2026-06-22

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0016_lyria_music_model"
down_revision: Union[str, None] = "0015_veo_3_1_video_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Insert Lyria 3 Clip catalog row (idempotent guard)
    op.execute("""
        INSERT INTO model_catalog
            (code, display_name, provider, is_local,
             cost_per_1k_input_tokens, cost_per_1k_output_tokens,
             max_context_tokens, supports_images, is_active)
        SELECT
            'lyria-3-clip-preview', 'Lyria 3 Clip', 'google'::model_provider, FALSE,
            NULL, NULL, NULL, FALSE, TRUE
        WHERE NOT EXISTS (
            SELECT 1 FROM model_catalog WHERE code = 'lyria-3-clip-preview'
        )
    """)

    # Role permissions: L5, L6, ADMIN
    op.execute("""
        INSERT INTO role_model_permissions (role, model_id)
        SELECT r.role::role_level, m.id
        FROM (VALUES ('L5'), ('L6'), ('ADMIN')) AS r(role)
        CROSS JOIN model_catalog m
        WHERE m.code = 'lyria-3-clip-preview'
        ON CONFLICT DO NOTHING
    """)

    # Department permission: MKT
    op.execute("""
        INSERT INTO department_model_permissions (department_id, model_id)
        SELECT d.id, m.id
        FROM departments d, model_catalog m
        WHERE d.code = 'MKT' AND m.code = 'lyria-3-clip-preview'
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    # Remove permissions and catalog row
    op.execute("""
        DELETE FROM department_model_permissions
        WHERE model_id = (SELECT id FROM model_catalog WHERE code = 'lyria-3-clip-preview')
    """)
    op.execute("""
        DELETE FROM role_model_permissions
        WHERE model_id = (SELECT id FROM model_catalog WHERE code = 'lyria-3-clip-preview')
    """)
    op.execute("DELETE FROM model_catalog WHERE code = 'lyria-3-clip-preview'")
