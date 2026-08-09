# Brandbiz AI

AI chat platform with local LLM by default, gated access to external APIs (Claude, GPT, Gemini, Perplexity), PDPA-compliant encryption, and 4-eyes audit reveal.

## Prerequisites

- Docker + Docker Compose v2
- NVIDIA Container Toolkit (for GPU-accelerated llama.cpp)
- An NVIDIA GPU with ≥16 GB VRAM (RTX 4090 recommended)

## Local dev setup

### 1. Clone and configure

```bash
git clone <repo> brandbiz-ai && cd brandbiz-ai

cp .env.example .env
# Edit .env — mandatory fields:
#   POSTGRES_PASSWORD   — any strong password
#   ENCRYPTION_KEY      — openssl rand -base64 32
#   JWT_SECRET          — openssl rand -hex 32
#   GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET  — from Google Cloud Console
#   GOOGLE_WORKSPACE_DOMAIN  — e.g. company.com (leave blank to allow any Google account)
#   Register authorized redirect URI in Google Cloud Console:
#     https://api.brandbiz.ai/auth/google/callback
```

### 2. Download models

```bash
mkdir -p models
# Qwen 2.5 14B Instruct Q5_K_M (primary chat model, ~10.2 GB)
# Place at: models/qwen2.5-14b-instruct-q5_k_m.gguf
#
# Download from Hugging Face:
#   huggingface-cli download bartowski/Qwen2.5-14B-Instruct-GGUF \
#     Qwen2.5-14B-Instruct-Q5_K_M.gguf \
#     --local-dir models/ \
#     --local-dir-use-symlinks False
#
# BGE-M3 Q8_0 (embedding model, ~1.2 GB — required for Phase 3 RAG)
# Place at: models/bge-m3-q8_0.gguf
#   huggingface-cli download gpustack/bge-m3-GGUF \
#     bge-m3-q8_0.gguf \
#     --local-dir models/ \
#     --local-dir-use-symlinks False
```

> **VRAM budget (RTX 4090, 24 GB):**
> - llamacpp-primary: ~10.2 GB (weights) + ~2.7 GB (KV cache, 32K ctx, Q8) ≈ 13 GB
> - llamacpp-embed: ~1.2 GB (Phase 3 only; runs concurrently)
> - Total peak: ~14.5 GB — keep llamacpp-embed on CPU if headroom is tight

> Model download links are also shared via internal Confluence. Do not upload GGUF files to git.

### 3. Add hosts entries (local HTTPS — Windows)

Run Notepad as admin: `Start-Process notepad C:\Windows\System32\drivers\etc\hosts -Verb RunAs`

Add at the bottom:
```
127.0.0.1  chat.brandbiz.ai admin.brandbiz.ai api.brandbiz.ai
```

### 4. First boot

```bash
# Start storage and infra first
docker compose up -d postgres redis garage

# Run database migrations
docker compose run --rm backend-api alembic upgrade head

# Verify schema (should show 15 tables, partitioned audit_log, vector extension)
docker compose exec postgres psql -U brandbiz brandbiz -c '\dt'
docker compose exec postgres psql -U brandbiz brandbiz -c '\d audit_log'
docker compose exec postgres psql -U brandbiz brandbiz -c 'SELECT extname FROM pg_extension;'

# Seed the first admin user
docker compose run --rm backend-api python -m scripts.bootstrap_admin --email you@company.com

# Bring up all services
docker compose up -d
```

### 5. One-time Garage bucket setup

```bash
# Assign Garage storage node layout (required on first run)
docker compose exec garage garage layout assign -z dc1 -c 1 <node-id>
docker compose exec garage garage layout apply --version 1

# Create bucket and grant access
docker compose exec garage garage bucket create brandbiz-files
docker compose exec garage garage key new my-key
# → Copy the access key + secret key into .env as GARAGE_ACCESS_KEY / GARAGE_SECRET_KEY

docker compose exec garage garage bucket allow \
  --read --write brandbiz-files --key <key-id>
```

### 6. Verify

```bash
# Backend health
curl https://api.brandbiz.ai/health
# → {"status":"ok","db":"ok","redis":"ok"}

# llama.cpp primary (use dev compose to expose port 8080 locally)
curl http://localhost:8080/health
# → {"status":"ok"} when model is fully loaded (may take ~60 s on first start)

# Quick chat completion test
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5","messages":[{"role":"user","content":"Hello"}],"max_tokens":20}'
# → streaming JSON chunks with content

# VRAM check (≤14 GB expected for llamacpp-primary alone)
docker compose exec llamacpp-primary nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits
```

Caddy issues self-signed certs in local mode. Accept the browser warning or install Caddy's local CA:
```bash
caddy trust  # run once on your machine if caddy CLI is installed
```

## Deployment (single VM)

Full procedure for a fresh Ubuntu 22.04 / 24.04 server with an NVIDIA GPU.

### Prerequisites

