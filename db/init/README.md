# Brandbiz AI — Database initialisation

The canonical way to create the Brandbiz database from scratch is via Alembic.
Do **not** run `reference/schema.sql` directly — it is the design-input only.

## First-time setup (fresh host)

```bash
# 1. Copy and fill the env template
cp .env.example .env
# Fill in: POSTGRES_PASSWORD, ENCRYPTION_KEY, JWT_SECRET, Google OAuth creds

# 2. Start only Postgres and wait for it to be healthy
docker compose up -d postgres
docker compose ps   # wait until postgres shows "(healthy)"

# 3. Run all migrations on the blank DB (creates tables + seed data)
docker compose run --rm backend-api alembic upgrade head

# 4. Bring the rest of the stack up
docker compose up -d
```

## Subsequent deployments / schema upgrades

```bash
docker compose run --rm backend-api alembic upgrade head
```

Alembic detects the current revision in `alembic_version` and applies only
the missing migrations.

## Migration chain (as of 2026-06-30)

| Rev | Description |
|-----|-------------|
| 0001_baseline | All tables, enums, indexes, seed data |
| 0002_consent_acknowledged | User consent flag |
| 0004_thai_id_compact | Compact Thai ID regex |
| 0005_image_gen_audit_actions | Image-gen audit enum values |
| 0006_image_model_catalog | Image model catalog entries |
| 0007_remove_l1_image_model_permission | Role permission cleanup |
| 0008_file_scope | File scope column |
| 0009_api_keys | Per-user API key table |
| 0010_gemini_image_model | Gemini image model entry |
| 0011_studio_generations | Studio generations table |
| 0012_studio_output_ref_text | Output reference text column |
| 0013_veo_video_model | Veo video model entry |
| 0014_studio_audit_actions | Studio audit enum values |
| 0015_veo_3_1_video_model | Veo 3.1 model entry |
| 0016_lyria_music_model | Lyria music model entry |
| 0017_music_audit_actions | Music audit enum values |
| 0018_agents | Agents table |
| 0019_agent_audit_actions | Agent audit enum values |
| 0020_truehub_model_catalog | TrueHub model entries |
| 0021_veo_3_1_lite_video_model | Veo 3.1 Lite model entry |

## pgvector dimension

`file_chunks.embedding` is `VECTOR(1024)` — matches **BGE-M3** (`bge-m3:latest`),
which always outputs 1024-dimensional embeddings. Do not change the embedding
model without a migration to alter the column dimension and rebuild the HNSW index.

## Connection details (from docker-compose / .env.example)

| Setting | Value |
|---------|-------|
| Host | `postgres` (internal) / `localhost` (from host via mapped port) |
| Port | 5432 |
| Database | `brandbiz` |
| User | `brandbiz` |
| Password | set in `.env` → `POSTGRES_PASSWORD` |
