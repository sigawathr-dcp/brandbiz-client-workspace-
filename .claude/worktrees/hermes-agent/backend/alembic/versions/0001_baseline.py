"""Baseline schema: all tables, enums, indexes, and seed data from schema.sql

Revision ID: 0001_baseline
Revises:
Create Date: 2026-05-26

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Extensions
    # ------------------------------------------------------------------
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto')
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ------------------------------------------------------------------
    # ENUM types (created before first reference)
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TYPE role_level AS ENUM (
            'L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'ADMIN'
        )
    """)

    op.execute("""
        CREATE TYPE model_provider AS ENUM (
            'local', 'anthropic', 'openai', 'google', 'perplexity'
        )
    """)

    op.execute("""
        CREATE TYPE data_tier AS ENUM (
            'TIER_1_PUBLIC',
            'TIER_2_INTERNAL',
            'TIER_3_CONFIDENTIAL',
            'TIER_4_RESTRICTED'
        )
    """)

    op.execute("""
        CREATE TYPE message_role AS ENUM (
            'user', 'assistant', 'system', 'tool'
        )
    """)

    op.execute("""
        CREATE TYPE audit_action AS ENUM (
            'login', 'logout',
            'message_sent', 'message_received',
            'model_blocked', 'pii_detected', 'tier_blocked', 'quota_exceeded',
            'reveal_requested', 'reveal_approved', 'reveal_denied', 'reveal_viewed',
            'admin_user_created', 'admin_role_changed', 'admin_quota_changed',
            'admin_permission_changed', 'file_uploaded', 'rag_query'
        )
    """)

    op.execute("""
        CREATE TYPE reveal_status AS ENUM (
            'pending', 'approved', 'denied', 'expired', 'completed'
        )
    """)

    # ------------------------------------------------------------------
    # 1. Identity & Access
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE departments (
            id SERIAL PRIMARY KEY,
            code VARCHAR(50) UNIQUE NOT NULL,
            name VARCHAR(255) NOT NULL,
            google_group_email VARCHAR(255),
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            google_email VARCHAR(255) UNIQUE NOT NULL,
            google_sub VARCHAR(255) UNIQUE,
            display_name VARCHAR(255),
            avatar_url TEXT,
            role role_level NOT NULL DEFAULT 'L1',
            is_active BOOLEAN DEFAULT TRUE,
            last_login_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute('CREATE INDEX idx_users_email ON users(google_email)')
    op.execute('CREATE INDEX idx_users_role ON users(role) WHERE is_active = TRUE')

    op.execute("""
        CREATE TABLE user_departments (
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            department_id INT REFERENCES departments(id) ON DELETE CASCADE,
            PRIMARY KEY (user_id, department_id)
        )
    """)

    # ------------------------------------------------------------------
    # 2. Model Catalog & Permissions
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE model_catalog (
            id SERIAL PRIMARY KEY,
            code VARCHAR(100) UNIQUE NOT NULL,
            display_name VARCHAR(255) NOT NULL,
            provider model_provider NOT NULL,
            is_local BOOLEAN NOT NULL,
            cost_per_1k_input_tokens NUMERIC(10, 6) DEFAULT 0,
            cost_per_1k_output_tokens NUMERIC(10, 6) DEFAULT 0,
            max_context_tokens INT,
            supports_images BOOLEAN DEFAULT FALSE,
            supports_tools BOOLEAN DEFAULT TRUE,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE role_model_permissions (
            role role_level NOT NULL,
            model_id INT REFERENCES model_catalog(id) ON DELETE CASCADE,
            PRIMARY KEY (role, model_id)
        )
    """)

    op.execute("""
        CREATE TABLE department_model_permissions (
            department_id INT REFERENCES departments(id) ON DELETE CASCADE,
            model_id INT REFERENCES model_catalog(id) ON DELETE CASCADE,
            PRIMARY KEY (department_id, model_id)
        )
    """)

    # ------------------------------------------------------------------
    # 3. Quotas
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE quotas (
            id SERIAL PRIMARY KEY,
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            period_start DATE NOT NULL,
            tokens_limit BIGINT NOT NULL,
            tokens_used BIGINT DEFAULT 0,
            cost_used_usd NUMERIC(10, 4) DEFAULT 0,
            UNIQUE (user_id, period_start)
        )
    """)

    op.execute('CREATE INDEX idx_quotas_user_period ON quotas(user_id, period_start)')

    op.execute("""
        CREATE TABLE quota_defaults (
            role role_level PRIMARY KEY,
            monthly_token_limit BIGINT NOT NULL
        )
    """)

    # ------------------------------------------------------------------
    # 4. Data Classification
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE data_classification_rules (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            pattern_type VARCHAR(50) NOT NULL,
            pattern TEXT NOT NULL,
            detected_tier data_tier NOT NULL,
            description TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    # ------------------------------------------------------------------
    # 5. Conversations & Messages
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE conversations (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            title VARCHAR(500),
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute('CREATE INDEX idx_conv_user ON conversations(user_id, updated_at DESC)')

    op.execute("""
        CREATE TABLE messages (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
            role message_role NOT NULL,
            content_ciphertext BYTEA NOT NULL,
            content_nonce BYTEA NOT NULL,
            content_tag BYTEA NOT NULL,
            key_version INT NOT NULL DEFAULT 1,
            detected_tier data_tier,
            model_used VARCHAR(100),
            tokens_input INT,
            tokens_output INT,
            cost_usd NUMERIC(10, 6),
            latency_ms INT,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute('CREATE INDEX idx_msg_conv ON messages(conversation_id, created_at)')
    op.execute('CREATE INDEX idx_msg_created ON messages(created_at)')

    # ------------------------------------------------------------------
    # 6. Audit Log (append-only, see Section 7.3)
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE audit_log (
            id BIGSERIAL PRIMARY KEY,
            user_id UUID,
            actor_id UUID,
            action audit_action NOT NULL,
            resource_type VARCHAR(50),
            resource_id UUID,
            details JSONB,
            ip_address INET,
            user_agent TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute('CREATE INDEX idx_audit_user ON audit_log(user_id, created_at DESC)')
    op.execute('CREATE INDEX idx_audit_action ON audit_log(action, created_at DESC)')

    # ------------------------------------------------------------------
    # 7. Reveal Requests (4-eyes principle)
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE reveal_requests (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            requester_id UUID REFERENCES users(id),
            target_user_id UUID REFERENCES users(id),
            target_conversation_id UUID REFERENCES conversations(id),
            target_message_id UUID REFERENCES messages(id),
            reason TEXT NOT NULL,
            status reveal_status DEFAULT 'pending',
            approver_id UUID REFERENCES users(id),
            approved_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ,
            viewed_at TIMESTAMPTZ,
            notified_target_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now(),
            CONSTRAINT no_self_approve CHECK (requester_id != approver_id)
        )
    """)

    op.execute('CREATE INDEX idx_reveal_status ON reveal_requests(status, created_at)')
    op.execute('CREATE INDEX idx_reveal_target ON reveal_requests(target_user_id)')

    # ------------------------------------------------------------------
    # 8. Files & RAG (BGE-M3 = 1024 dims)
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE files (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            filename VARCHAR(500) NOT NULL,
            mime_type VARCHAR(100),
            size_bytes BIGINT,
            s3_key VARCHAR(500) NOT NULL,
            sha256_hash VARCHAR(64),
            detected_tier data_tier,
            is_processed BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute('CREATE INDEX idx_files_user ON files(user_id, created_at DESC)')

    op.execute("""
        CREATE TABLE file_chunks (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            file_id UUID REFERENCES files(id) ON DELETE CASCADE,
            chunk_index INT NOT NULL,
            content TEXT NOT NULL,
            embedding VECTOR(1024),
            token_count INT,
            metadata JSONB,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute('CREATE INDEX idx_chunks_file ON file_chunks(file_id, chunk_index)')
    op.execute(
        'CREATE INDEX idx_chunks_embedding ON file_chunks '
        'USING hnsw (embedding vector_cosine_ops)'
    )

    # ------------------------------------------------------------------
    # 10. Seed data
    # ------------------------------------------------------------------
    op.execute("""
        INSERT INTO quota_defaults (role, monthly_token_limit) VALUES
            ('L1'::role_level,      50000),
            ('L2'::role_level,     200000),
            ('L3'::role_level,     500000),
            ('L4'::role_level,   1000000),
            ('L5'::role_level,   2000000),
            ('L6'::role_level,   9223372036854775807),
            ('ADMIN'::role_level, 9223372036854775807)
    """)

    op.execute("""
        INSERT INTO model_catalog
            (code, display_name, provider, is_local,
             cost_per_1k_input_tokens, cost_per_1k_output_tokens,
             max_context_tokens, supports_images)
        VALUES
            ('qwen2.5-14b-local',      'Qwen 2.5 14B (Local)',  'local'::model_provider,       TRUE,  0,        0,       32768,  FALSE),
            ('gpt-4o-mini',            'GPT-4o-mini',           'openai'::model_provider,      FALSE, 0.00015,  0.0006,  128000, TRUE),
            ('claude-sonnet-4',        'Claude Sonnet 4',       'anthropic'::model_provider,   FALSE, 0.003,    0.015,   200000, TRUE),
            ('gpt-4o',                 'GPT-4o',                'openai'::model_provider,      FALSE, 0.005,    0.015,   128000, TRUE),
            ('claude-opus-4',          'Claude Opus 4',         'anthropic'::model_provider,   FALSE, 0.015,    0.075,   200000, TRUE),
            ('gemini-2.5-flash-image', 'Gemini Image',          'google'::model_provider,      FALSE, 0.000075, 0.0003,  32768,  TRUE),
            ('perplexity-sonar',       'Perplexity Sonar',      'perplexity'::model_provider,  FALSE, 0.001,    0.001,   127000, FALSE)
    """)

    op.execute("""
        WITH model_ids AS (SELECT id, code FROM model_catalog)
        INSERT INTO role_model_permissions (role, model_id)
        SELECT 'L1'::role_level, id FROM model_ids WHERE code = 'qwen2.5-14b-local'
        UNION ALL SELECT 'L2'::role_level, id FROM model_ids WHERE code IN ('qwen2.5-14b-local', 'gpt-4o-mini')
        UNION ALL SELECT 'L3'::role_level, id FROM model_ids WHERE code IN ('qwen2.5-14b-local', 'gpt-4o-mini', 'claude-sonnet-4', 'perplexity-sonar')
        UNION ALL SELECT 'L4'::role_level, id FROM model_ids WHERE code IN ('qwen2.5-14b-local', 'gpt-4o-mini', 'claude-sonnet-4', 'gpt-4o', 'claude-opus-4', 'perplexity-sonar')
        UNION ALL SELECT 'L5'::role_level, id FROM model_ids
        UNION ALL SELECT 'L6'::role_level, id FROM model_ids
        UNION ALL SELECT 'ADMIN'::role_level, id FROM model_ids
    """)

    op.execute(r"""
        INSERT INTO data_classification_rules
            (name, pattern_type, pattern, detected_tier, description)
        VALUES
            ('Thai National ID', 'regex', '\d-\d{4}-\d{5}-\d{2}-\d',                          'TIER_3_CONFIDENTIAL'::data_tier, 'เลขบัตรประชาชนไทย 13 หลัก'),
            ('Thai Mobile',      'regex', '0[689]\d{8}',                                      'TIER_3_CONFIDENTIAL'::data_tier, 'เบอร์มือถือไทย'),
            ('Email',            'regex', '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',   'TIER_3_CONFIDENTIAL'::data_tier, 'อีเมล'),
            ('Bank Account TH',  'regex', '\d{3}-\d-\d{5}-\d',                                'TIER_3_CONFIDENTIAL'::data_tier, 'เลขบัญชีธนาคารไทย'),
            ('Credit Card',      'regex', '\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}',           'TIER_3_CONFIDENTIAL'::data_tier, 'เลขบัตรเครดิต')
    """)

    op.execute("""
        INSERT INTO departments (code, name) VALUES
            ('ENG',      'Engineering'),
            ('MKT',      'Marketing & Creative'),
            ('SALES',    'Sales'),
            ('FIN',      'Finance'),
            ('HR',       'Human Resources'),
            ('LEGAL',    'Legal'),
            ('OPS',      'Operations'),
            ('RESEARCH', 'Research')
    """)

    op.execute("""
        INSERT INTO department_model_permissions (department_id, model_id)
        SELECT d.id, m.id
        FROM departments d, model_catalog m
        WHERE d.code = 'MKT' AND m.code = 'gemini-2.5-flash-image'
    """)


def downgrade() -> None:
    # Drop in reverse dependency order
    op.execute('DROP TABLE IF EXISTS file_chunks')
    op.execute('DROP TABLE IF EXISTS files')
    op.execute('DROP TABLE IF EXISTS reveal_requests')
    op.execute('DROP TABLE IF EXISTS audit_log')
    op.execute('DROP TABLE IF EXISTS messages')
    op.execute('DROP TABLE IF EXISTS conversations')
    op.execute('DROP TABLE IF EXISTS data_classification_rules')
    op.execute('DROP TABLE IF EXISTS quota_defaults')
    op.execute('DROP TABLE IF EXISTS quotas')
    op.execute('DROP TABLE IF EXISTS department_model_permissions')
    op.execute('DROP TABLE IF EXISTS role_model_permissions')
    op.execute('DROP TABLE IF EXISTS model_catalog')
    op.execute('DROP TABLE IF EXISTS user_departments')
    op.execute('DROP TABLE IF EXISTS users')
    op.execute('DROP TABLE IF EXISTS departments')

    op.execute('DROP TYPE IF EXISTS reveal_status')
    op.execute('DROP TYPE IF EXISTS audit_action')
    op.execute('DROP TYPE IF EXISTS message_role')
    op.execute('DROP TYPE IF EXISTS data_tier')
    op.execute('DROP TYPE IF EXISTS model_provider')
    op.execute('DROP TYPE IF EXISTS role_level')

    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
    op.execute('DROP EXTENSION IF EXISTS pgcrypto')
    op.execute('DROP EXTENSION IF EXISTS vector')
