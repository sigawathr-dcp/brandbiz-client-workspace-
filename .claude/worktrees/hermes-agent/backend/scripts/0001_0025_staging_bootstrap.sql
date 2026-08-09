-- Full schema bootstrap for an EMPTY database (e.g. staging).
-- Raw SQL equivalent of running every Alembic migration from
-- 0001_baseline through 0025_hide_truehub_branding in one shot.
--
-- Generated with:
--   alembic upgrade head --sql
-- (offline mode — compiles the migration chain to SQL without touching
-- a live DB; see backend/alembic/env.py: run_migrations_offline()).
-- Do not hand-edit; regenerate with the same command if migrations change.
--
-- Preconditions:
--   - Target database exists and is completely empty (no tables).
--   - Postgres 16 with the following extensions installable by the
--     connecting role: vector (pgvector), pgcrypto, "uuid-ossp".
--     (pgvector/pgvector:pg16 image satisfies this — PLAN.md D6 / Task 1.2.)
--
-- Usage:
--   docker compose exec -T postgres psql -U brandbiz -d brandbiz < backend/scripts/0001_0025_staging_bootstrap.sql
--   # or, against a remote staging host:
--   psql "$STAGING_DATABASE_URL" -f backend/scripts/0001_0025_staging_bootstrap.sql
--
-- This script creates and populates `alembic_version` itself, ending at
-- revision 0025_hide_truehub_branding — so no separate `alembic stamp`
-- step is needed afterwards. Once applied, `alembic upgrade head` against
-- this database will correctly report "already at head".
--
-- The whole script runs as a single transaction (BEGIN/COMMIT). This is
-- safe on Postgres 16: `ALTER TYPE ... ADD VALUE` is transactional as of
-- PG12+ (PLAN.md Section 8, Gotcha #5 only applies to older PG versions,
-- and nothing here reads a newly-added enum value within this same
-- transaction). If it fails partway through, nothing is committed —
-- safe to fix and re-run against the same empty database.
--
-- NOT idempotent against a non-empty database — this is a bootstrap
-- script for a fresh DB only. For applying individual deltas to an
-- already-migrated database, use the smaller per-revision scripts
-- (e.g. 0022_0023_user_password_auth.sql) or `alembic upgrade head`.

BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_baseline

CREATE EXTENSION IF NOT EXISTS vector;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TYPE role_level AS ENUM (
            'L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'ADMIN'
        );

CREATE TYPE model_provider AS ENUM (
            'local', 'anthropic', 'openai', 'google', 'perplexity'
        );

CREATE TYPE data_tier AS ENUM (
            'TIER_1_PUBLIC',
            'TIER_2_INTERNAL',
            'TIER_3_CONFIDENTIAL',
            'TIER_4_RESTRICTED'
        );

CREATE TYPE message_role AS ENUM (
            'user', 'assistant', 'system', 'tool'
        );

CREATE TYPE audit_action AS ENUM (
            'login', 'logout',
            'message_sent', 'message_received',
            'model_blocked', 'pii_detected', 'tier_blocked', 'quota_exceeded',
            'reveal_requested', 'reveal_approved', 'reveal_denied', 'reveal_viewed',
            'admin_user_created', 'admin_role_changed', 'admin_quota_changed',
            'admin_permission_changed', 'file_uploaded', 'rag_query'
        );

CREATE TYPE reveal_status AS ENUM (
            'pending', 'approved', 'denied', 'expired', 'completed'
        );

CREATE TABLE departments (
            id SERIAL PRIMARY KEY,
            code VARCHAR(50) UNIQUE NOT NULL,
            name VARCHAR(255) NOT NULL,
            google_group_email VARCHAR(255),
            created_at TIMESTAMPTZ DEFAULT now()
        );

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
        );

CREATE INDEX idx_users_email ON users(google_email);

CREATE INDEX idx_users_role ON users(role) WHERE is_active = TRUE;

CREATE TABLE user_departments (
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            department_id INT REFERENCES departments(id) ON DELETE CASCADE,
            PRIMARY KEY (user_id, department_id)
        );

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

CREATE TABLE data_classification_rules (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            pattern_type VARCHAR(50) NOT NULL,
            pattern TEXT NOT NULL,
            detected_tier data_tier NOT NULL,
            description TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT now()
        );

