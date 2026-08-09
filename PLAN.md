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
- ~~Customer-facing chatbot~~ — superseded by D21/D22 (Phase 5, Client Workspaces). A bounded,
  tenant-isolated client-facing surface is now in scope; a general-purpose public chatbot is not.
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
| D21 | Client workspaces are in scope: a bounded, tenant-isolated client-facing surface (Phase 5) for external prospects/clients to interview with an AI persona and reach a costed plan, handed off to a human expert. Not a general-purpose public chatbot — every client seat belongs to a `workspace_id` and only reaches agents/skills/files scoped to that workspace. | Business requirement — event demo + productized client funnel (see `DSME_ai.md`, `brandbiz_ecosystem_and_workflow.md`). Supersedes the "Customer-facing chatbot" non-goal in §1. |
| D22 | The gateway has two tenant classes: **internal** (`users.workspace_id IS NULL`, unchanged behavior) and **client** (`users.workspace_id` set). A single `workspace_visibility_filter` helper gates `files`, `skills`, and `agents` visibility; `require_internal` gates all existing internal routers at `include_router` level. This is deliberately *not* full multi-tenancy — internal users still share one pool exactly as before. | Cheapest correct fix for the tenant-leak risk introduced by D21, without rewriting every scoping predicate in the codebase. Supersedes "Multi-tenancy (single company only)" in §11 — see the amended entry there. |
| | **Amended by D23:** `require_internal` is now flag-gated (admits client seats when `CLIENT_INTERNAL_ACCESS_ENABLED` is on, default off), and `workspace_visibility_filter` is now asymmetric — the shared internal pool (`workspace_id IS NULL`) is readable by all tenants when the flag is on, while a workspace's own rows stay readable only in-workspace. The two-mechanism design itself is unchanged; only what each mechanism decides has changed. `require_client` is removed (it never had a call site — `require_client_context` is the real gate for `/client/*`). Two routers (`hermes`, `automations`) are carved out onto a new hard `require_staff` / `require_staff_principal` gate that never reads the flag. | |
| D23 | Client-workspace seats may use the full internal app (chat, files, agents, skills, studio, tasks, conversations, image), behind one reversible switch (`CLIENT_INTERNAL_ACCESS_ENABLED`, default **off** in code) — not just `/client/*`. When on: `require_internal` admits client seats to the internal routers — except `hermes` and `automations`, which stay on a hard `require_staff` gate — and `workspace_visibility_filter` widens to "the shared internal pool is readable by everyone; a workspace's own rows stay readable only within that workspace." Everything a client seat *creates* is stamped with its own `workspace_id` and forced private to that seat (`scope="personal"` / `visibility="personal"`), because every booth attendee shares one workspace (`redeem_invite` mints into `invite.workspace_id`) — client-to-client isolation is the one invariant this does not relax. | The owner wants event-booth attendees to get the whole product, not a walled demo, and explicitly accepted the resulting exposure of the internal knowledge base, public agents/skills, and staff emails on agent cards (`routers/agents.py`'s creator enrichment). A single flag keeps it reversible mid-event without a deploy. Per-seat private-by-default writes are required, not optional, because the pooled event cost cap (`workspaces.token_budget_limit`) is per-workspace, ruling out one workspace per invite as an alternative. See `docs/adr/0001-client-seats-in-the-internal-app.md`. |

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
- Gateway-side client + wiring; Hermes itself runs **natively on the Docker host** (revised again
  2026-07-14 — originally a manual host install, then briefly a `hermes` compose service; now back
  to a native install as the default, per user preference). Install via NousResearch's official
  installer, configure the API server in Hermes's `.env` (`%LOCALAPPDATA%\hermes\.env` on Windows,
  `~/.hermes/.env` on Linux/macOS: `API_SERVER_ENABLED=true`, `API_SERVER_HOST=0.0.0.0`,
  `API_SERVER_KEY` = `HERMES_API_KEY`), start with `hermes gateway run` — full steps in
  `.env.example`. `backend-api` reaches it at `http://host.docker.internal:8642/v1` (via
  `extra_hosts`). The compose services (`hermes` + one-shot `hermes-init` config writer, official
  `nousresearch/hermes-agent` image, pointed at Ollama via `HERMES_OLLAMA_URL`/
  `HERMES_OLLAMA_MODEL`) remain as an opt-in fallback behind the `hermes-docker` profile:
  `docker compose --profile hermes-docker up -d` + `HERMES_API_URL=http://hermes:8642/v1`.
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

#### Task 3.13 — Hermes host-setup from the Tasks page ☑

Companion to the Task 3.11 revision that moved Hermes back to a native host install (2026-07-14):
since Hermes now runs on the Docker host, the backend can't install or start it itself. This adds
the next-best thing to a one-click install: the Tasks page shows a live online/offline banner, and
when Hermes is offline an ADMIN can download a generated, pre-configured `install-hermes.ps1`
(one `powershell -ExecutionPolicy Bypass -File` run on the host installs Hermes via NousResearch's
official installer and starts `hermes gateway run`). The banner polls and flips to green on its
own once Hermes comes up.

