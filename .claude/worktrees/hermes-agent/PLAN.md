# Company AI Gateway — Implementation Plan

> Internal AI chat platform for ~100 employees. Local LLM as default, gated access to external APIs (Claude, GPT, Gemini, Perplexity), with PDPA-compliant encryption and 4-eyes audit reveal.

---

## How to use this document with Claude Code

This plan is the source of truth. When asking Claude Code to work on something, reference it by section number, e.g.:

- `"Implement Phase 1, Task 1.3 from PLAN.md"`
- `"Review Section 7 (gotchas) and refactor app/services/policy_engine.py accordingly"`
- `"Generate Alembic migration matching schema.sql"`

The **Decisions Log** (Section 2) records every choice already made — Claude Code should treat these as fixed unless explicitly asked to revisit. The **Out of Scope** list (Section 11) prevents scope creep.

Phases are sequential. Do not start Phase N+1 until Phase N's acceptance criteria pass.

---

## 1. Project Overview

### Goal
Single internal chat UI where all employees converse with a local LLM by default. When the request needs more capability (or a specific model the user is entitled to), the orchestrator routes to an external API — but only if the user's role permits it and the data being sent isn't classified as confidential.

### Why
- **Cost**: Local model is free at inference time. External APIs only fire when justified.
- **Privacy/PDPA**: Confidential data (customer PII) physically cannot reach external providers.
- **Governance**: Every external call has a named user, model, token count, and cost trail.
- **Productivity**: Employees get one tool, not five different AI subscriptions.

### Users
- 100 employees, 6 role tiers (L1–L6) plus ADMIN
- Identity: Google Workspace SSO (existing)
- Peak concurrency: ~15 simultaneous chats
- Languages: Thai + English

### Non-goals
- Replacing existing tools (Slack, Confluence, Notion)
- Customer-facing chatbot
- Self-service model fine-tuning

---

## 2. Decisions Log

Every item here has been deliberated. Do not re-litigate without explicit user request.

| # | Decision | Rationale |
|---|---|---|
| D1 | Backend: Python + FastAPI | LLM ecosystem is Python-first; async is enough for 100 users |
| D2 | Orchestrator: LangGraph state machine | Built for multi-agent routing; explicit nodes match our flow |
| D3 | Frontend: single Next.js app (frontend-chat) with `(admin)` route group | Merged from two apps — admin routes protected by middleware + layout role check |
| D4 | Local LLM: Qwen 2.5 14B Instruct Q5_K_M via llama.cpp | Fits 4090, good Thai support, balanced quality/speed |
| D5 | Embeddings: BGE-M3 (1024 dims) via llama.cpp embedding mode | Multilingual including Thai, established in original architecture |
| D6 | DB: Postgres 16 + pgvector + HNSW index | One DB for relational + vector; pgvector is production-ready |
| D7 | Redis serves two roles: app cache (DB 0) + Celery broker (DB 1) + result backend (DB 2) | Per original architecture; logically separated by DB index |
| D8 | Object storage: Garage (S3-compatible) | Per original architecture; self-hosted, no AWS dependency |
| D9 | Queue: Celery (one image, multiple worker queues) | Mature; matches "decoupled workers scale independently" goal |
| D10 | Reverse proxy: Caddy 2 | Automatic TLS, simpler than nginx for this scale |
| D11 | Auth: Google OAuth + JWT (HS256) | SSO already in place; JWT keeps backend stateless |
| D12 | Encryption: AES-256-GCM at app layer for message content | DB compromise alone cannot leak prompts |
| D13 | Key management: Env var for v1; plan migration to Vault/KMS in Phase 4 | Pragmatic for one engineer; documented upgrade path |
| D14 | Retention: 30 days for `messages.content_*`; metadata kept indefinitely | Balances debug needs vs. PDPA minimization |
| D15 | Reveal flow: 4-eyes (requester ≠ approver); target user notified | Required for `log everything` to be ethically defensible |
| D16 | Tier 3/4 data silently downgrades to local LLM | Better UX than hard rejection; still logged for audit |
| D17 | Role L5+ required for Tier 4 data even on local | Highest-sensitivity data needs senior accountability |
| D18 | Quota: monthly token budget per role; resets first of month | Predictable cost ceiling |
| D19 | Department permissions are additive over role permissions | e.g. Marketing L2 unlocks Gemini Image even though L2 alone wouldn't |
| D20 | Admin panel uses same FastAPI backend but separate router prefix `/admin/*` with `require_admin` dependency | One backend codebase; admin authz enforced at route level |

---

## 3. Architecture Summary

### Layers (top → bottom)

1. **Edge** — Caddy reverse proxy, TLS termination, routes to two upstreams
   - `chat.decomplica.tech` → frontend-chat (Next.js; chat + admin under `/(admin)` route group)
   - `api.decomplica.tech` → backend-api (FastAPI)

2. **Backend API + Agent Orchestrator** — FastAPI app exposing chat, files, admin, reveal endpoints. The orchestrator is a LangGraph state machine inside this process.

3. **Policy & Audit Layer** — Not a separate service; lives as `app/services/policy_engine.py` and async Celery tasks for audit writes.

4. **Processing** — llama.cpp primary (chat) + llama.cpp embed (BGE-M3). Both on GPU.

5. **RAG Workers** — Three Celery queues: `chunking`, `embedding`, `dbwriter`. Plus auxiliary queues: `audit`, `beat` (scheduled jobs).

6. **Storage** — Postgres (relational + pgvector), Redis (cache + queue), Garage (S3 blobs).

7. **External APIs** — Claude, GPT, Gemini, Perplexity. Reached only when policy engine approves.

### Request lifecycle (chat message)

```
User → Caddy → backend-api
            → auth middleware (JWT verify)
            → orchestrator.invoke(message)
                ├─ classifier.detect_tier(message)       # regex + later NER
                ├─ policy_engine.decide(user, tier, model_requested)
                │     ├─ if downgrade → use local
                │     ├─ if deny → raise PermissionError
                │     └─ if allow → continue
                ├─ llm_router.get(decision.model_code).stream(message)
                ├─ encrypt and persist user message + assistant message
                ├─ quota.consume(tokens)         # only for external
                └─ audit.log_async(...)          # Celery enqueue
            → SSE stream back to user
```

---

## 4. Tech Stack (pin these)

