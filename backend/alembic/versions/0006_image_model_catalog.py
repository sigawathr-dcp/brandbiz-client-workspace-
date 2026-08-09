"""Seed gpt-image-1 into model_catalog and wire role/department permissions

gpt-image-1 was previously hardcoded in app/tools/image_gen.py with no catalog
row and therefore no PolicyEngine visibility. This migration adds the catalog row
and grants access to Marketing department (MKT) and roles L5/L6/ADMIN — mirroring
the existing gemini-2.5-flash-image permission matrix.

Revision ID: 0006_image_model_catalog
Revises: 0005_image_gen_audit_actions
Create Date: 2026-06-08

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0006_image_model_catalog"
down_revision: Union[str, None] = "0005_image_gen_audit_actions"
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
            'gpt-image-1', 'GPT Image 1', 'openai'::model_provider, FALSE,
            NULL, NULL, NULL, TRUE, TRUE
        WHERE NOT EXISTS (
            SELECT 1 FROM model_catalog WHERE code = 'gpt-image-1'
        )
    """)

    # Role permissions: L5, L6, ADMIN (same tiers that hold gemini-2.5-flash-image)
    op.execute("""
        INSERT INTO role_model_permissions (role, model_id)
        SELECT r.role::role_level, m.id
        FROM (VALUES ('L5'), ('L6'), ('ADMIN')) AS r(role)
        CROSS JOIN model_catalog m
        WHERE m.code = 'gpt-image-1'
        ON CONFLICT DO NOTHING
    """)

    # Department permission: MKT
    op.execute("""
        INSERT INTO department_model_permissions (department_id, model_id)
        SELECT d.id, m.id
        FROM departments d, model_catalog m
        WHERE d.code = 'MKT' AND m.code = 'gpt-image-1'
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM department_model_permissions
        WHERE model_id = (SELECT id FROM model_catalog WHERE code = 'gpt-image-1')
    """)
    op.execute("""
        DELETE FROM role_model_permissions
        WHERE model_id = (SELECT id FROM model_catalog WHERE code = 'gpt-image-1')
    """)
    op.execute("DELETE FROM model_catalog WHERE code = 'gpt-image-1'")