CREATE TABLE conversations (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            title VARCHAR(500),
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        );

CREATE INDEX idx_conv_user ON conversations(user_id, updated_at DESC);

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
        );

CREATE INDEX idx_msg_conv ON messages(conversation_id, created_at);

CREATE INDEX idx_msg_created ON messages(created_at);

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
        );

CREATE INDEX idx_audit_user ON audit_log(user_id, created_at DESC);

CREATE INDEX idx_audit_action ON audit_log(action, created_at DESC);

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

INSERT INTO quota_defaults (role, monthly_token_limit) VALUES
            ('L1'::role_level,      50000),
            ('L2'::role_level,     200000),
            ('L3'::role_level,     500000),
            ('L4'::role_level,   1000000),
            ('L5'::role_level,   2000000),
            ('L6'::role_level,   9223372036854775807),
            ('ADMIN'::role_level, 9223372036854775807);

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
            ('perplexity-sonar',       'Perplexity Sonar',      'perplexity'::model_provider,  FALSE, 0.001,    0.001,   127000, FALSE);

WITH model_ids AS (SELECT id, code FROM model_catalog)
        INSERT INTO role_model_permissions (role, model_id)
        SELECT 'L1'::role_level, id FROM model_ids WHERE code = 'qwen2.5-14b-local'
        UNION ALL SELECT 'L2'::role_level, id FROM model_ids WHERE code IN ('qwen2.5-14b-local', 'gpt-4o-mini')
        UNION ALL SELECT 'L3'::role_level, id FROM model_ids WHERE code IN ('qwen2.5-14b-local', 'gpt-4o-mini', 'claude-sonnet-4', 'perplexity-sonar')
        UNION ALL SELECT 'L4'::role_level, id FROM model_ids WHERE code IN ('qwen2.5-14b-local', 'gpt-4o-mini', 'claude-sonnet-4', 'gpt-4o', 'claude-opus-4', 'perplexity-sonar')
        UNION ALL SELECT 'L5'::role_level, id FROM model_ids
        UNION ALL SELECT 'L6'::role_level, id FROM model_ids
        UNION ALL SELECT 'ADMIN'::role_level, id FROM model_ids;

INSERT INTO data_classification_rules
            (name, pattern_type, pattern, detected_tier, description)
        VALUES
            ('Thai National ID', 'regex', '\d-\d{4}-\d{5}-\d{2}-\d',                          'TIER_3_CONFIDENTIAL'::data_tier, 'เลขบัตรประชาชนไทย 13 หลัก'),
            ('Thai Mobile',      'regex', '0[689]\d{8}',                                      'TIER_3_CONFIDENTIAL'::data_tier, 'เบอร์มือถือไทย'),
            ('Email',            'regex', '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',   'TIER_3_CONFIDENTIAL'::data_tier, 'อีเมล'),
            ('Bank Account TH',  'regex', '\d{3}-\d-\d{5}-\d',                                'TIER_3_CONFIDENTIAL'::data_tier, 'เลขบัญชีธนาคารไทย'),
            ('Credit Card',      'regex', '\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}',           'TIER_3_CONFIDENTIAL'::data_tier, 'เลขบัตรเครดิต');

INSERT INTO departments (code, name) VALUES
            ('ENG',      'Engineering'),
            ('MKT',      'Marketing & Creative'),
            ('SALES',    'Sales'),
            ('FIN',      'Finance'),
            ('HR',       'Human Resources'),
            ('LEGAL',    'Legal'),
            ('OPS',      'Operations'),
            ('RESEARCH', 'Research');

INSERT INTO department_model_permissions (department_id, model_id)
        SELECT d.id, m.id
        FROM departments d, model_catalog m
        WHERE d.code = 'MKT' AND m.code = 'gemini-2.5-flash-image';

INSERT INTO alembic_version (version_num) VALUES ('0001_baseline') RETURNING alembic_version.version_num;

-- Running upgrade 0001_baseline -> 0002_consent_acknowledged

ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'consent_acknowledged';

ALTER TABLE users ADD COLUMN consent_acknowledged_at TIMESTAMP WITH TIME ZONE;

UPDATE alembic_version SET version_num='0002_consent_acknowledged' WHERE alembic_version.version_num = '0001_baseline';

-- Running upgrade 0002_consent_acknowledged -> 0004_thai_id_compact