| Layer | Tech | Version |
|---|---|---|
| Backend runtime | Python | 3.12 |
| Backend framework | FastAPI | 0.115.x |
| ORM | SQLAlchemy | 2.0.x (async) |
| Migrations | Alembic | 1.13.x |
| Validation | Pydantic | 2.x |
| Orchestration | LangGraph | 0.2.x |
| Queue | Celery | 5.4.x |
| HTTP client | httpx | 0.27.x |
| Crypto | cryptography | 43.x |
| Frontend | Next.js | 15.x (App Router) |
| Frontend AI SDK | Vercel AI SDK | 4.x |
| Database | Postgres + pgvector | 16 + pgvector 0.7+ |
| Cache/Queue | Redis | 7-alpine |
| Object storage | Garage | v1.0.1 |
| LLM serving | llama.cpp server-cuda | latest stable |
| Reverse proxy | Caddy | 2.x |
| Observability | Langfuse (self-hosted, Phase 3) | latest |
| Container | Docker Compose | v2 |

Use `uv` for Python dep management (faster than Poetry, modern). Use `pnpm` for Next.js apps.

---

## 5. Repository Structure

Single mono-repo. One backend image used by all FastAPI + Celery workers.

```
ai-gateway/
├── PLAN.md                          # this file
├── README.md                        # quick start
├── .env.example                     # all required env vars
├── docker-compose.yml               # see /artifacts (already drafted)
├── docker-compose.dev.yml           # local overrides (mount volumes, hot reload)
├── caddy/Caddyfile
├── garage/garage.toml
├── models/                          # GGUF files (gitignored)
│   ├── qwen2.5-14b-instruct-q5_k_m.gguf
│   └── bge-m3-q8_0.gguf
│
├── db/
│   └── init/                        # baseline schema (dev convenience only)
│       └── 01_schema.sql            # copy from /artifacts/schema.sql
│
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── crypto.py
│   │   ├── deps.py                  # FastAPI dependencies (current_user, db_session, etc.)
│   │   ├── routers/
│   │   │   ├── auth.py
│   │   │   ├── chat.py              # SSE streaming
│   │   │   ├── conversations.py
│   │   │   ├── files.py
│   │   │   ├── admin.py
│   │   │   └── reveal.py
│   │   ├── models/                  # SQLAlchemy ORM
│   │   ├── schemas/                 # Pydantic DTOs
│   │   ├── agents/
│   │   │   ├── orchestrator.py      # LangGraph state machine
│   │   │   ├── nodes.py             # individual node functions
│   │   │   └── prompts.py
│   │   ├── services/
│   │   │   ├── policy_engine.py     # copy from /artifacts/policy_engine.py
│   │   │   ├── classifier.py
│   │   │   ├── quota.py
│   │   │   ├── audit.py
│   │   │   └── reveal.py
│   │   ├── llm/
│   │   │   ├── base.py              # abstract LLMClient
│   │   │   ├── llamacpp.py
│   │   │   ├── anthropic.py
│   │   │   ├── openai.py
│   │   │   ├── google.py
│   │   │   ├── perplexity.py
│   │   │   └── router.py
│   │   ├── tools/                   # tool registry for orchestrator
│   │   └── workers/
│   │       ├── celery_app.py
│   │       ├── chunking.py
│   │       ├── embedding.py
│   │       ├── dbwriter.py
│   │       ├── audit_writer.py
│   │       └── retention.py
│   └── tests/
│       ├── unit/
│       └── integration/
│
├── frontend-chat/                   # Next.js 15 (App Router)
│   ├── package.json
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx                 # redirect to /chat
│   │   ├── login/page.tsx
│   │   ├── chat/[id]/page.tsx
│   │   └── api/auth/[...nextauth]/route.ts
│   ├── components/
│   │   ├── ChatPane.tsx
│   │   ├── ModelPicker.tsx
│   │   ├── TierBadge.tsx
│   │   └── QuotaMeter.tsx
│   └── lib/
│       └── api.ts                   # backend-api fetch wrapper
│
```

---

## 6. Phase Breakdown

Each task lists: scope, files touched, acceptance criteria. Tick the box when done. Claude Code should work one task at a time, run tests, then move on.

### Phase 1 — Foundation (Weeks 1–8)

Goal: A logged-in user can chat with the local LLM. Messages persist encrypted. Nothing external yet.

#### Task 1.1 — Repo scaffold ☑
- Create directory structure from Section 5
- `.env.example` with every variable referenced in `docker-compose.yml`
- `README.md` with "Local dev setup" steps
- Add `.gitignore` (models/, .env, __pycache__, node_modules, .next, etc.)

**Accept:** `tree -L 3 -I 'node_modules|.next|.venv'` matches Section 5

#### Task 1.2 — Postgres + Alembic ☑
- `pgvector/pgvector:pg16` running via compose
- Convert `/artifacts/schema.sql` into Alembic baseline migration `0001_baseline.py`
- Add `alembic upgrade head` to backend container's startup or document it as separate step
- All ENUM types, tables, indexes from schema.sql present after `upgrade head`

**Accept:** `psql -c '\dt+'` shows all 13 tables. `\d audit_log` shows partitioning. `pgvector` extension installed.

#### Task 1.3 — Backend skeleton ☑
- FastAPI app boots on `:8000`
- `/health` returns `{"status":"ok", "db":"ok", "redis":"ok"}`
- Async SQLAlchemy session dependency works
- Pydantic Settings loads from env

**Accept:** `curl localhost:8000/health` returns 200 with all subsystems "ok"

#### Task 1.4 — Crypto module ☑
- `app/crypto.py` with `encrypt(plaintext: str) -> tuple[bytes, bytes, bytes, int]` returning `(ciphertext, nonce, tag, key_version)`
- `decrypt(ct, nonce, tag, key_version) -> str`
- Uses AES-256-GCM via `cryptography.hazmat.primitives.ciphertext.aead.AESGCM`
- Key read from `ENCRYPTION_KEY` env (base64-encoded 32 bytes)
- Supports key versioning (env can hold multiple keys keyed by version)

**Accept:** Round-trip unit test passes. Tampered ciphertext raises `InvalidTag`. Different nonces produce different ciphertexts.

#### Task 1.5 — Google OAuth login ☑
- `/auth/google/login` redirects to Google consent
- `/auth/google/callback` exchanges code, verifies `hd` claim matches `GOOGLE_WORKSPACE_DOMAIN`
- Creates/updates `users` row, issues JWT (HS256, 8-hour expiry)
- Frontend stores JWT in httpOnly cookie

**Accept:** Logging in with a `@company.com` account creates a `users` row with `role=L1` (default) and returns a valid JWT. Non-domain accounts get 403.

#### Task 1.6 — Auth middleware + current_user dependency ☑
- `app/deps.py: get_current_user()` — verifies JWT, loads user with departments, returns `User` ORM object
- `require_admin()` — depends on `get_current_user`, raises 403 if `role != ADMIN`
- All routes except `/health`, `/auth/*` require auth

