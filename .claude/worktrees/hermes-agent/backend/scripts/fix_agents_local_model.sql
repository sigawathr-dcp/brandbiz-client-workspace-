-- One-time fix: force every agent onto the local model.
--
-- Re-applies migration 0024_agents_local_model's UPDATE to correct agents
-- that were seeded or created with non-local providers AFTER 0024 ran.
-- Needed on staging, where 0026_seed_truehub_agents.sql was applied in its
-- pre-fix form (carrying the original True AI Hub export providers) after
-- the 0001_0025 bootstrap had already executed 0024's reset.
--
-- Idempotent: the WHERE clause makes re-runs no-ops.
--
-- Usage:
--   psql "$STAGING_DATABASE_URL" -f backend/scripts/fix_agents_local_model.sql
--   # or locally:
--   docker compose exec -T postgres psql -U brandbiz -d brandbiz < backend/scripts/fix_agents_local_model.sql

UPDATE agents
SET provider = 'local', model = 'gemma4:26b', updated_at = now()
WHERE provider <> 'local' OR model <> 'gemma4:26b';
