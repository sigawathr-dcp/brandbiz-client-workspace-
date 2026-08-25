"""Rename the client-facing persona from "น้องภูมิ" to "น้อง brandbiz"

Copy-only rename. The persona's name is baked into the intake question and
insight text of every published script version, and the running app reads
those rows from the database (client_intake's *_db functions), not from the
INTAKE_SCRIPT literal — so editing the literal alone renames the persona on
a rebuilt database while every already-migrated one keeps saying "น้องภูมิ".

This touches PUBLISHED intake_questions rows, which the versioning rule in
client_intake's module docstring normally forbids. Same carve-out migration
0064 took for `multi_select`: the rule exists so that a stored answer is
never REINTERPRETED against a vocabulary it was not collected under, and a
persona name in prose is not vocabulary — no field_key, option, value, tag,
weight or use_mode moves here. An answer given to "ผมน้องภูมิ ..." means
exactly what it meant before.

It runs across ALL versions (v1 frozen in 0052, v2 in 0060, v3 in 0062) on
purpose. The frozen literals stay frozen — they still reproduce their own
publication byte-for-byte — and applying this rename on top of them leaves a
rebuilt database in the same final state as an upgraded one.

Not covered here: the `agents` row that carries the persona (name +
instructions). That is operational data seeded per environment
(scripts/seed_client_demo.py, or CLIENT_TEMPLATE_AGENT_ID's template row),
so it is renamed in the admin UI / by re-running the seed, not by a
migration that would rewrite rows an admin may have edited by hand.

Revision ID: 0067_rename_persona
Revises: 0066_openai_default_model
Create Date: 2026-08-25
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0067_rename_persona"
down_revision: Union[str, None] = "0066_openai_default_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD = "น้องภูมิ"
_NEW = "น้อง brandbiz"


def _rewrite(old: str, new: str) -> None:
    op.get_bind().execute(text("""
        UPDATE intake_questions
        SET prompt = REPLACE(prompt, :old, :new),
            insight = REPLACE(insight, :old, :new)
        WHERE prompt LIKE '%' || :old || '%'
           OR insight LIKE '%' || :old || '%'
    """), {"old": old, "new": new})


def upgrade() -> None:
    _rewrite(_OLD, _NEW)


def downgrade() -> None:
    _rewrite(_NEW, _OLD)
