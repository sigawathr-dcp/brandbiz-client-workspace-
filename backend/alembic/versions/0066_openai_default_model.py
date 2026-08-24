"""D25 — OpenAI becomes the default chat + embedding provider

1. model_catalog: add gpt-5.4-mini-2026-03-17 (the LLM_DEFAULT_MODEL) and
   grant it to every role so it also appears in the external-permission
   listings. PolicyEngine Rule 1 allows the default model regardless of
   permission rows; the grant is for display/admin consistency.
2. agents: bulk-switch every agent to the new default (same lossy reset as
   0024_agents_local_model, which pointed them at gemma4:26b).
3. file_chunks.embedding: VECTOR(1024) BGE-M3 -> VECTOR(1536)
   text-embedding-3-small. Existing vectors are dropped (dimension change
   makes them unusable) and files.is_processed is reset so rag_search's
   "processed files only" scope excludes them until re-ingested. Re-run
   ingestion (services/ingestion.process_file) for every file afterwards.

Revision ID: 0066_openai_default_model
Revises: 0065_case_library_scope
Create Date: 2026-08-25
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0066_openai_default_model"
down_revision: Union[str, None] = "0065_case_library_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_MODEL_CODE = "gpt-5.4-mini-2026-03-17"


def upgrade() -> None:
    # 1. Catalog row — $0.75 / $4.50 per 1M tokens (OpenAI list price, 2026-03).
    op.execute(f"""
        INSERT INTO model_catalog
            (code, display_name, provider, is_local,
             cost_per_1k_input_tokens, cost_per_1k_output_tokens,
             max_context_tokens, supports_images, supports_tools, is_active)
        SELECT
            '{DEFAULT_MODEL_CODE}', 'GPT-5.4 mini', 'openai'::model_provider, FALSE,
            0.00075, 0.0045, 400000, TRUE, TRUE, TRUE
        WHERE NOT EXISTS (
            SELECT 1 FROM model_catalog WHERE code = '{DEFAULT_MODEL_CODE}'
        )
    """)
    op.execute(f"""
        INSERT INTO role_model_permissions (role, model_id)
        SELECT r.role, m.id
        FROM unnest(ARRAY['L1','L2','L3','L4','L5','L6','ADMIN']::role_level[]) AS r(role)
        CROSS JOIN model_catalog m
        WHERE m.code = '{DEFAULT_MODEL_CODE}'
          AND NOT EXISTS (
              SELECT 1 FROM role_model_permissions p
              WHERE p.role = r.role AND p.model_id = m.id
          )
    """)

    # 2. Agents -> default model.
    op.execute(f"""
        UPDATE agents
        SET provider = 'openai', model = '{DEFAULT_MODEL_CODE}', updated_at = now()
    """)

    # 3. Embedding column 1024 -> 1536. Vectors from the old model cannot be
    #    reused, so they are nulled and files flagged for re-ingestion.
    op.execute("DROP INDEX IF EXISTS idx_chunks_embedding")
    op.execute("UPDATE file_chunks SET embedding = NULL")
    op.execute("ALTER TABLE file_chunks ALTER COLUMN embedding TYPE vector(1536)")
    op.execute(
        "CREATE INDEX idx_chunks_embedding ON file_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("UPDATE files SET is_processed = FALSE")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_chunks_embedding")
    op.execute("UPDATE file_chunks SET embedding = NULL")
    op.execute("ALTER TABLE file_chunks ALTER COLUMN embedding TYPE vector(1024)")
    op.execute(
        "CREATE INDEX idx_chunks_embedding ON file_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("UPDATE files SET is_processed = FALSE")
    # Agents: lossy (like 0024) — point them back at the local baseline.
    op.execute("""
        UPDATE agents
        SET provider = 'local', model = 'gemma4:26b', updated_at = now()
    """)
    op.execute(f"""
        DELETE FROM role_model_permissions
        WHERE model_id = (SELECT id FROM model_catalog WHERE code = '{DEFAULT_MODEL_CODE}')
    """)
    op.execute(f"DELETE FROM model_catalog WHERE code = '{DEFAULT_MODEL_CODE}'")