**Accept:** `curl /chat` without token returns 401. With valid token returns 200.

#### Task 1.7 — llama.cpp container running ☑
- Download Qwen 2.5 14B Q5_K_M GGUF to `./models/`
- `llamacpp-primary` container serves on `:8080` with continuous batching
- Backend can hit `http://llamacpp-primary:8080/v1/chat/completions` (OpenAI-compatible API)
- VRAM usage ≤ 14GB

**Accept:** `curl http://llamacpp-primary:8080/v1/chat/completions -d '...'` returns a completion. `nvidia-smi` confirms VRAM use.

#### Task 1.8 — LLMClient interface + llama.cpp adapter ☑
- `app/llm/base.py` defines abstract async streaming interface: `async def stream_chat(messages, **opts) -> AsyncIterator[ChatChunk]`
- `app/llm/llamacpp.py` implements it via httpx async SSE
- `app/llm/router.py` returns the right client for a model code

**Accept:** Unit test against running llama.cpp returns at least one chunk with content.

#### Task 1.9 — Minimal orchestrator ☑
- LangGraph with two nodes: `load_history` → `call_llm`
- Persists user message + assistant message via encrypted insert
- Returns SSE stream

**Accept:** `POST /chat` with `{"conversation_id": null, "content": "hello"}` returns a stream and creates two rows in `messages`. Decrypting them via crypto module yields the plaintext.

#### Task 1.10 — Chat frontend (minimum) ☑
- Next.js app with Google login button → backend OAuth flow
- After login: simple chat page with message input + streaming display
- Uses Vercel AI SDK's `useChat` against `/chat`
- Conversation list sidebar

**Accept:** Full loop: login → send message → see streamed response → reload page → message still there.

#### Task 1.11 — Deployment ☑
- Caddy config for `chat.decomplica.tech` and `api.decomplica.tech`
- Single-VM deploy with `docker compose up -d`
- Document procedure in `README.md`

**Accept:** Five test users can use the chat from their browsers concurrently. No crashes for 24 hours.

### Phase 1 acceptance gate
- 10 employees use it for a week
- Zero plaintext-message database leaks (verify with `SELECT content_ciphertext FROM messages LIMIT 1` — must look like random bytes)
- llama.cpp p95 latency under 5s for short prompts
- No external API code paths exist yet (run `grep -r 'anthropic\|openai' backend/app/llm/` should return only stubs)

---

### Phase 2 — Permission Layer + External APIs (Weeks 9–16)

Goal: External APIs work, gated by role + tier + quota. Audit log captures everything. Admin panel functional.

#### Task 2.1 — Data classifier ☑
- `app/services/classifier.py: detect_tier(text) -> DataTier`
- Loads patterns from `data_classification_rules` table
- Returns highest tier among matching patterns
- Caches compiled regex in-process

**Accept:** Unit tests: `"My ID is 1-2345-67890-12-3"` → TIER_3. `"Hello"` → TIER_1. `"Project Apollo M&A target list"` should be added as keyword rule and detected as TIER_4.

#### Task 2.2 — Policy engine integration ☑
- Drop `/artifacts/policy_engine.py` into `app/services/`
- Wire into orchestrator before LLM call
- On `downgrade_to_local`: surface a non-blocking UI hint ("Using local model because your message contains sensitive data")
- On `deny`: return 403 with reason code

**Accept:** Unit + integration tests cover every branch of `PolicyEngine.decide`. Sending a Thai national ID with `model=claude-sonnet-4` returns the response but the audit log shows `tier_blocked` and `model_used=qwen2.5-14b-local`.

#### Task 2.3 — Quota service ☑
- `app/services/quota.py: consume(user, tokens, cost)`
- Atomic increment via `UPDATE ... RETURNING`
- Pre-check in policy engine (already present in artifact)

**Accept:** Two concurrent requests consuming quota don't double-spend (verify via stress test with `pytest-asyncio` + multiple sessions).

#### Task 2.4 — Audit logger (async) ☑
- `app/services/audit.py: log(action, user, details)` enqueues to Celery `audit` queue
- `app/workers/audit_writer.py` consumes and inserts into `audit_log`
- IP and user agent captured at request middleware, threaded through

**Accept:** Sending 100 chat messages produces ≥ 100 rows in `audit_log` (one `message_sent`, one `message_received` per turn). Async, so chat latency must not be impacted (compare p50 before/after).

#### Task 2.5 — External LLM adapters ☑
Implement one at a time, each its own task:

- **2.5a** — Claude via `anthropic` SDK (`app/llm/anthropic.py`) ☑
- **2.5b** — GPT via `openai` SDK (`app/llm/openai.py`) ☑
- **2.5c** — Gemini via `google-genai` SDK (`app/llm/google.py`) ☑
- **2.5d** — Perplexity via httpx (OpenAI-compatible) (`app/llm/perplexity.py`) ☑

Each must support streaming, return token counts in final chunk, and surface errors as `LLMProviderError` for orchestrator to handle.

**Accept:** With a test user upgraded to L6, manually sending a message with `model=claude-sonnet-4` returns streamed Claude output. Quota row increments by `tokens_input + tokens_output`. Audit log shows `model_used=claude-sonnet-4` and `cost_usd > 0`.

#### Task 2.6 — Reveal request flow ☑
- `POST /reveal` — create request with target_message_id + reason
- `POST /reveal/{id}/approve` — different user, sets approver_id, status=approved, expires_at=now+24h
- `GET /reveal/{id}/view` — only requester, only if status=approved and not expired, decrypts message, sets viewed_at, enqueues notify-target audit task
- All four steps generate audit entries

**Accept:** Self-approve attempt returns 400 (DB constraint `no_self_approve`). Approved request can be viewed once; second view either works (idempotent) or returns 410 — pick one and document.

#### Task 2.7 — Admin panel: users + permissions ☑
- `/admin/users` — list, search, change role
- `/admin/permissions/role` — toggle role×model matrix
- `/admin/permissions/department` — toggle department×model add-ons
- Every mutation produces an `admin_*` audit entry

**Accept:** Demoting a user from L4 to L1 immediately blocks their access to Claude on next request (no caching staleness > 30s).

#### Task 2.8 — Admin panel: dashboard + audit + reveal queue ☑
- Dashboard with metric cards (active users, total messages, external cost, PII blocks, pending reveals)
- Model usage breakdown
- Top users by cost
- Pending reveal cards with approve/deny
- Searchable audit log with CSV export

**Accept:** All numbers on dashboard match SQL queries against the DB. Approve action from dashboard transitions the reveal request and creates the audit trail.

