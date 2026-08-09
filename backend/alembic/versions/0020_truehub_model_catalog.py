"""Add True AI Hub verbatim model codes to catalog with role permissions

Adds catalog rows for the exact model-name strings used in the True AI Hub
agent dataset, wired to real underlying providers. All roles L1–ADMIN get
access so any seeded user can chat with these agents.

Revision ID: 0020_truehub_model_catalog
Revises: 0019_agent_audit_actions
Create Date: 2026-06-23
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0020_truehub_model_catalog"
down_revision: Union[str, None] = "0019_agent_audit_actions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Verbatim codes from True_AI_agent_data.md → (display_name, provider, supports_images)
_MODELS = [
    ("gpt-5-nano",                   "GPT-5 Nano",                    "openai",     False),
    ("GPT 5.1",                      "GPT 5.1",                       "openai",     False),
    ("@b2c-production-openai/gpt-5", "GPT-5 (B2C Production)",        "openai",     False),
    ("Gemini 2.5 Pro",               "Gemini 2.5 Pro",                "google",     False),
    ("Claude Sonnet 4.5",            "Claude Sonnet 4.5",             "anthropic",  False),
    ("Claude Sonnet 4.6",            "Claude Sonnet 4.6",             "anthropic",  False),
    ("GPT-Image-1",                  "GPT Image 1 (True AI Hub)",     "openai",     True),
]

_ROLES = ("L1", "L2", "L3", "L4", "L5", "L6", "ADMIN")


def upgrade() -> None:
    for code, display_name, provider, supports_images in _MODELS:
        img = "TRUE" if supports_images else "FALSE"
        op.execute(f"""
            INSERT INTO model_catalog
                (code, display_name, provider, is_local,
                 supports_images, is_active)
            SELECT
                '{code}', '{display_name}',
                '{provider}'::model_provider,
                FALSE, {img}, TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM model_catalog WHERE code = '{code}'
            )
        """)

        # Grant all roles (L1–ADMIN) so any seeded user can chat
        roles_sql = ", ".join(f"('{r}')" for r in _ROLES)
        op.execute(f"""
            INSERT INTO role_model_permissions (role, model_id)
            SELECT r.role::role_level, m.id
            FROM (VALUES {roles_sql}) AS r(role)
            CROSS JOIN model_catalog m
            WHERE m.code = '{code}'
            ON CONFLICT DO NOTHING
        """)


def downgrade() -> None:
    for code, _, _, _ in _MODELS:
        op.execute(f"""
            DELETE FROM role_model_permissions
            WHERE model_id = (SELECT id FROM model_catalog WHERE code = '{code}')
        """)
        op.execute(f"DELETE FROM model_catalog WHERE code = '{code}'")