INSERT INTO data_classification_rules
            (name, pattern_type, pattern, detected_tier, description)
        SELECT
            'Thai National ID (compact)',
            'regex',
            '\d{13}',
            'TIER_3_CONFIDENTIAL'::data_tier,
            'เลขบัตรประชาชนไทย 13 หลัก (ไม่มีขีด) — ต้องผ่าน Mod-11 checksum'
        WHERE NOT EXISTS (
            SELECT 1 FROM data_classification_rules
            WHERE name = 'Thai National ID (compact)'
        );

UPDATE alembic_version SET version_num='0004_thai_id_compact' WHERE alembic_version.version_num = '0002_consent_acknowledged';

-- Running upgrade 0004_thai_id_compact -> 0005_image_gen_audit_actions

ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'image_requested';

ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'image_generated';

UPDATE alembic_version SET version_num='0005_image_gen_audit_actions' WHERE alembic_version.version_num = '0004_thai_id_compact';

-- Running upgrade 0005_image_gen_audit_actions -> 0006_image_model_catalog

INSERT INTO model_catalog
            (code, display_name, provider, is_local,
             cost_per_1k_input_tokens, cost_per_1k_output_tokens,
             max_context_tokens, supports_images, is_active)
        SELECT
            'gpt-image-1', 'GPT Image 1', 'openai'::model_provider, FALSE,
            NULL, NULL, NULL, TRUE, TRUE
        WHERE NOT EXISTS (
            SELECT 1 FROM model_catalog WHERE code = 'gpt-image-1'
        );

INSERT INTO role_model_permissions (role, model_id)
        SELECT r.role::role_level, m.id
        FROM (VALUES ('L5'), ('L6'), ('ADMIN')) AS r(role)
        CROSS JOIN model_catalog m
        WHERE m.code = 'gpt-image-1'
        ON CONFLICT DO NOTHING;

INSERT INTO department_model_permissions (department_id, model_id)
        SELECT d.id, m.id
        FROM departments d, model_catalog m
        WHERE d.code = 'MKT' AND m.code = 'gpt-image-1'
        ON CONFLICT DO NOTHING;

UPDATE alembic_version SET version_num='0006_image_model_catalog' WHERE alembic_version.version_num = '0005_image_gen_audit_actions';

-- Running upgrade 0006_image_model_catalog -> 0007_fix_l1_perms

DELETE FROM role_model_permissions
        WHERE role = 'L1'::role_level
          AND model_id = (
              SELECT id FROM model_catalog WHERE code = 'gemini-2.5-flash-image'
          );

UPDATE alembic_version SET version_num='0007_fix_l1_perms' WHERE alembic_version.version_num = '0006_image_model_catalog';

-- Running upgrade 0007_fix_l1_perms -> 0008_file_scope

ALTER TABLE files
        ADD COLUMN IF NOT EXISTS scope VARCHAR(16) NOT NULL DEFAULT 'personal';

UPDATE alembic_version SET version_num='0008_file_scope' WHERE alembic_version.version_num = '0007_fix_l1_perms';

-- Running upgrade 0008_file_scope -> 0009_api_keys

ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'n8n_triggered';

CREATE TABLE api_keys (
    id UUID DEFAULT uuid_generate_v4() NOT NULL,
    name VARCHAR(255) NOT NULL,
    key_hash VARCHAR(64) NOT NULL,
    service_user_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    last_used_at TIMESTAMP WITH TIME ZONE,
    revoked_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    UNIQUE (key_hash),
    FOREIGN KEY(service_user_id) REFERENCES users (id) ON DELETE CASCADE
);

COMMENT ON COLUMN api_keys.key_hash IS 'SHA-256 hex of the raw secret';

CREATE INDEX ix_api_keys_service_user_id ON api_keys (service_user_id);

UPDATE alembic_version SET version_num='0009_api_keys' WHERE alembic_version.version_num = '0008_file_scope';

-- Running upgrade 0009_api_keys -> 0010_gemini_image_model

INSERT INTO model_catalog
            (code, display_name, provider, is_local,
             cost_per_1k_input_tokens, cost_per_1k_output_tokens,
             max_context_tokens, supports_images, is_active)
        SELECT
            'gemini-3.1-flash-image', 'Gemini 3.1 Flash Image', 'google'::model_provider, FALSE,
            NULL, NULL, NULL, TRUE, TRUE
        WHERE NOT EXISTS (
            SELECT 1 FROM model_catalog WHERE code = 'gemini-3.1-flash-image'
        );

