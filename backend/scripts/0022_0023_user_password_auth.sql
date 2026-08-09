-- Raw SQL equivalent of Alembic migrations:
--   0022_user_password_auth           (adds users.username, users.password_hash)
--   0023_login_failed_audit_action    (adds 'login_failed' to audit_action enum)
--
-- Use this if you want to apply the change directly via psql instead of
-- `alembic upgrade head`, e.g.:
--   docker compose exec -T postgres psql -U brandbiz -d brandbiz < backend/scripts/0022_0023_user_password_auth.sql
--
-- Both statements are idempotent (IF NOT EXISTS) and safe to re-run.
-- If you run `alembic upgrade head` afterwards, Alembic will see these
-- changes already applied and just record the revision as current —
-- but only if you also stamp it: `alembic stamp 0023_login_failed_audit_action`.

-- 0022_user_password_auth: upgrade()
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS username VARCHAR(255) UNIQUE,
    ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);

-- 0023_login_failed_audit_action: upgrade()
-- Note: ALTER TYPE ... ADD VALUE cannot run inside an explicit transaction
-- block on older Postgres versions (PLAN.md Section 8, Gotcha #5). Keep this
-- as its own statement, not wrapped in BEGIN/COMMIT.
ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'login_failed';