#### Task 2.9 — Privacy notice + first-login flow ☑
- On first login, modal shows: what is logged, 30-day retention, encryption + 4-eyes access, link to full policy
- User must click "I understand" — recorded in audit log
- Block chat usage until acknowledged

**Accept:** New user can't send a message until they acknowledge. Returning users skip the modal. Audit log has one `consent_acknowledged` row per user.

#### Task 2.10 — External automation integration (n8n) ☑

Two-direction connection between this gateway and an n8n Gmail-labelling workflow.

**Part 0 — Service-account API-key auth (foundation)**
- `app/models/api_key.py` — `api_keys` table; SHA-256 keyed, `gw_` prefix
- `alembic/versions/0009_api_keys.py` — migration + `n8n_triggered` audit action
- `app/deps.py` — `get_api_principal()`, `get_principal()` (accepts JWT or API key)
- `app/routers/admin.py` — `POST /admin/api-keys`, `GET /admin/api-keys`, `DELETE /admin/api-keys/{id}`
- `scripts/create_service_account.py` — bootstrap CLI (mint user + key, print once)

**Part A — n8n → Gateway: OpenAI-compatible passthrough**
- `app/routers/openai_compat.py` — `POST /v1/chat/completions`, `GET /v1/models`
- `app/llm/openai.py` + `app/llm/llamacpp.py` — `raw_chat()` and `raw_streaming_chat()` methods for tool-calling passthrough
- `app/config.py` + `.env.example` — `N8N_WEBHOOK_URL`, `N8N_WEBHOOK_SECRET`
- Every call governed by `PolicyEngine.decide()`, classified, audited, quota-charged

**Part B — Gateway → n8n: outbound webhook trigger**
- `app/services/n8n_client.py` — httpx client firing the n8n webhook
- `app/routers/automations.py` — `POST /automations/n8n/label-inbox`

**n8n workflow changes needed** (manual, in the n8n UI):
1. OpenAI Chat Model node → set Base URL: `https://api.decomplica.tech/v1`, API Key: `gw_…`
2. Add a parallel Webhook trigger node (POST) → run same Gmail labelling agent
3. Set `X-N8N-Secret` header validation on the webhook node; set the same value in `N8N_WEBHOOK_SECRET`

**Accept:**
- `curl -H "Authorization: Bearer gw_…" /v1/models` returns allowed model list → 200
- `POST /v1/chat/completions` with `tools: [...]` returns a response with `tool_calls` intact; audit log shows `message_sent`/`message_received` with `source: "n8n"`
- A payload containing a Thai national ID → `tier_blocked` in audit, `model_used=gemma4:26b` (downgrade to local)
- `POST /automations/n8n/label-inbox` fires the n8n webhook and writes `n8n_triggered` audit row
- Bad API key → 401; revoked key → 401 (immediate, no TTL delay)

### Phase 2 acceptance gate
- All 100 employees onboarded
- One full billing cycle (≥ 30 days) of external API usage tracked against quotas with < 5% variance vs. provider invoice
- At least one reveal request approved and viewed end-to-end in production
- Zero successful external API calls with Tier 3+ data (verify in audit log)

---

### Phase 3 — RAG, Files, Advanced (Weeks 17–26)

Goal: Upload documents, ask questions over them. Image generation for Marketing. Code execution for engineering.

#### Task 3.1 — Garage S3 + file upload ☑
- ~~Garage container configured with a bucket + access keys~~ (demo: local disk volume)
- `POST /files` accepts multipart upload, stores in local volume, creates `files` row
- File-tier classification at upload time

**Demo-mode deviation:** Blobs stored in `FILE_STORAGE_DIR` (`files.s3_key` = relative path). No Celery/Redis — ingestion runs via FastAPI `BackgroundTasks`.

**Accept:** Uploading a 5MB PDF works, file appears on disk, row in DB has correct `sha256_hash` and `detected_tier`.

#### Task 3.2 — RAG chunking worker ☑
- File upload enqueues `BackgroundTasks.add_task(process_file, file_id)` (demo: no Celery)
- Worker extracts text, splits into ~500-token chunks with 50-token overlap
- Writes chunks (with embeddings, see 3.3) to `file_chunks`

**Accept:** 20-page PDF produces ~40 chunks in DB. Chunking is idempotent (re-running same file_id deletes existing chunks first).

#### Task 3.3 — RAG embedding worker ☑
- `llm_embed_url` points at Ollama host running `bge-m3` (1024 dims, honors D5)
- `app/llm/embeddings.py` `EmbeddingClient` calls `/v1/embeddings` OpenAI-compat endpoint
- Batches of 32 chunks embedded per request

**Accept:** Embed endpoint returns 1024-dim vector for Thai + English. Chunks embedded inline in `process_file`.

#### Task 3.4 — RAG dbwriter worker ☑
- Vectors written by `process_file` in `app/services/ingestion.py`
- Marks `files.is_processed = TRUE` when all chunks done

**Accept:** End-to-end: upload PDF → `is_processed=True` → file_chunks all have non-null embedding. HNSW index works (`EXPLAIN ANALYZE` shows index scan).

#### Task 3.5 — RAG query tool ☑
- `app/tools/rag_search.py` — embeds query, runs pgvector cosine search `ORDER BY embedding <=> $1 LIMIT top_k`
- Context injected as system message in `call_llm`; citations emitted as SSE `sources` event
- Retrieval happens in `prepare_chat` (before tier classification, per R3)

**Accept:** Asking a question whose answer is in an uploaded PDF returns a response that quotes/references the PDF.

#### Task 3.6 — Image generation route ☑
- Gemini Image adapter accepts text prompt, returns image bytes
- Stores image in Garage, returns signed URL
- Marketing dept users only (department permission)

**Accept:** Marketing user generates an image and sees it inline in chat. Non-Marketing L4 user gets 403 with clear reason.

#### Task 3.7 — Multi-instance llama.cpp + load balancer ☐
- Run 2-3 llamacpp-primary instances on different ports
- Caddy or HAProxy round-robin between them
- Health check removes failed instances

**Accept:** Killing one instance doesn't break chat for users. Latency under load improves measurably (run a 30-user concurrent test).

#### Task 3.8 — Code sandbox (optional) ☐
- E2B or self-hosted Docker-based sandbox
- Tool exposed only to L4+ engineering users
- Strict resource limits, network isolation

**Accept:** Sandboxed code can't reach internal network. Resource limits enforced. Outputs returned to chat.

#### Task 3.9 — True Studio (generative-media studio) ☑

Three-tab creative studio (Image / Video / Music) with a split-pane UI: left-side generation form, right-side My Studio history + Templates gallery.