INSERT INTO role_model_permissions (role, model_id)
        SELECT r.role::role_level, m.id
        FROM (VALUES ('L5'), ('L6'), ('ADMIN')) AS r(role)
        CROSS JOIN model_catalog m
        WHERE m.code = 'gemini-3.1-flash-image'
        ON CONFLICT DO NOTHING;

INSERT INTO department_model_permissions (department_id, model_id)
        SELECT d.id, m.id
        FROM departments d, model_catalog m
        WHERE d.code = 'MKT' AND m.code = 'gemini-3.1-flash-image'
        ON CONFLICT DO NOTHING;

UPDATE alembic_version SET version_num='0010_gemini_image_model' WHERE alembic_version.version_num = '0009_api_keys';

-- Running upgrade 0010_gemini_image_model -> 0011_studio_generations

CREATE TABLE IF NOT EXISTS studio_generations (
            id          UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            type        VARCHAR(16)   NOT NULL,
            model_label VARCHAR(100)  NOT NULL,
            prompt_ciphertext BYTEA   NOT NULL,
            prompt_nonce      BYTEA   NOT NULL,
            prompt_tag        BYTEA   NOT NULL,
            key_version INTEGER       NOT NULL DEFAULT 1,
            settings    JSONB,
            status      VARCHAR(16)   NOT NULL DEFAULT 'mocked',
            output_ref  VARCHAR(4000),
            token_cost  INTEGER,
            created_at  TIMESTAMPTZ   NOT NULL DEFAULT now()
        );

CREATE INDEX IF NOT EXISTS ix_studio_generations_user_id
        ON studio_generations (user_id);

UPDATE alembic_version SET version_num='0011_studio_generations' WHERE alembic_version.version_num = '0010_gemini_image_model';

-- Running upgrade 0011_studio_generations -> 0012_studio_output_ref_text

ALTER TABLE studio_generations
            ALTER COLUMN output_ref TYPE TEXT;

UPDATE alembic_version SET version_num='0012_studio_output_ref_text' WHERE alembic_version.version_num = '0011_studio_generations';

-- Running upgrade 0012_studio_output_ref_text -> 0013_veo_video_model

INSERT INTO model_catalog
            (code, display_name, provider, is_local,
             cost_per_1k_input_tokens, cost_per_1k_output_tokens,
             max_context_tokens, supports_images, is_active)
        SELECT
            'veo-2.0-generate-001', 'Veo 2.0', 'google'::model_provider, FALSE,
            NULL, NULL, NULL, FALSE, TRUE
        WHERE NOT EXISTS (
            SELECT 1 FROM model_catalog WHERE code = 'veo-2.0-generate-001'
        );

INSERT INTO role_model_permissions (role, model_id)
        SELECT r.role::role_level, m.id
        FROM (VALUES ('L5'), ('L6'), ('ADMIN')) AS r(role)
        CROSS JOIN model_catalog m
        WHERE m.code = 'veo-2.0-generate-001'
        ON CONFLICT DO NOTHING;

INSERT INTO department_model_permissions (department_id, model_id)
        SELECT d.id, m.id
        FROM departments d, model_catalog m
        WHERE d.code = 'MKT' AND m.code = 'veo-2.0-generate-001'
        ON CONFLICT DO NOTHING;

UPDATE alembic_version SET version_num='0013_veo_video_model' WHERE alembic_version.version_num = '0012_studio_output_ref_text';

-- Running upgrade 0013_veo_video_model -> 0014_studio_audit_actions

ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'studio_image_denied';

ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'studio_generate_requested';

ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'studio_image_generated';

ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'studio_video_denied';

ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'studio_video_generated';

ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'studio_video_failed';

ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'studio_generate_mocked';

UPDATE alembic_version SET version_num='0014_studio_audit_actions' WHERE alembic_version.version_num = '0013_veo_video_model';

-- Running upgrade 0014_studio_audit_actions -> 0015_veo_3_1_video_model

