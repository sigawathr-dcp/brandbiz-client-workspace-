"""Seed gemini-3.1-flash-image into model_catalog and wire role/department permissions

Switches the active image model from gpt-image-1 to gemini-3.1-flash-image.
Adds the catalog row and grants access to Marketing department (MKT) and roles
L5/L6/ADMIN — mirroring the existing permission matrix for other image models.

The gpt-image-1 catalog row is intentionally left in place as a rollback path.

Revision ID: 0010_gemini_image_model
Revises: 0009_api_keys
Create Date: 2026-06-09

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0010_gemini_image_model"
down_revision: Union[str, None] = "0009_api_keys"
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
            'gemini-3.1-flash-image', 'Gemini 3.1 Flash Image', 'google'::model_provider, FALSE,
            NULL, NULL, NULL, TRUE, TRUE
        WHERE NOT EXISTS (
            SELECT 1 FROM model_catalog WHERE code = 'gemini-3.1-flash-image'
        )
    """)

    # Role permissions: L5, L6, ADMIN
    op.execute("""
        INSERT INTO role_model_permissions (role, model_id)
        SELECT r.role::role_level, m.id
        FROM (VALUES ('L5'), ('L6'), ('ADMIN')) AS r(role)
        CROSS JOIN model_catalog m
        WHERE m.code = 'gemini-3.1-flash-image'
        ON CONFLICT DO NOTHING
    """)

    # Department permission: MKT
    op.execute("""
        INSERT INTO department_model_permissions (department_id, model_id)
        SELECT d.id, m.id
        FROM departments d, model_catalog m
        WHERE d.code = 'MKT' AND m.code = 'gemini-3.1-flash-image'
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM department_model_permissions
        WHERE model_id = (SELECT id FROM model_catalog WHERE code = 'gemini-3.1-flash-image')
    """)
    op.execute("""
        DELETE FROM role_model_permissions
        WHERE model_id = (SELECT id FROM model_catalog WHERE code = 'gemini-3.1-flash-image')
    """)
    op.execute("DELETE FROM model_catalog WHERE code = 'gemini-3.1-flash-image'")