**Scope:**
- Image generation is real via the existing Gemini pipeline (routes through `PolicyEngine.decide()` — §7.2). Marketing dept (MKT) and roles L5/L6/ADMIN only.
- Video (Seedance 1.5 Pro) and Music (Lyria 3 Pro Preview) are mocked placeholders — no external provider, no queue, no Celery/Redis (D9 / Section 11 honoured).
- Prompts are AES-256-GCM encrypted before DB insert (§7.1 — never store plaintext).
- All actions audited via `app/services/audit.py`.

**Files touched:**
- `backend/app/models/studio.py` — `StudioGeneration` ORM model
- `backend/app/models/__init__.py` — register model
- `backend/alembic/versions/0011_studio_generations.py` — idempotent migration
- `backend/app/services/studio.py` — `generate()`, `list_generations()`, `list_templates(type)`
- `backend/app/routers/studio.py` — `POST /studio/generate`, `GET /studio/generations`, `GET /studio/templates`
- `backend/app/main.py` — register studio router
- `backend/tests/unit/test_studio.py` — policy gate, mock branches, ciphertext check
- `frontend-chat/app/studio/layout.tsx` — server layout (auth + ConsentGate + NavSidebar)
- `frontend-chat/app/studio/page.tsx` — page entry point
- `frontend-chat/components/studio/StudioPage.tsx` — full client component (tabs, form, results panel)
- `frontend-chat/app/api/studio/generate/route.ts`
- `frontend-chat/app/api/studio/generations/route.ts`
- `frontend-chat/app/api/studio/templates/route.ts`
- `frontend-chat/components/NavSidebar.tsx` — add True Studio nav item

**Accept:**
- `/studio` page loads with three mode tabs (Image / Video / Music).
- Marketing L2 or L5+ user: Image → Generate → result appears in My Studio panel.
- L1–L4 without MKT: Image → Generate → 403 with clear denial message.
- Video / Music → Generate → row created with `status=mocked`; no external call made.
- `SELECT prompt_ciphertext FROM studio_generations` returns binary, not readable text.
- Templates tab shows seeded grid (6 image, 6 video, 6 music templates).
- All actions produce `audit_log` rows.

#### Task 3.10 — Obsidian vault RAG ingestion (read-only) ☑

One shared team Obsidian vault (a git repo) is synced read-only into the
existing RAG corpus, reusing the upload→classify→`process_file` pipeline
from Tasks 3.1–3.5 wholesale. No Celery/Redis (D9 / Section 11 honoured) —
sync runs via a standalone script invoked by host cron.

**Scope:**
- Every vault note is ingested as a `files` row owned by a dedicated
  `obsidian-bot` service-account user, `scope="org"` (searchable by all
  employees) — no per-user/personal vaults, no departmental scoping.
- Note identity is `(source="obsidian", source_path=<vault-relative path>)`;
  re-sync upserts by that key instead of duplicating rows.
- Full-tree reconcile every run: unchanged (sha + `is_processed` match) →
  skip; new/changed → (re)classify → ingest; missing from tree → hard-delete
  (handles renames as delete-old + add-new).
- Notes classified Tier 3+ (confidential) are quarantined — never ingested
  into the org-wide corpus; audited for admin review.
- Markdown is ingested raw — no wikilink/frontmatter/comment preprocessing.
- File types: everything `extract_text` supports (`.md/.txt/.csv/.pdf/.docx`);
  `.obsidian/`, `.trash/`, and the templates dir are excluded.

**Files touched:**
- `backend/alembic/versions/0027_obsidian_source_columns.py` — `files.source`
  + `files.source_path`, partial index, 4 new `audit_action` values
- `backend/app/models/file.py` — `source` / `source_path` columns
- `backend/app/models/audit.py` — `vault_note_ingested/updated/deleted/quarantined`
- `backend/app/services/vault_sync.py` — reconcile service (`sync_vault()`)
- `backend/scripts/sync_vault.py` — standalone cron entrypoint (git pull → reconcile)
- `backend/app/config.py`, `.env.example`, `docker-compose.yml`, `backend/Dockerfile`
  (git binary) — `VAULT_*` settings + `vault_data` volume
- `backend/tests/unit/test_vault_sync.py`, `backend/tests/integration/conftest.py`

**Accept:**
- `alembic upgrade head` adds `files.source`/`source_path` and the 4 audit values.
- `python -m scripts.sync_vault` against a test vault ingests normal notes
  (`scope=org`, `source=obsidian`), quarantines a Tier-3 note (no `files` row
  created), and skips excluded dirs (`.obsidian/`, `.trash/`, `templates/`).
- Deleting a note from the vault and re-running sync removes its `files` row
  and chunks; editing a note re-embeds under the same `file_id`.
- A chat question answerable only by a synced note returns a response citing
  it (SSE `sources` event) — proves the org corpus is reachable from chat
  with zero changes to `app/tools/rag_search.py`.
- `pytest backend/tests/unit/test_vault_sync.py` green.

#### Task 3.11 — Hermes Agent integration (external governed agent provider) ☑

Wires NousResearch's Hermes Agent (self-hosted, autonomous agent with tools/memory/skills) into the gateway as a new external model, using its built-in OpenAI-compatible API server. Same pattern as Task 2.5's external adapters — no orchestrator or policy-engine changes needed; governance, audit, and quota apply automatically once registered.

