"""Seed hermes-agent into model_catalog and grant role permissions

Hermes Agent is an autonomous agent (runs tools/terminal/web per request),
not a plain chat model, so access defaults to L5/L6/ADMIN only — tunable
afterward via PUT /admin/permissions/role.

Revision ID: 0030_hermes_model_catalog
Revises: 0029_hermes_provider_enum
Create Date: 2026-07-13
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0030_hermes_model_catalog"
down_revision: Union[str, None] = "0029_hermes_provider_enum"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MODEL_CODE = "hermes-agent"
_ROLES = ("L5", "L6", "ADMIN")


def upgrade() -> None:
    op.execute(f"""
        INSERT INTO model_catalog
            (code, display_name, provider, is_local,
             supports_images, supports_tools, is_active)
        SELECT
            '{_MODEL_CODE}', 'Hermes Agent', 'hermes'::model_provider, FALSE,
            FALSE, TRUE, TRUE
        WHERE NOT EXISTS (
            SELECT 1 FROM model_catalog WHERE code = '{_MODEL_CODE}'
        )
    """)

    roles_sql = ", ".join(f"('{r}')" for r in _ROLES)
    op.execute(f"""
        INSERT INTO role_model_permissions (role, model_id)
        SELECT r.role::role_level, m.id
        FROM (VALUES {roles_sql}) AS r(role)
        CROSS JOIN model_catalog m
        WHERE m.code = '{_MODEL_CODE}'
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute(f"""
        DELETE FROM role_model_permissions
        WHERE model_id = (SELECT id FROM model_catalog WHERE code = '{_MODEL_CODE}')
    """)
    op.execute(f"DELETE FROM model_catalog WHERE code = '{_MODEL_CODE}'")