INSERT INTO model_catalog
            (code, display_name, provider, is_local,
             cost_per_1k_input_tokens, cost_per_1k_output_tokens,
             max_context_tokens, supports_images, is_active)
        SELECT
            'veo-3.1-generate-preview', 'Veo 3.1', 'google'::model_provider, FALSE,
            NULL, NULL, NULL, FALSE, TRUE
        WHERE NOT EXISTS (
            SELECT 1 FROM model_catalog WHERE code = 'veo-3.1-generate-preview'
        );

INSERT INTO role_model_permissions (role, model_id)
        SELECT r.role::role_level, m.id
        FROM (VALUES ('L5'), ('L6'), ('ADMIN')) AS r(role)
        CROSS JOIN model_catalog m
        WHERE m.code = 'veo-3.1-generate-preview'
        ON CONFLICT DO NOTHING;

INSERT INTO department_model_permissions (department_id, model_id)
        SELECT d.id, m.id
        FROM departments d, model_catalog m
        WHERE d.code = 'MKT' AND m.code = 'veo-3.1-generate-preview'
        ON CONFLICT DO NOTHING;

UPDATE model_catalog SET is_active = FALSE
        WHERE code = 'veo-2.0-generate-001';

UPDATE alembic_version SET version_num='0015_veo_3_1_video_model' WHERE alembic_version.version_num = '0014_studio_audit_actions';

-- Running upgrade 0015_veo_3_1_video_model -> 0016_lyria_music_model

INSERT INTO model_catalog
            (code, display_name, provider, is_local,
             cost_per_1k_input_tokens, cost_per_1k_output_tokens,
             max_context_tokens, supports_images, is_active)
        SELECT
            'lyria-3-clip-preview', 'Lyria 3 Clip', 'google'::model_provider, FALSE,
            NULL, NULL, NULL, FALSE, TRUE
        WHERE NOT EXISTS (
            SELECT 1 FROM model_catalog WHERE code = 'lyria-3-clip-preview'
        );

INSERT INTO role_model_permissions (role, model_id)
        SELECT r.role::role_level, m.id
        FROM (VALUES ('L5'), ('L6'), ('ADMIN')) AS r(role)
        CROSS JOIN model_catalog m
        WHERE m.code = 'lyria-3-clip-preview'
        ON CONFLICT DO NOTHING;

INSERT INTO department_model_permissions (department_id, model_id)
        SELECT d.id, m.id
        FROM departments d, model_catalog m
        WHERE d.code = 'MKT' AND m.code = 'lyria-3-clip-preview'
        ON CONFLICT DO NOTHING;

UPDATE alembic_version SET version_num='0016_lyria_music_model' WHERE alembic_version.version_num = '0015_veo_3_1_video_model';

-- Running upgrade 0016_lyria_music_model -> 0017_music_audit_actions

ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'studio_music_denied';

ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'studio_music_generated';

ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'studio_music_failed';

UPDATE alembic_version SET version_num='0017_music_audit_actions' WHERE alembic_version.version_num = '0016_lyria_music_model';

-- Running upgrade 0017_music_audit_actions -> 0018_agents

CREATE TABLE IF NOT EXISTS agents (
            id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         UUID          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name            VARCHAR(100)  NOT NULL,
            description     TEXT,
            instructions    TEXT,
            provider        VARCHAR(32)   NOT NULL,
            model           VARCHAR(64)   NOT NULL,
            capabilities    JSONB,
            creativity_level INTEGER      NOT NULL DEFAULT 0,
            visibility      VARCHAR(16)   NOT NULL DEFAULT 'public',
            status          VARCHAR(16)   NOT NULL DEFAULT 'published',
            avatar_color    VARCHAR(16),
            category        VARCHAR(32),
            created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
        );

CREATE INDEX IF NOT EXISTS ix_agents_user_id
        ON agents (user_id);

CREATE INDEX IF NOT EXISTS ix_agents_visibility_status
        ON agents (visibility, status);

CREATE TABLE IF NOT EXISTS agent_files (
            agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
            file_id  UUID NOT NULL REFERENCES files(id)  ON DELETE CASCADE,
            PRIMARY KEY (agent_id, file_id)
        );

CREATE INDEX IF NOT EXISTS ix_agent_files_agent_id
        ON agent_files (agent_id);

ALTER TABLE conversations
        ADD COLUMN IF NOT EXISTS agent_id UUID REFERENCES agents(id) ON DELETE SET NULL;