**Scope:**
- Gateway-side client + wiring, **plus Hermes itself** (revised 2026-07-14 — originally scoped as
  deployed separately/out of repo; switched to running Hermes as a `hermes` service in
  `docker-compose.yml`, using the official `nousresearch/hermes-agent` image. A one-shot
  `hermes-init` service pre-populates `config.yaml`/`.env` into a named volume on first boot only
  (non-interactive, no `hermes setup` wizard needed), pointed at an existing Ollama host via
  `HERMES_OLLAMA_URL`/`HERMES_OLLAMA_MODEL`. `docker compose up` now installs and starts Hermes
  automatically. `backend-api` reaches it at `http://hermes:8642/v1` over the compose network.
- `is_local=false`, so Tier 3/4 messages auto-downgrade to the local model before ever reaching Hermes (D16/D17).
- Access defaults to L5/L6/ADMIN only (not all roles, unlike most Task 2.5 adapters) — Hermes autonomously runs tools/terminal/web per request, higher blast radius than a plain chat model.

**Files touched:**
- `backend/app/llm/hermes.py` — `HermesClient`, OpenAI-compatible httpx streaming client (modeled on `perplexity.py`)
- `backend/app/llm/router.py` — `HERMES_MODEL_CODE`, conditional registration on `hermes_api_key`
- `backend/app/config.py` + `.env.example` — `HERMES_API_KEY`, `HERMES_API_URL`
- `backend/app/models/model_catalog.py` — `"hermes"` added to `model_provider` enum
- `backend/alembic/versions/0029_hermes_provider_enum.py` — enum value (own migration + explicit `COMMIT`; see Gotcha #5)
- `backend/alembic/versions/0030_hermes_model_catalog.py` — catalog row + L5/L6/ADMIN role permissions
- `frontend-chat/lib/domain.ts` — `MODEL_BY_CODE['hermes-agent']` picker entry with expectation-setting blurb
- `backend/tests/unit/test_hermes_llm.py` — streaming, base-URL config, auth header, error mapping

**Accept:**
- Unit tests pass; migration chain (`alembic upgrade head` / `downgrade -2`) verified clean against a scratch DB — done, verified 2026-07-13.
- `GET /models/available` as L5+ lists `hermes-agent`; L1–L4 does not see it — done, verified live 2026-07-14 (ADMIN sees `hermes-agent`; `l1.associate` does not).
- Chat via Hermes streams tokens, shows tier/model badge, produces an `audit_log` row, decrements quota — done, verified live 2026-07-14 (`message_sent`/`message_received` audit rows with correct `model_used`/token counts; `quotas.tokens_used` incremented).
- Blank `HERMES_API_KEY` → model not registered, not offered — unit-tested only (not re-checked against the live instance, which now has a key configured; re-verifying would mean temporarily unregistering Hermes).

#### Task 3.12 — Cowork-style background tasks (Hermes) ☑

"Claude Cowork"-style capability: assign Hermes Agent an outcome, close the tab, come back later
to a finished, reviewable result. Extends Task 3.11 — Hermes is already a registered governed
model; this adds a *detached* execution mode (`BackgroundTasks`, not the live SSE chat stream) so
a run outlives the HTTP connection, plus a poll-based Tasks page to submit and review jobs.

**Scope (Phase 1 / MVP only — confirmed with user):**
- Submit a task → runs unattended via Hermes → poll → review result. Fully governed: routes
  through the same `prepare_chat()` → `PolicyEngine.decide()` gate as `/chat` and
  `/automations/agent`; Tier 3/4 prompts silently downgrade to the local model (Hermes never
  sees them); quota charged automatically for non-local models.
- **Explicitly NOT built in Phase 1** (documented follow-ons, schema leaves room via nullable
  columns / a reserved status value, no code shipped): Phase 2 = scheduling/recurring (host-cron
  script + cadence picker, same pattern as `scripts/sync_vault.py`); Phase 3 = pre-run approval
  gate (RevealQueue-style "awaiting_approval" status). Hermes runs its tools autonomously on its
  own host — the gateway can gate *whether a task starts*, not pause it mid-tool-call.
- No Celery/Redis (D9) — `BackgroundTasks` in the API worker process, same pattern as AI Studio's
  video/music generation jobs. Known limitation: an API container restart loses in-flight tasks
  (stuck `running`); documented, not fixed in Phase 1.

**Files touched:**
- NEW `backend/app/models/agent_task.py` — `AgentTask` (encrypted prompt/result, VARCHAR status
  + frozenset, mirrors `StudioGeneration`/`VaultSyncRun`)
- NEW `backend/alembic/versions/0031_agent_task_audit_actions.py` — 5 new `audit_action` values
- NEW `backend/alembic/versions/0032_agent_task.py` — `agent_task` table + indexes
- `backend/app/models/audit.py` — new action strings added to the ORM enum tuple
- NEW `backend/app/services/agent_tasks.py` — `submit_task` (governance gate + enqueue),
  `_run_task` (background worker: runs `run_chat_collect`, updates status, never raises),
  `list_tasks`/`get_task`/`cancel_task` (best-effort — flips the row, can't interrupt an
  in-flight run)
- NEW `backend/app/routers/tasks.py` — `POST /tasks` (202), `GET /tasks`, `GET /tasks/{id}`,
  `POST /tasks/{id}/cancel`; registered in `app/main.py`
- `backend/app/llm/hermes.py` + `router.py` + `config.py` + `.env.example` — configurable
  `hermes_api_timeout` (default 600s, up from the hardcoded 120s) since an unattended tool loop
  runs far longer than interactive chat
- NEW `backend/tests/unit/test_agent_tasks.py` — submit guard rails (403 deny, 503 unconfigured),
  submit success + downgrade recording, `_run_task` success/failure paths
- `backend/tests/unit/test_hermes_llm.py` — 2 new tests for the configurable timeout
- NEW `frontend-chat/app/tasks/layout.tsx` + `page.tsx` — role-gated (L5+/ADMIN, mirrors Hermes's
  own catalog permissions) page shell, modeled on `app/studio/layout.tsx`
- NEW `frontend-chat/components/tasks/TasksPage.tsx` — submit form + poll-driven task list +
  detail modal, modeled on `components/studio/StudioPage.tsx`'s poll pattern and
  `components/admin/RevealQueue.tsx`'s status-badge convention
- NEW `frontend-chat/app/api/tasks/route.ts`, `[id]/route.ts`, `[id]/cancel/route.ts` — proxy
  routes mirroring `app/api/studio/**`
- `frontend-chat/components/NavSidebar.tsx` + `lib/domain.ts` — `canUseTasks()` role gate,
  `TASK_STATUS` label/tone map, "Tasks" nav entry

**Follow-on (2026-07-14) — live activity log + output:** the detail view originally showed only
the terminal result. Added a streaming collect path so the Tasks page shows Hermes's live
activity log and partial output while a task is still running, not just the finished result.
Honest constraint: richness of the log depends on what Hermes's OpenAI-compatible stream emits
(content deltas + a few status markers today, not per-tool-call structure) — documented, not
oversold. New/changed files:
- `backend/app/agents/orchestrator.py` — NEW `run_chat_collect_streamed()`: same graph-driving
  queue-drain pattern as `run_chat_stream`, but calls an `on_event(dict)` callback per queue item
  instead of yielding SSE lines; returns the same shape as `run_chat_collect`.
- `backend/app/models/agent_task.py` — NEW `progress_ciphertext/nonce/tag/progress_key_version`
  columns (encrypted quad, same pattern as prompt/result); cleared on terminal status.
- NEW `backend/alembic/versions/0033_agent_task_progress.py` — adds the 4 progress columns
  (nullable, no COMMIT needed).
- `backend/app/services/agent_tasks.py` — `_run_task` now drives `run_chat_collect_streamed` with
  an `on_event` callback that accumulates a log + partial answer and throttled-flushes an
  encrypted snapshot (`_flush_progress`, ≤1 write / 2s) to `progress_*`; cleared on the terminal
  update. NEW `decrypt_progress()`.
- `backend/app/routers/tasks.py` — `TaskDetail.progress: str | None`; `TaskSummary.has_progress:
  bool` (cheap presence flag, no decrypt, for the list view's "Hermes is working…" hint).
- NEW `frontend-chat/components/ui/Markdown.tsx` — `MarkdownContent` extracted out of
  `ChatPane.tsx` so both chat and the Tasks detail page share one renderer (no duplication).
- NEW `frontend-chat/app/tasks/[id]/page.tsx` + `components/tasks/TaskDetailView.tsx` — dedicated
  detail page (promoted from the inline modal) with a monospace auto-scrolling activity-log
  console (live while running, collapsible once done), rendered-markdown output, Copy/Re-run.
- `frontend-chat/components/tasks/TasksPage.tsx` — cards route to `/tasks/{id}` instead of
  opening a modal; running cards show a "Hermes is working…" hint via `has_progress`.
- `backend/tests/unit/test_orchestrator.py` — 3 new tests for `run_chat_collect_streamed`
  (per-event callback + final result, works without a callback, raises on error-with-no-output).
- `backend/tests/unit/test_agent_tasks.py` — 1 new test: progress flushes during a run and is
  cleared on the terminal update.

**Accept:**
- Unit tests pass (6 `test_agent_tasks.py` + 2 timeout + 3 streamed-collect + 1 progress-flush =
  12 new tests total across the two follow-ons) — done, verified 2026-07-14.
- Migration chain (0001→0033, `upgrade head` / `downgrade -1` / re-`upgrade head`) verified clean
  against a scratch DB — done, verified 2026-07-14.
- `tsc --noEmit` and `next build` pass with the new routes registered — done, verified
  2026-07-14.
- Submit a task as L5+ → 202 → poll shows `queued`→`running`→`succeeded` with a decrypted result,
  new `audit_log` rows, quota decrement — done, verified live 2026-07-14 (both a fast task and a
  longer one completed correctly with decrypted `result`, correct `model_used`/token counts).
- Detail page shows the activity log growing while running and swaps to rendered output on
  completion — done, verified live 2026-07-14 at the API level (`progress` field observed
  accumulating partial content across multiple polls while `status=running`, `has_progress: true`;
  cleared to `null`/`false` once the terminal `result` was written). Frontend rendering itself not
  re-driven through a browser this session — code-verified via unit tests + this API-level check.
- L1–L4 cannot see `/tasks` or submit — enforced via `canUseTasks()` (frontend) — done,
  code-verified. Live check 2026-07-14 found the **backend** behavior is actually the same silent
  D16-style downgrade used elsewhere, not a hard reject: an L1 `POST /tasks` returns 202 and
  `downgrade_to_local: true`, and the task genuinely executes on the local model
  (`model_used: "gemma4:26b"`), Hermes is never called. So the governance property holds (Hermes
  unreachable by unauthorized roles) even though submission itself isn't blocked server-side —
  worth confirming this matches intent, since it differs from a literal reading of "cannot submit."
  Also found: the live activity log's `"start"` event hardcodes `"Task started on Hermes"` even on
  a downgraded run, which is misleading in that case — a minor logging bug, not a security issue
  (`backend/app/services/agent_tasks.py`, the `on_event` "start" handler).
- Blank `HERMES_API_KEY` → `POST /tasks` returns 503 — done, unit-tested.

### Phase 3 acceptance gate
- RAG works on Thai + English documents with reasonable accuracy
- p95 RAG query latency < 8s end-to-end
- Image gen quota tracked separately from text tokens
- Marketing team uses image gen for ≥ 1 month without incident

---

### Phase 4 — Hardening (ongoing)

Lower-priority but important:

- ☐ **Key management**: migrate `ENCRYPTION_KEY` from env to HashiCorp Vault or Google Cloud KMS
- ☐ **Backups**: nightly `pg_dump` to encrypted S3 location; tested restore procedure
- ☐ **Langfuse**: self-host, wire all LLM calls for observability
- ☐ **Rate limiting**: per-user request-per-minute cap at gateway
- ☐ **Prometheus + Grafana**: latency, error rate, GPU temp, queue depth dashboards
- ☐ **NER-based PII detection**: improve over regex with a Thai-aware NER model
- ☐ **Pen test**: external security review before opening beyond pilot

---

## 7. Critical Implementation Patterns

### 7.1 Always encrypt at the boundary

**Wrong:**
```python
msg = Message(content=user_text, ...)
db.add(msg)
```

**Right:**
```python
ct, nonce, tag, kv = crypto.encrypt(user_text)
msg = Message(
    content_ciphertext=ct,
    content_nonce=nonce,
    content_tag=tag,
    key_version=kv,
    ...
)
db.add(msg)
```

Plaintext must never touch the DB. Even during debugging. If you need to inspect content, go through the reveal flow.

### 7.2 Policy decision is the only path to an LLM

Every LLM call in the codebase must be preceded by a `PolicyEngine.decide()` call whose output is the model code used. **Never** hardcode a provider in business logic. If you find yourself writing `anthropic.Client()...` outside `app/llm/anthropic.py`, stop.

### 7.3 Audit logs are append-only

No update, no delete. Use `audit_log` partitioning to drop old partitions wholesale when retention requires. Audit writes are async (Celery) so they cannot slow user requests, but they must be reliable — Celery's `acks_late=True` + at-least-once delivery is the contract.

### 7.4 SSE streaming + early-abort

Chat responses stream via SSE. The orchestrator must:
- Yield the first token within 2s (status: `working`)
- Yield tier/model decision before content streams (so frontend can show badges)
- Cancel cleanly if the client disconnects (don't burn external API tokens on abandoned requests)

### 7.5 Quota is decremented after response

Reserve estimate at request time (policy check); commit actuals from the streamed response's final usage block. If the stream fails mid-way, charge for partial usage based on tokens received.

### 7.6 Conversation history must be re-classified

If a Tier 1 conversation later includes a Tier 3 message, the **entire next request** to the LLM (history + new message) is Tier 3. Always re-classify the full payload, not just the latest message.

---

## 8. Gotchas (from earlier conversations)

1. **Redis DB index separation matters.** Don't share keyspaces between cache and broker. Set them explicitly in `config.py` and never use the default DB 0 for everything.

2. **llama.cpp's `--parallel N`** enables continuous batching but each parallel slot reserves KV cache. On 4090 with Qwen 14B Q5, start with `--parallel 4` and monitor VRAM headroom. Going to 8 may OOM.

3. **GPU split for embed + chat** — if running both llama.cpp containers on one 4090, they share VRAM. Budget: Qwen 14B Q5 ~10GB + KV cache ~6GB + BGE-M3 ~1.2GB + headroom = tight. If issues, run embed-server on CPU or reduce Qwen parallel slots.

4. **Garage is finicky to bootstrap.** First-time setup requires `garage layout` commands to assign storage nodes. Document this thoroughly in README, with a working `garage.toml` example.

5. **Postgres ENUM types are painful to alter.** When adding new role levels or actions, use Alembic's `op.execute("ALTER TYPE ... ADD VALUE ...")` and remember it can't run inside a transaction in older PG versions.

6. **JWT in cookies + CORS**: backend on `api.decomplica.tech`, frontend on `chat.decomplica.tech` — two different hosts. Cookie must be `Secure; HttpOnly; SameSite=None; Domain=.decomplica.tech` and CORS allow-credentials configured. Easy to misconfigure.

7. **Google's `hd` claim is not sufficient by itself** — also verify `email_verified=true` and confirm via Workspace Admin SDK that the account is active (defer to Phase 4 if you don't want SCIM yet).

8. **PII regex false positives**: Thai national ID regex matches some sequences that aren't IDs. Add a checksum validation function for the 13-digit format to reduce noise.

9. **Decrypting in reveal must be rate-limited.** Even with 4-eyes, a malicious admin pair could enumerate. Add a hard cap (e.g., 10 reveals/admin/month) with audit alerts.

10. **Frontend tier badges are UX-critical.** Users must see "this response came from the local model because your message contained sensitive data." Hidden downgrades feel like the AI is "dumber on Mondays" — surface the reason clearly.

---

## 9. Testing Strategy

### Unit tests (pytest)
- `crypto.py`: round-trip, tamper detection, key rotation
- `classifier.py`: every regex pattern, false-positive cases for Thai
- `policy_engine.py`: every branch (uses in-memory SQLite or test Postgres)
- `quota.py`: concurrent decrement
- LLM adapters: mock httpx, verify request shape

### Integration tests
- Spin up full compose stack with `pytest-docker`
- End-to-end: login → send message → verify DB state, audit trail, encryption
- Reveal flow: 4-eyes happy path + self-approve denial

### Manual test checklists
Maintain `tests/manual/` with Markdown checklists for things hard to automate:
- New external provider added
- Phase gate releases
- Disaster recovery (restore from backup)

### Load test
Before Phase 2 gate: `locust` script with 30 concurrent users, 5-min hold, measure p50/p95/p99 latency.

---

## 10. Local Development Setup

```bash
# Prereqs: Docker, Docker Compose v2, NVIDIA Container Toolkit (for GPU)

git clone <repo> ai-gateway && cd ai-gateway

# Download models (manual; document URLs in README)
mkdir -p models
# put qwen2.5-14b-instruct-q5_k_m.gguf and bge-m3-q8_0.gguf here

# Configure env
cp .env.example .env
# Edit .env:
#   POSTGRES_PASSWORD=<random>
#   ENCRYPTION_KEY=$(openssl rand -base64 32)
#   JWT_SECRET=$(openssl rand -hex 32)
#   GOOGLE_OAUTH_CLIENT_ID / SECRET from Google Cloud Console
#   GOOGLE_WORKSPACE_DOMAIN=company.com
#   GARAGE_ACCESS_KEY / SECRET from `garage key new`
#   ANTHROPIC_API_KEY etc. (Phase 2+ only)

# First boot
docker compose up -d postgres redis garage
docker compose run --rm backend-api alembic upgrade head
docker compose run --rm backend-api python -m scripts.bootstrap_admin --email you@company.com
docker compose up -d

# Garage bucket setup (one-time)
docker compose exec garage garage bucket create brandbiz-files
docker compose exec garage garage bucket allow --read --write brandbiz-files --key <key-id>

# Verify
curl https://api.decomplica.tech/health
```

Add to hosts file during local dev:
- **Windows** (admin Notepad): `C:\Windows\System32\drivers\etc\hosts`
- **Linux/macOS**: `/etc/hosts`

```
127.0.0.1  chat.decomplica.tech admin.decomplica.tech api.decomplica.tech
```

For HTTPS during dev: Caddy issues certs from its internal CA (`local_certs`). Export and trust once:
```powershell
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt .\caddy-root.crt
Import-Certificate -FilePath .\caddy-root.crt -CertStoreLocation Cert:\LocalMachine\Root
```

Register the OAuth redirect URI in Google Cloud Console:
```
https://api.decomplica.tech/auth/google/callback
```

---

## 11. Out of Scope (do not build)

Explicit non-goals to prevent scope creep:

- ❌ Mobile apps (web is responsive enough)
- ❌ Voice input/output
- ❌ Custom model fine-tuning UI
- ❌ Multi-tenancy (single company only)
- ❌ Federated identity beyond Google Workspace
- ❌ Plugin marketplace
- ❌ Inline document editing (Google Docs–style)
- ❌ Slack/Teams bot integration in Phase 1–3 (revisit in Phase 4 if asked)
- ❌ Custom embedding models per user/group
- ❌ Hot-swap of encryption keys without downtime (Phase 4)

---

## 12. Open Questions

Items to revisit with the user before or during the relevant phase:

1. **Tier 4 actor**: who is authorized to handle M&A / source-code level data? L5+ is set by default — confirm against the actual org chart before Phase 2 launch.
2. **Reveal approver pool**: which roles can approve? Currently any ADMIN. Should there be a separate "compliance" role? (Phase 2)
3. **Audit log retention**: indefinite for now. Compliance team may want a max (e.g., 7 years). Confirm with Legal before any production data lands.
4. **Default model on auto**: if user doesn't pick a model, currently the orchestrator picks the highest one their role allows. Alternative: always start with local, escalate on user request. Decide before Phase 2.
5. **Cost allocation**: should departments be billed back for external API usage? If yes, add `department_id` to messages and aggregate. (Phase 2 or 3)
6. **External provider fallback**: if Claude is down, fall through to GPT? Or error? Currently errors. (Phase 3 hardening)

---

## 13. Related Artifacts

Files referenced throughout this plan, generated in prior planning sessions:

- `schema.sql` — Postgres DDL + seed data
- `docker-compose.yml` — service definitions
- `policy_engine.py` — reference implementation of Section 7.2

Drop these into the repo at the paths indicated in Section 5 as starting points. They are not final — refine during implementation but preserve their structural decisions.

---

*Last updated: 2026-05-25*