**Scope:**
- `GET /hermes/status` — live reachability probe (`GET {HERMES_API_URL}/models`, 3s timeout);
  visible to any consented user, drives the banner poll (10s while offline, stops when online).
- `GET /hermes/setup-script` — ADMIN-only download. The script embeds `HERMES_API_KEY` (it becomes
  Hermes's own `API_SERVER_KEY`) plus `HERMES_OLLAMA_URL`/`HERMES_OLLAMA_MODEL`, and mirrors the
  `hermes-init` compose service's contract exactly: API server on `0.0.0.0:8642`, config written
  only if absent (never clobbers an existing install's sessions/memory/skills). Every download is
  audit-logged (`hermes_setup_script_downloaded`) since it hands out the shared secret.
- Non-admins seeing the offline banner get "ask an administrator" instead of the button.
- Explicitly NOT built: the backend executing anything on the host (no Docker-socket exposure, no
  host helper daemon — considered and rejected with the user in favor of this download approach).

**Files touched:**
- NEW `backend/app/services/hermes_setup.py` — `probe()` + `render_setup_script()` (PowerShell
  template filled via `.replace()`, not `str.format()` — the template is full of `${}` blocks)
- NEW `backend/app/routers/hermes.py` — the two endpoints; registered in `app/main.py`
- NEW `backend/alembic/versions/0034_hermes_setup_audit_action.py` — `audit_action` enum value
  (no COMMIT needed, same reasoning as 0031); `backend/app/models/audit.py` ORM tuple updated
- `backend/app/config.py` + `docker-compose.yml` — `hermes_ollama_url`/`hermes_ollama_model` now
  also passed to backend-api (previously only `hermes-init` saw them), used only to render the
  script
- NEW `backend/tests/unit/test_hermes_setup.py` — 6 tests: probe short-circuit/reachable/
  conn-error/non-200, script placeholder fill, hermes-init contract mirror
- NEW `frontend-chat/components/tasks/HermesStatusBanner.tsx` — banner + poll + admin-gated
  download (admin check via `/api/me`, same as `ChatPane`); wired into
  `components/tasks/TasksPage.tsx`
- NEW `frontend-chat/app/api/hermes/status/route.ts` + `setup-script/route.ts` — proxy routes
  mirroring `app/api/tasks/**`

**Accept:**
- Unit tests pass (6 new; full suite's 15 pre-existing host-env failures confirmed identical on
  clean HEAD via a temp worktree) — done, verified 2026-07-14.
- Migration 0034 applied clean; a script download now writes a real `audit_log` row (first attempt
  silently failed on the missing enum value — caught live because audit `log()` swallows errors by
  design, §7.3) — done, verified 2026-07-14.
- Auth matrix verified live: `/hermes/status` 401 unauth / 200 for consented users;
  `/hermes/setup-script` 403 non-admin / 200 + `Content-Disposition: attachment` for ADMIN, with
  key/URL/model correctly embedded and no placeholders left — done, verified 2026-07-14.
- Generated script parses clean under PowerShell's own parser (`Parser::ParseFile`, 0 errors) —
  done, verified 2026-07-14. Not yet exercised end-to-end (an actual install run on a fresh host)
  — it composes the already-live-verified manual steps from the Task 3.11 revision.
- `next build` passes with the new routes/component — done, verified 2026-07-14.

#### Task 3.14 — One-click native Hermes setup via a host helper ☑

Upgrades Task 3.13's download-and-run flow to a single button, per user request ("only click 1
time"). The backend (containerized) still cannot execute anything on the host — the workaround is
a tiny host helper, installed ONCE via a downloadable `install-helper.ps1`, that polls the gateway
outbound for jobs. After that: Tasks-page banner button → job queued → helper claims it → installs/
starts Hermes natively → progress lines stream into the banner → flips green. The helper also
restarts Hermes at logon/crash, so "keep the window open" goes away.

**Security posture (deliberate):**
- The gateway never sends code to the host. A claimed job carries lifecycle state plus Hermes's two
  config *files* (data); the helper's only behavior is the hardcoded install/start routine baked in
  at helper-install time (`Invoke-SetupJob`; no `Invoke-Expression` anywhere).
- The helper polls outbound with a dedicated least-privilege service account
  (`hermes-helper@service.local`, role L1) via the existing `gw_` API-key mechanism; claim/report
  endpoints reject every other principal. Each helper-script download rotates the key (old ones
  revoked). No inbound port, no Docker-socket exposure (considered and rejected).
- Both script downloads and every job creation are audit-logged.

**Files touched:**
- NEW `backend/app/models/hermes_host_job.py` + `alembic/versions/0035_hermes_host_job.py` —
  job table (VARCHAR status per Gotcha #5) + 2 `audit_action` values; `models/audit.py` +
  `models/__init__.py` updated
- NEW `backend/app/services/hermes_host_jobs.py` — job lifecycle (create/claim/report/latest),
  in-memory helper heartbeat (`helper_online()`, 15s window), helper service-account key minting
  with rotation, and the `install-helper.ps1` template (installer + `-Run` polling loop in one
  self-copying file)
- `backend/app/services/hermes_setup.py` — config.yaml/.env bodies extracted to shared
  `render_config_yaml()`/`render_env_file()` used by both the manual script and job payloads
- `backend/app/routers/hermes.py` — status gains `helper_online`; `POST /hermes/host-jobs` (ADMIN,
  202/409), `GET /hermes/host-jobs/latest` (consented), `GET /hermes/host-jobs/pending` (204 when
  idle) + `POST /hermes/host-jobs/{id}/report` (helper key only), `GET /hermes/helper-script`
  (ADMIN, audited)
- NEW `backend/tests/unit/test_hermes_host_jobs.py` — 11 tests (liveness window, 409-on-active,
  claim heartbeat + transition, report validation/404/409/append/cap, key minting, script render
  is trigger-only)
- `frontend-chat/components/tasks/HermesStatusBanner.tsx` — helper-aware: one-click "Set up Hermes
  now" + live job log (2s poll) when the helper is online; "Download helper installer (one-time)"
  with the manual script as fallback link when it isn't
- NEW `frontend-chat/app/api/hermes/host-jobs/route.ts`, `host-jobs/latest/route.ts`,
  `helper-script/route.ts` — proxy routes

**Accept:**
- Unit tests pass (11 new + 6 refactor-covered 3.13 tests) — done, verified 2026-07-14.
- Migration 0035 applied clean — done, verified 2026-07-14.
- Full lifecycle verified live with a simulated helper (real HTTP): mint 200 → queue 202 (L1 403,
  duplicate 409) → claim 200 with config payload (bad key 401, JWT-only 401, empty poll 204 +
  heartbeat flips `helper_online`) → progress report 200 → terminal report 200 with `finished_at`
  (late report 409) → `latest` 200 for the banner; audit rows for both new actions present — done,
  verified 2026-07-14. Found+fixed live: post-commit `updated_at` (server-side `onupdate`) expiry
  made response serialization lazy-load outside the async context (500 after a successful write);
  explicit `session.refresh()` in claim/report.
- Generated `install-helper.ps1` parses clean (`Parser::ParseFile`, 0 errors) — done, verified
  2026-07-14. Not yet exercised on a real host (needs the user to install the helper once); the
  helper's setup routine is the same live-verified sequence as Task 3.13's script.
- `next build` passes — done, verified 2026-07-14.

**Follow-on (2026-07-15) — download the .cmd wrapper is actually double-clickable:** the user
clicked the button, and nothing happened — root cause was UX, not a backend bug: the download
landed in their Downloads folder correctly, but a bare `.ps1` does nothing useful on double-click
(Windows opens it in Notepad instead of running it), so the "one click" flow silently stalled at
"the user must separately know to open PowerShell." Fixed by wrapping `render_helper_script()`'s
output in a self-extracting `.cmd` — real double-click support — plus a banner state that makes
the remaining manual step ("double-click the file you just downloaded") impossible to miss.
- NEW `render_helper_installer_cmd()` in `backend/app/services/hermes_host_jobs.py` — a fixed
  6-line batch header (`_CMD_STUB`/`_CMD_STUB_LINES`) that peels itself off via
  `Get-Content | Select-Object -Skip N` and writes the remainder (byte-identical to
  `render_helper_script()`) to a temp `.ps1`, then runs that; `exit /b` stops cmd.exe before it
  ever reaches the PS1 payload as batch text. CRLF throughout (cmd.exe requirement).
- **Found + fixed live, before it reached the user a second time:** the first version used
  `Get-Content -LiteralPath ... -Skip N`, which parses and imports cleanly (`ParseFile` is
  syntax-only) but silently doesn't exist as a *parameter* — `-Skip` on `Get-Content` is
  PowerShell 7+ only. Windows ships Windows PowerShell 5.1 (`powershell.exe`), where invoking it
  throws `ParameterBindingException` at runtime. Caught by actually running the generated command
  against this machine's real PowerShell (5.1.26100) before shipping, not just parsing it. Fixed
  to `Get-Content | Select-Object -Skip N` (`Select-Object -Skip` is a generic cmdlet parameter,
  supported since PowerShell v2/v3, not provider-specific) — live-verified extraction + a clean
  `ParseInput` on the result.
- `backend/app/routers/hermes.py` — `/hermes/helper-script` now serves `render_helper_installer_cmd()`,
  filename `install-helper.cmd`; `_ps1_download` renamed `_script_download` (serves both extensions
  now)
- `frontend-chat/app/api/hermes/helper-script/route.ts` — forwarded filename → `install-helper.cmd`
- `frontend-chat/components/tasks/HermesStatusBanner.tsx` — new `helperDownloaded` state
  (persisted via `sessionStorage` so a page reload doesn't silently revert to the download button
  mid-install), showing a pulsing "Downloaded install-helper.cmd — double-click it… waiting for
  the helper to connect" panel until `helper_online` flips true
- `backend/tests/unit/test_hermes_host_jobs.py` — 4 new tests: CRLF-throughout + exits-before-payload,
  line-by-line round-trip identical to `render_helper_script()`, stub explicitly asserts
  `Select-Object -Skip` present / `Get-Content -Skip` absent (regression guard for the exact bug
  above), no leftover placeholders

**Accept (follow-on):** unit tests pass (15 total) — done, verified 2026-07-15. Generated `.cmd`
downloaded from the live endpoint and validated directly on the target Windows PowerShell (5.1.26100):
6-line CRLF header, `Select-Object -Skip` extraction byte-for-byte matches `render_helper_script()`'s
output, extracted payload parses with 0 errors — done, verified 2026-07-15. Actually *running* the
installer was correctly blocked by the harness's permission system (registers a persistent Scheduled
Task + will later trigger an external NousResearch download) — this is a user action by design, not
re-attempted; the user was handed the one-double-click instruction instead.

#### Task 3.15 — Multi-turn Hermes tasks (chat within a task) ☑

Redesigns the Tasks detail page from one-shot (single prompt → single result, per Task 3.12) into
a two-column conversation view, per user request ("change it to be like this [Cowork chat
screenshot]"): a scrollable transcript on the left with a composer to keep chatting, and a
**Progress** checklist sidebar on the right (Downloads/Context panels from the reference screenshot
explicitly dropped — no backing data). Confirmed with user: follow-ups run **in the background and
are polled** (same execution model as Task 3.12, no live token streaming) so "assign it, close the
tab" still holds for every turn, not just the first.

Turned out to be mostly wiring, not new infrastructure: `AgentTask` already carries a
`conversation_id` (Task 3.12), and the normal `/chat` path already appends a new user+assistant
`Message` pair to an *existing* conversation via `prepare_chat()` → `call_llm()`. `submit_task()`
just always seeded a *fresh* conversation and never sent a second turn. No schema/migration change.

**Files touched:**
- `backend/app/services/agent_tasks.py` — NEW `add_followup()` (mirrors `submit_task()`: 409 if a
  turn is already `queued`/`running`, else `prepare_chat(conversation_id=task.conversation_id, ...)`
  re-queues the *same* row and schedules another `_run_task` run); NEW `get_transcript()` (decrypts
  all `Message` rows for the task's conversation, same pattern as `GET /conversations/{id}`).
  `_run_task` unchanged — it already overwrites `result_*`/`status` on completion, which works
  identically for turn 2+.
- `backend/app/routers/tasks.py` — `TaskDetail.messages: list[MessageOut]` (populated via
  `get_transcript`); NEW `POST /tasks/{id}/messages` (202, same deps as `submit`).
- NEW `frontend-chat/app/api/tasks/[id]/messages/route.ts` — proxy, mirrors `[id]/cancel/route.ts`.
- `frontend-chat/components/tasks/TaskDetailView.tsx` — rewritten: chat bubbles (reusing
  `ChatPane.tsx`'s visual language) rendered from `messages`, with an in-flight-turn fallback
  (Message rows only commit once a turn finishes, so the pending turn renders from
  `prompt`/`progress` instead); composer disabled while a turn is active; `Re-run` button dropped
  (follow-ups replace it); NEW `ProgressPanel` sidebar component parses the existing `- `-prefixed
  activity-log lines into a checklist (checked/struck-through once past, spinning on the current
  step) — replaces the old flat monospace activity-log block.
- `backend/tests/unit/test_agent_tasks.py` — 4 new tests: `add_followup` 409-when-active and
  requeue-on-existing-conversation; `get_transcript` empty-when-no-conversation and
  decrypts-in-order.
- `TasksPage.tsx` (the list + compose box) intentionally **unchanged** — already matched the
  desired design.

**Accept:**
- Unit tests pass (11/11 in `test_agent_tasks.py`, including the 4 new ones) — done, verified
  2026-07-15.
- `next build` (typecheck) passes with the new proxy route and rewritten detail page — done,
  verified 2026-07-15.
- Full backend suite run for regressions: 27 pre-existing failures confirmed unrelated (same
  failures reproduce with these changes `git stash`ed — crypto/audit/orchestrator tests failing on
  env-level issues, not this change) — done, verified 2026-07-15.
- Live E2E (send a follow-up against a real Hermes instance, confirm transcript + Progress panel
  update correctly, composer re-enables after) — **not yet done this session**; code- and
  unit-test-verified only. Flagging honestly rather than claiming a live check that didn't happen.

#### Task 3.16 — Skills: reusable instruction bundles for chat ☑

Net-new feature (not a pre-existing numbered task) requested by user, modeled directly on the
"Skills" capability at `claude.ai/new#settings/customize-skills`, scraped live via the Chrome
extension to capture the real shape rather than guessing: a skill is `name` (kebab-case slug,
doubles as the `/name` command) + `description` (the auto-match trigger) + `instructions` (system
prompt body), with a per-skill enable toggle and either a "Write skill instructions" form or a
`SKILL.md` upload (frontmatter-parsed). Confirmed with user: **auto-match + manual invocation**
(description-matched, `/slug` forced, or pinned to an Agent as always-on), **chat only** for this
pass (Tasks/Hermes integration deferred), **instructions + `SKILL.md` upload** only — no knowledge
files, no script execution (stays clear of the §11 "plugin marketplace" exclusion; this is
instruction bundles, same class as the existing Agent feature).

Maps directly onto the existing **Agent** primitive (`agents`/`agent_files`) plus one new
selection step, injected through the single existing governance seam
(`chat_policy.prepare_chat()` → `system_prompt`), so skills inherit tier classification, quota, and
audit for free — §7.2 (`PolicyEngine.decide()` is the only path to an LLM) is untouched; skill
selection itself only ever calls the **local** model (always policy-allowed), never an external
one.

**Files touched:**
- NEW `backend/app/models/skill.py` — `Skill` + `AgentSkill` (join), VARCHAR/BOOLEAN not PG enum
  (Gotcha #5), `UNIQUE(user_id, name)`. Registered in `app/models/__init__.py`.
- NEW `backend/alembic/versions/0036_skills.py`, `0037_skill_audit_actions.py` — idempotent
  `CREATE TABLE IF NOT EXISTS` (mirrors `0018_agents.py`); `skill_created`/`skill_updated`/
  `skill_deleted`/`skill_invoked` added to the `audit_action` enum and to `app/models/audit.py`.
- NEW `backend/app/services/skill.py` — CRUD, `parse_skill_markdown()` (hand-rolled frontmatter
  parse — no new PyYAML dependency), agent-pin helpers (`attach_skill`/`detach_skill`/
  `get_agent_skill_ids`/`get_pinned_skills`), `build_skill_system_block()`.
- NEW `backend/app/services/skill_selector.py` — `extract_forced_slug()` (leading `/slug`),
  `match_skills_by_description()` (asks the local model for a JSON array of relevant skill names;
  same graceful-fallback-to-`[]` shape as `app/tools/intent.classify_intent`), `select_skills()`
  (forced ∪ pinned always kept, auto-match fills remaining slots up to `max_n=5`).
- `backend/app/services/chat_policy.py` — `prepare_chat()` gained `explicit_skills` param; new
  block after agent-loading composes `agent_system_prompt` + selected skills' instructions, writes
  one `skill_invoked` audit row when any skill applies.
- NEW `backend/app/routers/skills.py` (`/skills` CRUD + `/skills/upload` + `/skills/{id}/toggle`);
  `backend/app/routers/agents.py` gained `GET/POST /agents/{id}/skills` +
  `DELETE /agents/{id}/skills/{skill_id}` (pin/unpin); registered in `app/main.py`;
  `routers/chat.py` `ChatRequest` gained optional `skills: list[str] | None`.
- NEW `frontend-chat/app/skills/**` (layout, list, create, edit — mirrors `app/agent/**`),
  `components/skills/{SkillsPage,SkillForm,SkillDetailModal}.tsx`, `app/api/skills/**` +
  `app/api/agent/[id]/skills/**` proxies. `components/agent/CreateAgentForm.tsx` gained a "Skills"
  pin picker section. `components/NavSidebar.tsx` gained a Skills nav entry (`Ic.layers`).
- NEW `backend/tests/unit/{test_skill_service,test_skill_selector,test_chat_policy_skills}.py` (62
  tests). `backend/tests/unit/test_chat_policy.py` gained an autouse `no_skills` fixture stubbing
  `skill_svc.get_enabled_skills` — the new unconditional lookup in `prepare_chat()` would otherwise
  exhaust those tests' hand-built `session.execute` `side_effect` lists.

**Accept:**
- Unit tests pass: 62/62 new (`test_skill_service.py`, `test_skill_selector.py`,
  `test_chat_policy_skills.py`) — done, verified 2026-07-17.
- Full backend suite regression check: 28 pre-existing failures confirmed unrelated — identical
  failure set reproduces on a `git stash -u` clean baseline (crypto/audit/orchestrator/
  vault_connection/alert/consent/google_llm, full-suite test-order pollution, unrelated to this
  change) — done, verified 2026-07-17.
- `tsc --noEmit` and `next build` pass with the new `/skills` routes — done, verified 2026-07-17.
- Live E2E against the running docker-compose stack (rebuilt `backend-api` + `frontend-chat`
  images): migrations `0036`/`0037` applied cleanly; create/list/toggle/delete a skill and upload a
  `SKILL.md` via the real API (direct + through the Next.js proxy); pin/unpin a skill to a real
  Agent and confirm `GET /agents/{id}/skills`; sent `/morning ...` through `/chat` and confirmed the
  `skill_invoked` audit row recorded `forced=["morning"]` with the *other* candidate skill correctly
  excluded (local-model auto-match gracefully returned `[]` — the dev sandbox can't reach the
  configured local LLM host, an environment limitation, not a code defect) — done, verified
  2026-07-17. Test data cleaned up after (skills/agent deleted; `skill_invoked` audit rows
  deliberately left in place per §7.3, audit_log is append-only).
- Browser UI click-through (create/toggle/edit/delete via the rendered pages) — **not done this
  session**: verification used the app's own JWT-signing to authenticate `curl`/API calls directly,
  since entering a password into the login form to drive the browser is a prohibited action.
  Flagging honestly rather than claiming a browser check that didn't happen; `next build` + the API
  E2E above are the verification that stands in for it.

**Follow-on (same session) — "Create with AI":** the original scrape showed three Add-menu options
on claude.ai (*Create with Claude* / *Write skill instructions* / *Upload a skill*); the first pass
shipped only the latter two. User asked where the third option was and confirmed they wanted it
built, renamed **"Create with AI"** (this gateway is multi-provider/local-first, not
Claude-branded) — a chat-style modal that asks clarifying questions, then hands off a drafted
`name`/`description`/`instructions` for review via the existing "Write skill instructions" form.
Local-model-only, following the exact precedent already set by `skill_selector`'s auto-match and
`app/tools/intent.classify_intent()` (background/utility calls to the local model skip
`PolicyEngine.decide()`, consistent with `policy_engine.py`'s own first rule that the local model is
always allowed) — no quota, no tier classification of the drafting chat, and unlike the selector's
silent `[]` fallback, failures surface a friendly in-chat message since this is a foreground
feature.
- `backend/app/services/skill.py` — new `draft_skill(messages)`: local-model call with a
  system prompt instructing one clarifying question at a time until it can respond with a JSON
  `{name, description, instructions}` object; defensive `{`...`}` extraction (same shape as the
  selector's `[`...`]` extraction), non-slug names normalized via a fallback slugifier, any
  exception or incomplete JSON returns a friendly `done=false` message rather than raising or
  leaking raw JSON into the chat.
- `backend/app/routers/skills.py` — new `POST /skills/draft` (+ DTOs), declared before
  `GET/PUT/DELETE /{skill_id}`; no audit row (mirrors `classify_intent`/the selector — no privileged
  action, nothing persisted until the user saves).
- `backend/tests/unit/test_skill_service.py` — new `TestDraftSkill` class, 7 tests: valid JSON →
  done+normalized draft, JSON wrapped in prose still parses, plain text → clarifying question,
  incomplete JSON → friendly message (never leaks raw JSON), non-slug name normalized, local-model
  exception → graceful fallback, malformed JSON → graceful fallback. 42/42 pass in the file
  (35 existing + 7 new).
- NEW `frontend-chat/components/skills/CreateWithAIModal.tsx` — self-contained chat modal (bubbles +
  composer, not a reuse of `ChatPane.tsx` — no streaming needed) with a "draft ready" review card
  (Keep refining / Review & edit); NEW `frontend-chat/app/api/skills/draft/route.ts` proxy.
- `frontend-chat/components/skills/SkillsPage.tsx` — `AddMenu` gained a third item, "Create with AI"
  (`Ic.spark`), above "Write skill instructions".
- `frontend-chat/components/skills/SkillForm.tsx` — new `useEffect` (not a lazy `useState`
  initializer, to avoid an SSR/hydration mismatch) that reads a one-time `sessionStorage` handoff
  (`skill_draft`) written by the modal's "Review & edit" button, prefilling the existing form so the
  save path is fully reused — no duplicate field markup or second save endpoint.
- **Accept:** `pytest test_skill_service.py` 42/42 pass; `tsc --noEmit` clean; `docker compose build`
  succeeds for both images (`/api/skills/draft` present in the Next.js route manifest); live against
  the rebuilt stack — `POST /skills/draft` routes correctly and returns the designed graceful
  fallback both directly and through the Next.js proxy (same unreachable-local-LLM sandbox
  limitation as the parent task, not a code defect — the "happy path" JSON-drafting logic is
  unit-test-verified with a mocked client); unauthenticated `GET /skills` 307-redirects to `/login`
  with no server error — done, verified 2026-07-17. Browser click-through of the actual chat
  modal — same **not done this session** caveat as above (password-entry restriction).

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

### Phase 5 — Client Workspaces (D21/D22)

A bounded, tenant-isolated client-facing surface: an outside prospect signs in, an AI persona
(น้องภูมิ) runs a deterministic intake, pulls live market research, matches the company's case
library, and drafts a costed plan handed off to a human expert. Built for a work event where
outside people try it hands-on, and productized from there. See the implementation plan filed for
"Client Workspaces — implementing `Brandbiz Workspace.dc.html`" for full design detail; this
section tracks task-level progress per the usual PLAN.md convention.

- ☑ 5.1 Tenant seam — `workspaces` table, `users.workspace_id`, `files.workspace_id`,
      `workspace_visibility_filter`, `require_internal`/`require_client`, workspace token budget,
      `CLIENT_SURFACE_ENABLED` kill switch, `client-workspaces` department grant (migrations
      0038/0039). 145 unit tests green incl. new tenancy regression suite; zero regressions in the
      full existing suite (verified against a throwaway venv — 554 passed / 13 pre-existing
      unrelated failures, same failures present before this work).
- ☑ 5.2 Provisioning + entry — `client_invites`, `/admin/clients` (+ admin UI at `/clients`),
      unauthenticated `/public/redeem`, `/try/<token>` frontend route (LINE-ready seam; LINE
      integration itself is a follow-on — invites are minted by hand for now)
- ☑ 5.3 Client workspace UI — deterministic 8-question intake, chat, research (Perplexity via
      `PolicyEngine`), case-library matching (`rag_search`), 3-column client shell
- ☑ 5.4 Plan as artifact — `plans`/`plan_versions`/`rate_card_items`, structured budget computed in
      Python (never model-emitted), plan document view
- ☑ 5.5 CTA → lead → expert inbox — `leads` table, n8n handoff, admin inbox at `/leads`
- ☑ 5.6 Export PDF (print stylesheet), share link (`/p/<token>`), read-only internal agent-config
      screen (`/clients/<id>`)
- ☑/☐ 5.7 Hardening — rate limiting on `/public/*` and `/client/*` **done** (in-process, no Redis
      needed — `app/services/rate_limit.py`), `CLIENT_SURFACE_ENABLED` checked on every write
      endpoint **done**. **Not done, needs a human:** prompt-injection pass against a live instance,
      secrets rotation (`JWT_SECRET`, `POSTGRES_PASSWORD`, the GitHub PAT in `VAULT_GIT_URL` —
      carried as an open item across prior `PROGRESS.md` entries).
- ☑ 5.8 Internal-app access for client seats (D23) — `CLIENT_INTERNAL_ACCESS_ENABLED` flag,
      default off; flag-aware `require_internal` + hard `require_staff`/`require_staff_principal`
      carve-out for `hermes`/`automations` (which also fixes automations' pre-existing 401 for n8n's
      `gw_…` key — it was gated with the JWT-only `require_internal` while its handlers authenticate
      via `get_principal`); flag-aware `workspace_visibility_filter` (shared pool readable by all
      tenants when on); `workspace_id` stamping + private-by-default writes (`scope`/`visibility`
      coerced to personal) for client seats on file upload, `create_skill`, `create_agent`;
      `require_admin` hardened against workspace-scoped users; three divergent copies of the
      quota-limit precedence unified into `quota.py::resolve_monthly_token_limit` (also fixes
      `GET /quota/me` silently pinning a client seat's monthly ceiling to the L1 role default);
      non-NULL default workspace caps in `create_workspace`; `internal_app_enabled` surfaced through
      `/auth/me` + `/client/bootstrap` for two-way navigation between `/w` and the internal shell.
      See `docs/adr/0001-client-seats-in-the-internal-app.md`.
- ☑ 5.9 Case-match offline eval harness — the "% match" shown on a case card was an unvalidated
      `1 - cosine_distance` number with no golden set, metric, or eval suite anywhere in the repo.
      Two production bugs fixed first (a measurement is worthless against a broken pipeline):
      preview-mode case matching returned zero results (`effective_workspace_id` override added to
      `rag_search.retrieve`/`_scope_filter` + `workspace_visibility_filter_by_workspace_id`, wired
      through `ClientContext.workspace_id`), and `CaseMatch` rows accumulated across repeated
      `/client/cases` calls, letting `plan.py`'s `ORDER BY score DESC LIMIT 3` pick stale/duplicate
      cases (now deleted-and-replaced per conversation). Extracted the matching pipeline out of the
      router into `app/services/case_match.py` (`match_cases`, `build_context_query`,
      `collapse_best_per_file`, `to_match_score`) so production and the harness share one code path.
      New `app/eval/` package (never imported by a request path): `metrics.py`
      (precision/recall/MRR/nDCG@k, Kendall tau — hand-computed unit tests), `calibration.py`
      (AUC + score distributions, to judge whether the % is signal or noise), `goldens.py` (loads/
      validates `backend/eval/case_match/profiles.json` — 14 synthetic personas — against
      `client_intake.INTAKE_SCRIPT`'s real chip values), `corpus.py` (DB-side corpus health +
      filename↔file_id resolution), `query_variants.py` (English-label vs. Thai-label vs.
      natural-Thai query builders — the corpus narrative is Thai, chip values are English),
      `report.py` (aggregation, worst-failures list, sensitivity/calibration rendering). Three CLI
      scripts (`backend/scripts/eval_case_match_{export,import,run}.py`): export a Thai labeling
      sheet + corpus manifest for a Brandbiz consultant to grade 0/1/2, import their filled sheet
      into a canonical `labels.csv`, and run retrieval in both "production settings" (what the
      client sees) and "deep pool" (uncapped — what the retriever could reach, since `rag_top_k` is
      a chunk budget, not a case budget) modes with a `--baseline` diff. Verified end-to-end against
      the live demo workspace's real 30-case corpus (14 profiles × 30 cases, 420 pairs); a
      `--top-k` sweep produces a real `--baseline` delta, confirming the instrument moves. Ground
      truth (`labels.csv`) awaits actual consultant labeling — everything else is unblocked without
      it (`--bootstrap-labels` placeholder proves the plumbing). 113 new/extended unit tests, zero
      regressions in the full existing suite (654 passed; 25 failed/21 errored are pre-existing
      host-env gaps — missing `ENCRYPTION_KEY` etc. — confirmed unrelated by reproducing them with
      the key set).

- ☑ 5.10 Client workspace redesign + plan NPS — reframes `/w`, `/w/plans`, `/w/plans/[id]` around
      the approved Claude Design mockup ("Brandbidd Workspace.dc.html"): a left nav rail showing
      four-chapter journey progress (Interview → Market scan → Case match → Plan & budget) and
      unlocked rewards, milestone cards in the chat thread, an "insight earned" callout tied to each
      intake answer (`insight` added to `INTAKE_SCRIPT`), locked Research/Cases work-panel tabs
      until their step has run, and a plan document with a provenance/versions rail plus a
      strategist-facing NPS rating (`plan_ratings` table, one row per plan+user, upserted;
      surfaced on the `/leads` admin inbox). Journey/progress state is derived in one pure function
      (`components/client/journey.ts`) rather than scattered ternaries. Login and the internal/admin
      mode screens in the mockup are out of scope. See the implementation plan filed for "Client
      workspace redesign (from the Claude Design mockup)" for full detail, including the mockup
      elements deliberately not built (fabricated KPI numbers, the client/internal mode switcher,
      the fake webhook trace line, invented provenance/version rows). Backend/frontend build clean,
      667 backend unit tests pass (27 failed/21 errored are pre-existing host-env gaps — bad
      `ENCRYPTION_KEY`, missing real LLM SDKs — same profile documented under 5.9, confirmed
      unrelated). New Postgres integration coverage for the rating's cross-tenant isolation and
      upsert behavior passes against the pytest-docker harness. One new integration test
      (`test_list_leads_surfaces_nps_score_for_a_rated_plan` in `test_admin.py`) could not be
      executed in this session — a local-`alembic/`-directory-vs-installed-package name collision
      in the ad-hoc verification venv breaks `app.main` import for every test in that file
      identically (pre-existing, not a regression); needs verification in the project's real
      dev/CI environment.

Seed script: `backend/scripts/seed_client_demo.py` provisions a demo workspace, agent, department
grant, and a placeholder rate card, and mints one invite — run it, then upload + attach sanitized
case studies by hand (file upload UI, then `/agent/<id>/edit`) before the event.

**Assumptions requiring business sign-off before the event:** the case-study and rate-card corpus
ingested for this feature must be a *sanitized* set, not real commercial rates — RAG will honor a
request to dump it verbatim. The plan's `draft · awaiting expert review` status is a liability
control, not decoration, and must not be removed from the UI.

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
- ~~❌ Multi-tenancy (single company only)~~ — superseded by D21/D22 (Phase 5). What's still out of
  scope: per-tenant deployments, per-tenant schemas/databases, tenant-configurable branding/billing,
  and tenant self-service admin. What's now in scope: workspace-scoped visibility for client seats
  within the single shared instance, per D22.
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

Separately tracked, not part of this plan's phases:

- `docs/gap-closure.md` — task list (`G-<area><n>`) for closing the 35 feature gaps found in the
  AskMe audit (`report.md`). Four of its tasks are blocked on amending Section 11 / D11.

---

*Last updated: 2026-05-25*