- Docker Engine + Compose v2: `apt install docker.io` (or the official Docker CE package)
- NVIDIA Container Toolkit: follow the [official install guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- GPU with ≥16 GB VRAM (RTX 4090 or equivalent)
- Domain `*.brandbiz.ai` resolves to the server IP on all client machines (via DNS or hosts file)

### 1. Clone and configure

```bash
git clone <repo> brandbiz-ai && cd brandbiz-ai

cp .env.example .env
# Mandatory fields:
#   POSTGRES_PASSWORD      — any strong random password
#   ENCRYPTION_KEY         — openssl rand -base64 32
#   JWT_SECRET             — openssl rand -hex 32
#   GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET   — from Google Cloud Console
#   GOOGLE_WORKSPACE_DOMAIN — e.g. company.com
#   COOKIE_DOMAIN          — .brandbiz.ai  (leading dot required for subdomain sharing)
#   COOKIE_SECURE          — true (Caddy provides HTTPS)
```

### 2. Download models

```bash
mkdir -p models
huggingface-cli download bartowski/Qwen2.5-14B-Instruct-GGUF \
  Qwen2.5-14B-Instruct-Q5_K_M.gguf \
  --local-dir models/ --local-dir-use-symlinks False

# BGE-M3 only needed for Phase 3 RAG — skip for Phase 1
huggingface-cli download gpustack/bge-m3-GGUF \
  bge-m3-q8_0.gguf \
  --local-dir models/ --local-dir-use-symlinks False
```

### 3. Configure TLS trust

Caddy issues a self-signed cert from its internal CA. Clients need to trust it once:

```bash
# Start Caddy so it generates the CA
docker compose up -d caddy

# Export the root cert
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt

# On each client machine:
#   Linux:   sudo cp caddy-root.crt /usr/local/share/ca-certificates/ && sudo update-ca-certificates
#   macOS:   sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain caddy-root.crt
#   Windows: Import caddy-root.crt into "Trusted Root Certification Authorities"
#
# Or on the server itself (if caddy CLI is installed):
#   caddy trust
```

### 4. First-time database setup

```bash
# Start storage services
docker compose up -d postgres redis

# Run Alembic migration (creates all 15 tables + extensions + seed data)
docker compose run --rm backend-api alembic upgrade head

# Verify schema
docker compose exec postgres psql -U brandbiz brandbiz -c '\dt'
docker compose exec postgres psql -U brandbiz brandbiz -c 'SELECT extname FROM pg_extension;'
```

### 5. One-time Garage S3 bootstrap

Garage requires an explicit cluster layout assignment before it will accept writes.

```bash
docker compose up -d garage

# Get the node ID (shown in startup logs or via status)
docker compose exec garage garage status
# → copy the node ID (a long hex string)

# Assign layout: 1 zone, capacity 1 (single-node cluster)
docker compose exec garage garage layout assign -z dc1 -c 1 <node-id>
docker compose exec garage garage layout apply --version 1

# Create the bucket and access key
docker compose exec garage garage bucket create brandbiz-files
docker compose exec garage garage key new my-key
# → copy the Key ID and Secret Key printed to stdout

# Add the key+secret to .env:
#   GARAGE_ACCESS_KEY=<key-id>
#   GARAGE_SECRET_KEY=<secret-key>

# Grant the key read/write on the bucket
docker compose exec garage garage bucket allow \
  --read --write brandbiz-files --key <key-id>
```

### 6. Bootstrap the first admin user

```bash
docker compose run --rm backend-api \
  python -m scripts.bootstrap_admin --email you@company.com
```

### 7. Bring up all services

```bash
docker compose up -d
```

Watch until all services are healthy:

```bash
docker compose ps
# All services should show "healthy" or "running"
```

### 8. Verify

```bash
# Backend health (both DB and Redis must be "ok")
curl https://api.brandbiz.ai/health
# → {"status":"ok","db":"ok","redis":"ok"}

# llama.cpp ready (wait ~60 s for model load; start_period is 120 s)
curl https://api.brandbiz.ai/health   # backend healthy means llamacpp is healthy (depends_on)

# Browse to chat UI
open https://chat.brandbiz.ai   # accept cert warning until CA is trusted
```

### Updating to a new version

```bash
git pull
docker compose build
docker compose run --rm backend-api alembic upgrade head   # only if migrations changed
docker compose up -d
```

### Useful operations

```bash
# Tail all logs
docker compose logs -f

# Tail a single service
docker compose logs -f backend-api

# Run backend tests
docker compose run --rm backend-api pytest

# Open a psql shell
docker compose exec postgres psql -U brandbiz brandbiz

# Check GPU VRAM usage
docker compose exec llamacpp-primary nvidia-smi

# Restart a single service without downtime to others
docker compose restart backend-api
```

## Architecture

See [PLAN.md](PLAN.md) for the full implementation plan, decisions log, and phase breakdown.

## Development overrides

For hot-reloading and mounted source volumes, use:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

## Useful commands

```bash
# Tail all logs
docker compose logs -f

# Run backend tests
docker compose run --rm backend-api pytest

# Open psql
docker compose exec postgres psql -U brandbiz brandbiz

# Check GPU usage
docker compose exec llamacpp-primary nvidia-smi
```
