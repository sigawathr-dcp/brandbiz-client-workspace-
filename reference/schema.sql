-- =============================================================================
-- Company AI Gateway - Database Schema
-- Postgres 16+ with pgvector
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- 1. Identity & Access
-- =============================================================================

CREATE TABLE departments (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    google_group_email VARCHAR(255),  -- for SCIM/group sync
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TYPE role_level AS ENUM ('L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'ADMIN');

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    google_email VARCHAR(255) UNIQUE NOT NULL,
    google_sub VARCHAR(255) UNIQUE,             -- stable Google user ID
    display_name VARCHAR(255),
    avatar_url TEXT,
    role role_level NOT NULL DEFAULT 'L1',
    is_active BOOLEAN DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_users_email ON users(google_email);
CREATE INDEX idx_users_role ON users(role) WHERE is_active = TRUE;

CREATE TABLE user_departments (
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    department_id INT REFERENCES departments(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, department_id)
);

-- =============================================================================
-- 2. Model Catalog & Permissions
-- =============================================================================

CREATE TYPE model_provider AS ENUM ('local', 'anthropic', 'openai', 'google', 'perplexity');

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
);

CREATE TABLE role_model_permissions (
    role role_level NOT NULL,
    model_id INT REFERENCES model_catalog(id) ON DELETE CASCADE,
    PRIMARY KEY (role, model_id)
);

CREATE TABLE department_model_permissions (
    department_id INT REFERENCES departments(id) ON DELETE CASCADE,
    model_id INT REFERENCES model_catalog(id) ON DELETE CASCADE,
    PRIMARY KEY (department_id, model_id)
);

-- =============================================================================
-- 3. Quotas (monthly, per user)
-- =============================================================================

CREATE TABLE quotas (
    id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    period_start DATE NOT NULL,
    tokens_limit BIGINT NOT NULL,
    tokens_used BIGINT DEFAULT 0,
    cost_used_usd NUMERIC(10, 4) DEFAULT 0,
    UNIQUE (user_id, period_start)
);
CREATE INDEX idx_quotas_user_period ON quotas(user_id, period_start);

CREATE TABLE quota_defaults (
    role role_level PRIMARY KEY,
    monthly_token_limit BIGINT NOT NULL
);

-- =============================================================================
-- 4. Data Classification
-- =============================================================================

CREATE TYPE data_tier AS ENUM (
    'TIER_1_PUBLIC',
    'TIER_2_INTERNAL',
    'TIER_3_CONFIDENTIAL',
    'TIER_4_RESTRICTED'
);

CREATE TABLE data_classification_rules (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    pattern_type VARCHAR(50) NOT NULL,  -- 'regex' | 'ner' | 'keyword'
    pattern TEXT NOT NULL,
    detected_tier data_tier NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- =============================================================================
-- 5. Conversations & Messages (content encrypted at app layer)
-- =============================================================================

CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(500),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_conv_user ON conversations(user_id, updated_at DESC);

CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system', 'tool');

CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role message_role NOT NULL,

    -- AES-256-GCM encrypted content. Decryption requires app key + 4-eyes flow.
    content_ciphertext BYTEA NOT NULL,
    content_nonce      BYTEA NOT NULL,  -- 12 bytes
    content_tag        BYTEA NOT NULL,  -- 16 bytes (auth tag)
    key_version        INT   NOT NULL DEFAULT 1,

    -- Metadata (unencrypted, used for indexing/admin views/quota)
    detected_tier data_tier,
    model_used    VARCHAR(100),
    tokens_input  INT,
    tokens_output INT,
    cost_usd      NUMERIC(10, 6),
    latency_ms    INT,

    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_msg_conv ON messages(conversation_id, created_at);
CREATE INDEX idx_msg_created ON messages(created_at);  -- for retention purge

-- =============================================================================
-- 6. Audit Log (immutable, partitioned by month)
-- =============================================================================

CREATE TYPE audit_action AS ENUM (
    'login', 'logout',
    'message_sent', 'message_received',
    'model_blocked', 'pii_detected', 'tier_blocked', 'quota_exceeded',
    'reveal_requested', 'reveal_approved', 'reveal_denied', 'reveal_viewed',
    'admin_user_created', 'admin_role_changed', 'admin_quota_changed',
    'admin_permission_changed', 'file_uploaded', 'rag_query'
);

CREATE TABLE audit_log (
    id BIGSERIAL,
    user_id UUID,
    actor_id UUID,
    action audit_action NOT NULL,
    resource_type VARCHAR(50),
    resource_id UUID,
    details JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE INDEX idx_audit_user ON audit_log(user_id, created_at DESC);
CREATE INDEX idx_audit_action ON audit_log(action, created_at DESC);

-- Example partitions (use pg_partman to automate, or create manually each month)
CREATE TABLE audit_log_2026_05 PARTITION OF audit_log
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
CREATE TABLE audit_log_2026_06 PARTITION OF audit_log
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');

-- =============================================================================
-- 7. Reveal Requests (4-eyes principle for decrypting messages)
-- =============================================================================

CREATE TYPE reveal_status AS ENUM ('pending', 'approved', 'denied', 'expired', 'completed');

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
);
CREATE INDEX idx_reveal_status ON reveal_requests(status, created_at);
CREATE INDEX idx_reveal_target ON reveal_requests(target_user_id);

-- =============================================================================
-- 8. Files & RAG (BGE-M3 = 1024 dims)
-- =============================================================================

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
);
CREATE INDEX idx_files_user ON files(user_id, created_at DESC);

CREATE TABLE file_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    file_id UUID REFERENCES files(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(1024),
    token_count INT,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_chunks_file ON file_chunks(file_id, chunk_index);
CREATE INDEX idx_chunks_embedding ON file_chunks USING hnsw (embedding vector_cosine_ops);

-- =============================================================================
-- 9. Retention: 30-day auto-purge for messages
-- =============================================================================
-- Schedule via pg_cron or Celery beat:
--   DELETE FROM messages WHERE created_at < now() - INTERVAL '30 days';
-- Keep audit_log forever (compliance), drop partitions older than retention window.

-- =============================================================================
-- 10. Seed data
-- =============================================================================

INSERT INTO quota_defaults (role, monthly_token_limit) VALUES
    ('L1',   50000),
    ('L2',  200000),
    ('L3',  500000),
    ('L4', 1000000),
    ('L5', 2000000),
    ('L6', 9223372036854775807),
    ('ADMIN', 9223372036854775807);

INSERT INTO model_catalog (code, display_name, provider, is_local,
    cost_per_1k_input_tokens, cost_per_1k_output_tokens, max_context_tokens, supports_images) VALUES
    ('qwen2.5-14b-local',     'Qwen 2.5 14B (Local)', 'local',      TRUE,  0,        0,        32768,  FALSE),
    ('gpt-4o-mini',           'GPT-4o-mini',          'openai',     FALSE, 0.00015,  0.0006,   128000, TRUE),
    ('claude-sonnet-4',       'Claude Sonnet 4',      'anthropic',  FALSE, 0.003,    0.015,    200000, TRUE),
    ('gpt-4o',                'GPT-4o',               'openai',     FALSE, 0.005,    0.015,    128000, TRUE),
    ('claude-opus-4',         'Claude Opus 4',        'anthropic',  FALSE, 0.015,    0.075,    200000, TRUE),
    ('gemini-2.5-flash-image','Gemini Image',         'google',     FALSE, 0.000075, 0.0003,   32768,  TRUE),
    ('perplexity-sonar',      'Perplexity Sonar',     'perplexity', FALSE, 0.001,    0.001,    127000, FALSE);

-- Role -> Model permission matrix
WITH model_ids AS (SELECT id, code FROM model_catalog)
INSERT INTO role_model_permissions (role, model_id)
SELECT 'L1', id FROM model_ids WHERE code = 'qwen2.5-14b-local'
UNION ALL SELECT 'L2', id FROM model_ids WHERE code IN ('qwen2.5-14b-local','gpt-4o-mini')
UNION ALL SELECT 'L3', id FROM model_ids WHERE code IN ('qwen2.5-14b-local','gpt-4o-mini','claude-sonnet-4','perplexity-sonar')
UNION ALL SELECT 'L4', id FROM model_ids WHERE code IN ('qwen2.5-14b-local','gpt-4o-mini','claude-sonnet-4','gpt-4o','claude-opus-4','perplexity-sonar')
UNION ALL SELECT 'L5', id FROM model_ids
UNION ALL SELECT 'L6', id FROM model_ids
UNION ALL SELECT 'ADMIN', id FROM model_ids;

-- Thai PDPA PII patterns
INSERT INTO data_classification_rules (name, pattern_type, pattern, detected_tier, description) VALUES
    ('Thai National ID',  'regex', '\d-\d{4}-\d{5}-\d{2}-\d',                              'TIER_3_CONFIDENTIAL', 'เลขบัตรประชาชนไทย 13 หลัก'),
    ('Thai Mobile',       'regex', '0[689]\d{8}',                                          'TIER_3_CONFIDENTIAL', 'เบอร์มือถือไทย'),
    ('Email',             'regex', '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',       'TIER_3_CONFIDENTIAL', 'อีเมล'),
    ('Bank Account TH',   'regex', '\d{3}-\d-\d{5}-\d',                                    'TIER_3_CONFIDENTIAL', 'เลขบัญชีธนาคารไทย'),
    ('Credit Card',       'regex', '\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}',               'TIER_3_CONFIDENTIAL', 'เลขบัตรเครดิต');

INSERT INTO departments (code, name) VALUES
    ('ENG',         'Engineering'),
    ('MKT',         'Marketing & Creative'),
    ('SALES',       'Sales'),
    ('FIN',         'Finance'),
    ('HR',          'Human Resources'),
    ('LEGAL',       'Legal'),
    ('OPS',         'Operations'),
    ('RESEARCH',    'Research');

-- Marketing department gets Gemini Image add-on
INSERT INTO department_model_permissions (department_id, model_id)
SELECT d.id, m.id
FROM departments d, model_catalog m
WHERE d.code = 'MKT' AND m.code = 'gemini-2.5-flash-image';