UPDATE alembic_version SET version_num='0018_agents' WHERE alembic_version.version_num = '0017_music_audit_actions';

-- Running upgrade 0018_agents -> 0019_agent_audit_actions

ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'agent_created';

ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'agent_updated';

ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'agent_deleted';

UPDATE alembic_version SET version_num='0019_agent_audit_actions' WHERE alembic_version.version_num = '0018_agents';

-- Running upgrade 0019_agent_audit_actions -> 0020_truehub_model_catalog

INSERT INTO model_catalog
                (code, display_name, provider, is_local,
                 supports_images, is_active)
            SELECT
                'gpt-5-nano', 'GPT-5 Nano',
                'openai'::model_provider,
                FALSE, FALSE, TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM model_catalog WHERE code = 'gpt-5-nano'
            );

INSERT INTO role_model_permissions (role, model_id)
            SELECT r.role::role_level, m.id
            FROM (VALUES ('L1'), ('L2'), ('L3'), ('L4'), ('L5'), ('L6'), ('ADMIN')) AS r(role)
            CROSS JOIN model_catalog m
            WHERE m.code = 'gpt-5-nano'
            ON CONFLICT DO NOTHING;

INSERT INTO model_catalog
                (code, display_name, provider, is_local,
                 supports_images, is_active)
            SELECT
                'GPT 5.1', 'GPT 5.1',
                'openai'::model_provider,
                FALSE, FALSE, TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM model_catalog WHERE code = 'GPT 5.1'
            );

INSERT INTO role_model_permissions (role, model_id)
            SELECT r.role::role_level, m.id
            FROM (VALUES ('L1'), ('L2'), ('L3'), ('L4'), ('L5'), ('L6'), ('ADMIN')) AS r(role)
            CROSS JOIN model_catalog m
            WHERE m.code = 'GPT 5.1'
            ON CONFLICT DO NOTHING;

INSERT INTO model_catalog
                (code, display_name, provider, is_local,
                 supports_images, is_active)
            SELECT
                '@b2c-production-openai/gpt-5', 'GPT-5 (B2C Production)',
                'openai'::model_provider,
                FALSE, FALSE, TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM model_catalog WHERE code = '@b2c-production-openai/gpt-5'
            );

INSERT INTO role_model_permissions (role, model_id)
            SELECT r.role::role_level, m.id
            FROM (VALUES ('L1'), ('L2'), ('L3'), ('L4'), ('L5'), ('L6'), ('ADMIN')) AS r(role)
            CROSS JOIN model_catalog m
            WHERE m.code = '@b2c-production-openai/gpt-5'
            ON CONFLICT DO NOTHING;

INSERT INTO model_catalog
                (code, display_name, provider, is_local,
                 supports_images, is_active)
            SELECT
                'Gemini 2.5 Pro', 'Gemini 2.5 Pro',
                'google'::model_provider,
                FALSE, FALSE, TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM model_catalog WHERE code = 'Gemini 2.5 Pro'
            );

INSERT INTO role_model_permissions (role, model_id)
            SELECT r.role::role_level, m.id
            FROM (VALUES ('L1'), ('L2'), ('L3'), ('L4'), ('L5'), ('L6'), ('ADMIN')) AS r(role)
            CROSS JOIN model_catalog m
            WHERE m.code = 'Gemini 2.5 Pro'
            ON CONFLICT DO NOTHING;

INSERT INTO model_catalog
                (code, display_name, provider, is_local,
                 supports_images, is_active)
            SELECT
                'Claude Sonnet 4.5', 'Claude Sonnet 4.5',
                'anthropic'::model_provider,
                FALSE, FALSE, TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM model_catalog WHERE code = 'Claude Sonnet 4.5'
            );

INSERT INTO role_model_permissions (role, model_id)
            SELECT r.role::role_level, m.id
            FROM (VALUES ('L1'), ('L2'), ('L3'), ('L4'), ('L5'), ('L6'), ('ADMIN')) AS r(role)
            CROSS JOIN model_catalog m
            WHERE m.code = 'Claude Sonnet 4.5'
            ON CONFLICT DO NOTHING;

INSERT INTO model_catalog
                (code, display_name, provider, is_local,
                 supports_images, is_active)
            SELECT
                'Claude Sonnet 4.6', 'Claude Sonnet 4.6',
                'anthropic'::model_provider,
                FALSE, FALSE, TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM model_catalog WHERE code = 'Claude Sonnet 4.6'
            );

INSERT INTO role_model_permissions (role, model_id)
            SELECT r.role::role_level, m.id
            FROM (VALUES ('L1'), ('L2'), ('L3'), ('L4'), ('L5'), ('L6'), ('ADMIN')) AS r(role)
            CROSS JOIN model_catalog m
            WHERE m.code = 'Claude Sonnet 4.6'
            ON CONFLICT DO NOTHING;

INSERT INTO model_catalog
                (code, display_name, provider, is_local,
                 supports_images, is_active)
            SELECT
                'GPT-Image-1', 'GPT Image 1 (True AI Hub)',
                'openai'::model_provider,
                FALSE, TRUE, TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM model_catalog WHERE code = 'GPT-Image-1'
            );

INSERT INTO role_model_permissions (role, model_id)
            SELECT r.role::role_level, m.id
            FROM (VALUES ('L1'), ('L2'), ('L3'), ('L4'), ('L5'), ('L6'), ('ADMIN')) AS r(role)
            CROSS JOIN model_catalog m
            WHERE m.code = 'GPT-Image-1'
            ON CONFLICT DO NOTHING;

UPDATE alembic_version SET version_num='0020_truehub_model_catalog' WHERE alembic_version.version_num = '0019_agent_audit_actions';

-- Running upgrade 0020_truehub_model_catalog -> 0021_veo_3_1_lite_video_model

INSERT INTO model_catalog
            (code, display_name, provider, is_local,
             cost_per_1k_input_tokens, cost_per_1k_output_tokens,
             max_context_tokens, supports_images, is_active)
        SELECT
            'veo-3.1-lite-generate-preview', 'Veo 3.1 Lite', 'google'::model_provider, FALSE,
            NULL, NULL, NULL, FALSE, TRUE
        WHERE NOT EXISTS (
            SELECT 1 FROM model_catalog WHERE code = 'veo-3.1-lite-generate-preview'
        );

INSERT INTO role_model_permissions (role, model_id)
        SELECT r.role::role_level, m.id
        FROM (VALUES ('L5'), ('L6'), ('ADMIN')) AS r(role)
        CROSS JOIN model_catalog m
        WHERE m.code = 'veo-3.1-lite-generate-preview'
        ON CONFLICT DO NOTHING;

INSERT INTO department_model_permissions (department_id, model_id)
        SELECT d.id, m.id
        FROM departments d, model_catalog m
        WHERE d.code = 'MKT' AND m.code = 'veo-3.1-lite-generate-preview'
        ON CONFLICT DO NOTHING;

UPDATE model_catalog SET is_active = FALSE
        WHERE code = 'veo-3.1-generate-preview';

UPDATE alembic_version SET version_num='0021_veo_3_1_lite_video_model' WHERE alembic_version.version_num = '0020_truehub_model_catalog';

-- Running upgrade 0021_veo_3_1_lite_video_model -> 0022_user_password_auth

ALTER TABLE users
        ADD COLUMN IF NOT EXISTS username VARCHAR(255) UNIQUE,
        ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);

UPDATE alembic_version SET version_num='0022_user_password_auth' WHERE alembic_version.version_num = '0021_veo_3_1_lite_video_model';

-- Running upgrade 0022_user_password_auth -> 0023_login_failed_audit_action

ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'login_failed';

UPDATE alembic_version SET version_num='0023_login_failed_audit_action' WHERE alembic_version.version_num = '0022_user_password_auth';

-- Running upgrade 0023_login_failed_audit_action -> 0024_agents_local_model

UPDATE agents
        SET provider = 'local', model = 'gemma4:26b', updated_at = now();

UPDATE alembic_version SET version_num='0024_agents_local_model' WHERE alembic_version.version_num = '0023_login_failed_audit_action';

-- Running upgrade 0024_agents_local_model -> 0025_hide_truehub_branding

UPDATE model_catalog SET display_name = 'GPT Image 1'
        WHERE code = 'GPT-Image-1' AND display_name = 'GPT Image 1 (True AI Hub)';

UPDATE alembic_version SET version_num='0025_hide_truehub_branding' WHERE alembic_version.version_num = '0024_agents_local_model';

COMMIT;
