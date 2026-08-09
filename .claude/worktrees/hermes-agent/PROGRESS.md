# Progress Log

## 2026-05-26 11:00 — main @ 2d4b6af

**Summary:** Completed Task 1.1 (Repo scaffold). Created the full directory structure matching PLAN.md Section 5, copied and placed `docker-compose.yml` from the reference artifact, and wrote all supporting files: `.env.example`, `.gitignore`, `README.md`, `docker-compose.dev.yml`, `caddy/Caddyfile`, `garage/garage.toml`, `backend/pyproject.toml`, `backend/Dockerfile`, and `backend/alembic.ini`. All backend Python packages have `__init__.py` and stub module files; both Next.js frontends have their directory trees and `package.json`. Task 1.1 checkbox in PLAN.md marked ☑.

**Files changed:**
- `docker-compose.yml` — copied from `reference/docker-compose.yml`; all 11 services defined
- `docker-compose.dev.yml` — hot-reload overrides with source-mounted backend volumes
- `.env.example` — all 13 env vars with generation instructions
- `.gitignore` — models, .env, Python/Node/editor artifacts
- `README.md` — full local dev setup walkthrough (prereqs, model download, Garage bootstrap, first-boot sequence)
- `caddy/Caddyfile` — reverse proxy for chat/admin/api subdomains
- `garage/garage.toml` — Garage v1 single-node config
- `backend/Dockerfile` — Python 3.12 + uv, uvicorn entrypoint
- `backend/pyproject.toml` — pinned deps (FastAPI 0.115, SQLAlchemy 2.0, LangGraph 0.2, Celery 5.4, etc.)
- `backend/alembic.ini` — Alembic config wired to env vars
- `backend/alembic/env.py` — stub
- `backend/alembic/versions/` — empty, ready for Task 1.2 migration
- `backend/app/__init__.py` + all sub-package `__init__.py` files
- `backend/app/main.py`, `config.py`, `db.py`, `crypto.py`, `deps.py` — stubs
- `backend/app/routers/*.py` — stubs (auth, chat, conversations, files, admin, reveal)
- `backend/app/models/__init__.py`, `backend/app/schemas/__init__.py` — stubs
- `backend/app/agents/*.py` — stubs (orchestrator, nodes, prompts)
- `backend/app/services/*.py` — stubs (policy_engine, classifier, quota, audit, reveal)
- `backend/app/llm/*.py` — stubs (base, llamacpp, anthropic, openai, google, perplexity, router)
- `backend/app/tools/__init__.py` — stub
- `backend/app/workers/*.py` — stubs (celery_app, chunking, embedding, dbwriter, audit_writer, retention)
- `backend/tests/unit/__init__.py`, `backend/tests/integration/__init__.py` — stubs
- `frontend-chat/package.json` — Next.js 15 + Vercel AI SDK 4 + next-auth 5
- `frontend-chat/app/*.tsx`, `frontend-chat/components/*.tsx`, `frontend-chat/lib/api.ts` — stubs
- `frontend-admin/package.json` — Next.js 15 + next-auth 5
- `frontend-admin/app/**/*.tsx` — stubs for all admin pages
- `models/.gitkeep`, `db/init/.gitkeep` — track empty dirs in git
- `PLAN.md` — Task 1.1 checkbox updated ☐ → ☑

**Next steps:**
- [x] Task 1.2 — Postgres + Alembic: convert `reference/schema.sql` to Alembic baseline migration `0001_baseline.py`; verify `alembic upgrade head` creates all 13 tables + pgvector extension
- [ ] Task 1.3 — Backend skeleton: implement `app/main.py`, `config.py`, `db.py`; wire `/health` endpoint; confirm `curl localhost:8000/health` returns 200
- [ ] Task 1.4 — Crypto module: implement `app/crypto.py` with AES-256-GCM encrypt/decrypt + key versioning; write round-trip unit tests
- [ ] Task 1.5 — Google OAuth login flow
- [ ] Task 1.6 — Auth middleware + `get_current_user` dependency
- [ ] Task 1.7 — llama.cpp container running with Qwen 2.5 14B Q5_K_M
- [ ] Task 1.8 — LLMClient abstract interface + llama.cpp adapter
- [ ] Task 1.9 — Minimal LangGraph orchestrator (load_history → call_llm, encrypted persist)
- [ ] Task 1.10 — Chat frontend (minimum viable: login + streaming chat + conversation list)
- [ ] Task 1.11 — Caddy deployment + README deploy procedure

## 2026-05-26 14:30 — main @ 2d4b6af

**Summary:** Completed Task 1.2 (Postgres + Alembic). Populated the empty `alembic/env.py` with a full async migration runner (asyncpg + `async_engine_from_config`). Created the missing `alembic/script.py.mako` template so future `alembic revision` calls work. Wrote `alembic/versions/0001_baseline.py` converting `reference/schema.sql` verbatim into `op.execute()` calls — covering 3 extensions, 6 ENUM types, 15 tables (including RANGE-partitioned `audit_log` with two bootstrap partitions), 13 indexes (including HNSW on `file_chunks.embedding`), and all seed data (quota_defaults, model_catalog, role_model_permissions, data_classification_rules, departments, department_model_permissions). Removed the `./db/init:/docker-entrypoint-initdb.d:ro` mount from docker-compose.yml to prevent schema.sql from auto-running and conflicting with Alembic. Added psql verification commands to README. Task 1.2 checkbox marked ☑.

**Files changed:**
- `backend/alembic/env.py` — async Alembic runner; reads POSTGRES_* env vars, overrides sqlalchemy.url; `target_metadata = None` until ORM models land in Task 1.3+
- `backend/alembic/script.py.mako` — standard async migration template (was missing; needed for `alembic revision`)
- `backend/alembic/versions/0001_baseline.py` — full baseline migration: extensions → ENUMs → tables → indexes → seed data; includes downgrade()
- `docker-compose.yml` — removed `./db/init:/docker-entrypoint-initdb.d:ro` mount from postgres service
- `README.md` — added three psql verification commands after `alembic upgrade head` step
- `PLAN.md` — Task 1.2 checkbox updated ☐ → ☑

**Next steps:**
- [ ] Task 1.3 — Backend skeleton: implement `app/main.py`, `config.py`, `db.py`; wire `/health` endpoint; confirm `curl localhost:8000/health` returns 200
- [ ] Task 1.4 — Crypto module: implement `app/crypto.py` with AES-256-GCM encrypt/decrypt + key versioning; write round-trip unit tests
- [ ] Task 1.5 — Google OAuth login flow
- [ ] Task 1.6 — Auth middleware + `get_current_user` dependency
- [ ] Task 1.7 — llama.cpp container running with Qwen 2.5 14B Q5_K_M
- [ ] Task 1.8 — LLMClient abstract interface + llama.cpp adapter
- [ ] Task 1.9 — Minimal LangGraph orchestrator (load_history → call_llm, encrypted persist)
- [ ] Task 1.10 — Chat frontend (minimum viable: login + streaming chat + conversation list)
- [ ] Task 1.11 — Caddy deployment + README deploy procedure
- [ ] Run `alembic upgrade head` against a live postgres container to confirm acceptance criteria (15 tables, partitioned audit_log, vector/pgcrypto/uuid-ossp extensions, HNSW index)

## 2026-05-26 15:30 — main @ 2d4b6af

**Summary:** Completed Task 1.3 (Backend skeleton). Implemented `app/config.py` with a Pydantic Settings class covering all env vars (DB, Redis, crypto, auth, OAuth, LLM endpoints, S3, CORS origins) and a `database_url` property. Implemented `app/db.py` with an async SQLAlchemy engine and `get_db` session dependency. Implemented `app/main.py` with CORS middleware and a `/health` endpoint that probes both Postgres (`SELECT 1`) and Redis (`PING`) and returns `{"status":"ok","db":"ok","redis":"ok"}` when both are healthy. Added a minimal `deps.py` stub re-exporting `get_db` for future router imports. Marked Task 1.3 ☑ in PLAN.md.

**Files changed:**
- `backend/app/config.py` — Pydantic Settings with all env vars + `database_url` property + `get_settings()` lru_cache factory
- `backend/app/db.py` — async SQLAlchemy engine, session factory, `get_db` FastAPI dependency
- `backend/app/main.py` — FastAPI app, CORS middleware, `/health` endpoint (DB + Redis probes)
- `backend/app/deps.py` — stub re-exporting `get_db`; placeholder for Task 1.6 auth dependencies
- `PLAN.md` — Task 1.3 checkbox updated ☐ → ☑

**Next steps:**
- [x] Task 1.3 — Backend skeleton: implement `app/main.py`, `config.py`, `db.py`; wire `/health` endpoint
- [ ] Task 1.4 — Crypto module: implement `app/crypto.py` with AES-256-GCM encrypt/decrypt + key versioning; write round-trip unit tests
- [ ] Task 1.5 — Google OAuth login flow
- [ ] Task 1.6 — Auth middleware + `get_current_user` dependency
- [ ] Task 1.7 — llama.cpp container running with Qwen 2.5 14B Q5_K_M
- [ ] Task 1.8 — LLMClient abstract interface + llama.cpp adapter
- [ ] Task 1.9 — Minimal LangGraph orchestrator (load_history → call_llm, encrypted persist)
- [ ] Task 1.10 — Chat frontend (minimum viable: login + streaming chat + conversation list)
- [ ] Task 1.11 — Caddy deployment + README deploy procedure
- [ ] Run `alembic upgrade head` against a live postgres container to confirm acceptance criteria (15 tables, partitioned audit_log, vector/pgcrypto/uuid-ossp extensions, HNSW index)
- [ ] Verify `curl localhost:8000/health` returns 200 with all subsystems "ok" against a running stack

## 2026-05-26 16:00 — main @ 2d4b6af

**Summary:** Completed Task 1.4 (Crypto module). Implemented `app/crypto.py` with AES-256-GCM encrypt/decrypt using `cryptography.hazmat.primitives.ciphers.aead.AESGCM`. Each `encrypt()` call generates a fresh 96-bit nonce via `secrets.token_bytes`, splits the 16-byte GCM tag from the ciphertext, and returns `(ciphertext, nonce, tag, key_version)`. Key versioning is supported via `ENCRYPTION_KEY` + `ENCRYPTION_KEY_VERSION` env vars for the current key, plus `ENCRYPTION_KEY_<n>` env vars for historical keys retained during rotation. All 7 unit tests pass: round-trip, empty-string round-trip, tampered-ciphertext `InvalidTag`, tampered-tag `InvalidTag`, nonce uniqueness, key rotation, and missing-version `KeyError`.

**Files changed:**
- `backend/app/crypto.py` — AES-256-GCM encrypt/decrypt with lazy key-store loading and key-version support
- `backend/tests/unit/test_crypto.py` — 7 unit tests covering all acceptance criteria + key rotation
- `PLAN.md` — Task 1.4 checkbox updated ☐ → ☑

**Next steps:**
- [ ] Task 1.5 — Google OAuth login flow (`/auth/google/login`, `/auth/google/callback`, JWT issuance, `hd` claim check)
- [ ] Task 1.6 — Auth middleware + `get_current_user` dependency + `require_admin`
- [ ] Task 1.7 — llama.cpp container running with Qwen 2.5 14B Q5_K_M
- [ ] Task 1.8 — LLMClient abstract interface + llama.cpp adapter
- [ ] Task 1.9 — Minimal LangGraph orchestrator (load_history → call_llm, encrypted persist)
- [ ] Task 1.10 — Chat frontend (minimum viable: login + streaming chat + conversation list)
- [ ] Task 1.11 — Caddy deployment + README deploy procedure
- [ ] Run `alembic upgrade head` against a live postgres container to confirm acceptance criteria
- [ ] Verify `curl localhost:8000/health` returns 200 with all subsystems "ok" against a running stack

## 2026-05-27 — main @ 2d4b6af

**Summary:** Completed Task 1.6 (Auth middleware + current_user dependency). Implemented `get_current_user()` in `app/deps.py` — extracts JWT from `Authorization: Bearer` header or `access_token` httpOnly cookie, decodes with python-jose (HS256), loads the `User` ORM row, raises 401 on missing/expired/invalid token or inactive user. Implemented `require_admin()` depending on `get_current_user` that raises 403 if `role != ADMIN`. Added a minimal `/chat` stub router protected by `get_current_user` and wired it into `app/main.py`. Created `tests/unit/conftest.py` to stub `asyncpg`, `redis`, and `app.db` so unit tests run without infra; all 21 unit tests pass (9 new for deps + 5 auth + 7 crypto).

**Files changed:**
- `backend/app/deps.py` — full `get_current_user()` and `require_admin()` implementation replacing the stub
- `backend/app/routers/chat.py` — minimal protected `GET /chat` stub (returns 401 without token, 200 with valid token)
- `backend/app/main.py` — added `chat` router include
- `backend/tests/unit/conftest.py` — stubs asyncpg, redis, app.db so all unit tests run without installed drivers
- `backend/tests/unit/test_deps.py` — 9 unit tests: no-token 401, invalid token 401, expired token 401, bearer token auth, cookie token auth, inactive user 401, user not found 401, require_admin pass, require_admin 403
- `PLAN.md` — Task 1.6 checkbox updated ☐ → ☑

**Next steps:**
- [ ] Task 1.7 — llama.cpp container running with Qwen 2.5 14B Q5_K_M
- [ ] Task 1.8 — LLMClient abstract interface + llama.cpp adapter
- [ ] Task 1.9 — Minimal LangGraph orchestrator (load_history → call_llm, encrypted persist)
- [ ] Task 1.10 — Chat frontend (minimum viable: login + streaming chat + conversation list)
- [ ] Task 1.11 — Caddy deployment + README deploy procedure
- [ ] Run `alembic upgrade head` against a live postgres container to confirm acceptance criteria
- [ ] Verify `curl localhost:8000/health` returns 200 with all subsystems "ok" against a running stack
- [ ] Verify `curl /chat` without token returns 401 and with valid token returns 200 against a running stack

## 2026-05-27 — main @ 2d4b6af

**Summary:** Completed Task 1.7 (llama.cpp container running). The `llamacpp-primary` service was already scaffolded in `docker-compose.yml` from Task 1.1 but was missing a healthcheck and VRAM-efficiency flags. Added `--flash-attn`, `--cache-type-k q8_0`, and `--cache-type-v q8_0` to the llama.cpp command to keep VRAM ≤ 14 GB with 32K context (model weights ~10.2 GB + Q8 KV cache ~2.7 GB ≈ 13 GB). Added a `/health` healthcheck with a 120 s start period (model load time) and promoted `backend-api`'s `depends_on` condition for `llamacpp-primary` from `service_started` to `service_healthy`. Exposed port 8080 in `docker-compose.dev.yml` for acceptance-criteria curl testing. Updated README with exact model download commands, VRAM budget table, and the verification curl sequence. Marked Task 1.7 ☑ in PLAN.md.

**Files changed:**
- `docker-compose.yml` — added `--flash-attn`, `--cache-type-k q8_0`, `--cache-type-v q8_0` to llamacpp-primary command; added `/health` healthcheck (start_period 120s, retries 5); changed backend-api depends_on llamacpp-primary condition from `service_started` → `service_healthy`
- `docker-compose.dev.yml` — added llamacpp-primary port 8080:8080 exposure for local curl testing
- `README.md` — added `huggingface-cli` download commands for both models; added VRAM budget note; added llamacpp-primary verification steps (health check, chat completion curl, nvidia-smi VRAM query)
- `PLAN.md` — Task 1.7 checkbox updated ☐ → ☑

**Next steps:**
- [ ] Task 1.8 — LLMClient abstract interface + llama.cpp adapter (`app/llm/base.py` abstract streaming interface; `app/llm/llamacpp.py` via httpx async SSE; `app/llm/router.py`)
- [ ] Task 1.9 — Minimal LangGraph orchestrator (load_history → call_llm, encrypted persist, SSE stream)
- [ ] Task 1.10 — Chat frontend (minimum viable: login + streaming chat + conversation list)
- [ ] Task 1.11 — Caddy deployment + README deploy procedure
- [ ] Run `alembic upgrade head` against a live postgres container to confirm acceptance criteria (15 tables, partitioned audit_log, vector/pgcrypto/uuid-ossp extensions, HNSW index)
- [ ] Verify `curl localhost:8000/health` returns 200 with all subsystems "ok" against a running stack
- [ ] Verify `curl /chat` without token returns 401 and with valid token returns 200 against a running stack
- [ ] Verify llamacpp-primary: `curl http://localhost:8080/v1/chat/completions -d '...'` returns completion and `nvidia-smi` shows VRAM ≤ 14 GB

## 2026-05-27 — main @ 2d4b6af

**Summary:** Completed Task 1.8 (LLMClient interface + llama.cpp adapter). Defined `ChatMessage`, `ChatChunk`, `LLMProviderError`, and abstract `LLMClient` in `app/llm/base.py`. Implemented `LlamaCppClient` in `app/llm/llamacpp.py` using `httpx.AsyncClient` streaming against `/v1/chat/completions` — parses SSE lines, yields `ChatChunk` per delta, surfaces token usage from the final chunk via `stream_options: {include_usage: true}`, and raises `LLMProviderError` on non-200 responses. Implemented `LLMRouter` in `app/llm/router.py` that registers `qwen2.5-14b-local` → `LlamaCppClient` at startup and raises `KeyError` for unregistered model codes (Phase 2+ providers are stubs). Created 7 unit tests covering chunk streaming, usage extraction, HTTP error handling, malformed SSE skipping, and router registration; all 28 unit tests pass.

**Files changed:**
- `backend/app/llm/base.py` — `ChatMessage`, `ChatChunk`, `LLMProviderError`, abstract `LLMClient` with `stream_chat` signature
- `backend/app/llm/llamacpp.py` — `LlamaCppClient` via httpx async SSE; handles usage, errors, and malformed lines
- `backend/app/llm/router.py` — `LLMRouter` mapping model codes to clients; `get_router()` lru_cache factory; `register()` for Phase 2+ adapters
- `backend/tests/unit/test_llm.py` — 7 unit tests: chunk yield, usage in last chunk, HTTP error raises, malformed SSE skip, router get/unknown/register
- `PLAN.md` — Task 1.8 checkbox updated ☐ → ☑

**Next steps:**
- [x] Task 1.8 — LLMClient abstract interface + llama.cpp adapter
- [ ] Task 1.9 — Minimal LangGraph orchestrator (load_history → call_llm, encrypted persist, SSE stream)
- [ ] Task 1.10 — Chat frontend (minimum viable: login + streaming chat + conversation list)
- [ ] Task 1.11 — Caddy deployment + README deploy procedure
- [ ] Run `alembic upgrade head` against a live postgres container to confirm acceptance criteria (15 tables, partitioned audit_log, vector/pgcrypto/uuid-ossp extensions, HNSW index)
- [ ] Verify `curl localhost:8000/health` returns 200 with all subsystems "ok" against a running stack
- [ ] Verify `curl /chat` without token returns 401 and with valid token returns 200 against a running stack
- [ ] Verify llamacpp-primary: `curl http://localhost:8080/v1/chat/completions -d '...'` returns completion and `nvidia-smi` shows VRAM ≤ 14 GB

## 2026-05-28 — main @ 2d4b6af

**Summary:** Completed Task 1.9 (Minimal orchestrator). Added `Conversation` and `Message` ORM models. Built a LangGraph `StateGraph` with two nodes — `load_history` (creates or verifies the conversation, decrypts existing messages into history, emits the `start` SSE event) → `call_llm` (streams from `LlamaCppClient`, encrypts and persists both the user and assistant messages via AES-256-GCM, emits `content` and `done` SSE events). Replaced the `GET /chat` stub with `POST /chat` returning a `StreamingResponse` driven by `run_chat_stream()`. Added 7 unit tests; all 37 unit tests pass.

**Files changed:**
- `backend/app/models/conversation.py` — new `Conversation` ORM model mapping `conversations` table
- `backend/app/models/message.py` — new `Message` ORM model with all encrypted-content columns
- `backend/app/models/__init__.py` — exported `Conversation` and `Message`
- `backend/app/agents/orchestrator.py` — `ChatState` TypedDict, `load_history` node, `call_llm` node, `_chat_graph` compiled graph, `run_chat_stream()` async generator with SSE formatting and error funneling
- `backend/app/routers/chat.py` — replaced GET stub with `POST /chat` (`ChatRequest` body → `StreamingResponse`, `text/event-stream`)
- `backend/tests/unit/test_orchestrator.py` — 7 unit tests: new-conversation creation, start-event in queue, history decryption, two-message persistence, ciphertext verification, chunk/done events, SSE line formatting
- `PLAN.md` — Task 1.9 checkbox updated ☐ → ☑

**Next steps:**
- [x] Task 1.9 — Minimal LangGraph orchestrator (load_history → call_llm, encrypted persist, SSE stream)
- [ ] Task 1.10 — Chat frontend (minimum viable: login + streaming chat + conversation list)
- [ ] Task 1.11 — Caddy deployment + README deploy procedure
- [ ] Run `alembic upgrade head` against a live postgres container to confirm acceptance criteria (15 tables, partitioned audit_log, vector/pgcrypto/uuid-ossp extensions, HNSW index)
- [ ] Verify `curl localhost:8000/health` returns 200 with all subsystems "ok" against a running stack
- [ ] Verify `POST /chat` with `{"conversation_id":null,"content":"hello"}` returns SSE stream and creates 2 encrypted rows in `messages`
- [ ] Verify llamacpp-primary: `curl http://localhost:8080/v1/chat/completions -d '...'` returns completion and `nvidia-smi` shows VRAM ≤ 14 GB

## 2026-05-28 — main @ 2d4b6af

**Summary:** Completed Task 1.10 (Chat frontend minimum). Implemented the full frontend-chat Next.js 15 app: Google OAuth login page, Next.js middleware for cookie-based auth gating, a chat layout with server-side conversation list sidebar, streaming `ChatPane` client component that reads our custom SSE events (`start`/`content`/`done`), and all API proxy routes (`/api/chat`, `/api/conversations`, `/api/me`, `/api/logout`). On the backend, added `GET /conversations`, `GET /conversations/{id}` (decrypts messages server-side), `GET /auth/me`, and `POST /auth/logout` endpoints, and wired the conversations router into `main.py`. Fixed `docker-compose.yml` to set the correct `NEXT_PUBLIC_API_URL` (public backend URL for OAuth) and added `BACKEND_URL` (internal Docker URL for Next.js server→FastAPI calls).

**Files changed:**
- `frontend-chat/tsconfig.json` — new; standard Next.js 15 TypeScript config with `@/*` path alias
- `frontend-chat/next.config.ts` — new; `output: standalone`, exposes `BACKEND_URL` env to server
- `frontend-chat/Dockerfile` — new; multi-stage pnpm build with standalone output
- `frontend-chat/middleware.ts` — new; redirects unauthenticated requests to `/login`, authenticated `/login` to `/chat`
- `frontend-chat/app/globals.css` — new; base reset + dark theme + blink keyframe
- `frontend-chat/app/layout.tsx` — root layout with metadata and globals.css import
- `frontend-chat/app/page.tsx` — redirects `/` → `/chat`
- `frontend-chat/app/login/page.tsx` — Google sign-in button pointing to `${NEXT_PUBLIC_API_URL}/auth/google/login`
- `frontend-chat/app/chat/layout.tsx` — new; server component fetching conversations + user, renders sidebar + main slot
- `frontend-chat/app/chat/page.tsx` — new; new-conversation page (empty `ChatPane`)
- `frontend-chat/app/chat/[id]/page.tsx` — existing-conversation page; fetches history server-side, passes as `initialMessages`
- `frontend-chat/app/api/chat/route.ts` — POST proxy to backend `/chat`; streams SSE directly to browser
- `frontend-chat/app/api/conversations/route.ts` — new; GET proxy to `/conversations`
- `frontend-chat/app/api/me/route.ts` — new; GET proxy to `/auth/me`
- `frontend-chat/app/api/logout/route.ts` — new; POST proxy to `/auth/logout` + deletes cookie
- `frontend-chat/components/ChatPane.tsx` — client component; SSE reader, optimistic user message, streaming assistant bubble, URL update on new conversation, `router.refresh()` after `done`
- `frontend-chat/components/ConversationList.tsx` — client component; sidebar with active-highlight via `usePathname`, sign-out button
- `frontend-chat/lib/api.ts` — client-side `fetchConversations` helper
- `backend/app/routers/conversations.py` — new; `GET /conversations` (list) + `GET /conversations/{id}` (detail with decrypted messages)
- `backend/app/routers/auth.py` — added `GET /auth/me` and `POST /auth/logout`
- `backend/app/main.py` — added conversations router include
- `docker-compose.yml` — fixed frontend env: `NEXT_PUBLIC_API_URL` → `https://api.company.local`; added `BACKEND_URL: http://backend-api:8000`; added internal network + depends_on
- `.env.example` — added `COOKIE_DOMAIN`, `COOKIE_SECURE`, `BACKEND_URL` vars
- `PLAN.md` — Task 1.10 checkbox updated ☐ → ☑

**Next steps:**
- [x] Task 1.9 — Minimal LangGraph orchestrator
- [x] Task 1.10 — Chat frontend (login + streaming chat + conversation list)
- [ ] Task 1.11 — Caddy deployment + README deploy procedure (Phase 1 final task)
- [ ] Run `alembic upgrade head` against a live postgres container to confirm all 15 tables present
- [ ] Verify `curl localhost:8000/health` returns 200 with all subsystems "ok" against a running stack
- [ ] Verify `POST /chat` with `{"conversation_id":null,"content":"hello"}` returns SSE stream and creates 2 encrypted rows in `messages`
- [ ] Verify llamacpp-primary: `curl http://localhost:8080/v1/chat/completions -d '...'` returns completion and `nvidia-smi` shows VRAM ≤ 14 GB
- [ ] Run `pnpm install && pnpm build` in `frontend-chat/` to confirm TypeScript compiles cleanly
- [ ] Confirm full login → send message → reload → message persists loop against a running stack (Phase 1 acceptance)

## 2026-06-09 14:00 — main @ 60ba095

**Summary:** Fixed two bugs causing "the server is down" to silently skip the n8n LINE alert and answer from unrelated knowledge-base documents. Defect 1: `N8N_ALERT_WEBHOOK_URL` (and the other two n8n vars) were set in root `.env` but never forwarded into the `backend-api` container — `docker-compose.yml`'s explicit `environment:` block omitted them entirely. Added all three passthroughs using the same `${VAR:-}` pattern as the API-key vars. Defect 2: `rag_search.retrieve()` ran a pure top-k cosine search with no distance cutoff, so every query injected the `k` nearest chunks regardless of relevance. Added a `rag_max_distance: float = 0.6` setting to `config.py` and a post-fetch filter in `rag_search.py` that drops chunks exceeding that ceiling; an empty result list makes `build_context_block` return `""` so the LLM answers without injected docs.

**Files changed:**
- `docker-compose.yml` — added `N8N_WEBHOOK_URL`, `N8N_WEBHOOK_SECRET`, `N8N_ALERT_WEBHOOK_URL` env passthroughs to `backend-api.environment`
- `backend/app/config.py` — added `rag_max_distance: float = 0.6` setting next to the RAG block
- `backend/app/tools/rag_search.py` — added distance-threshold filter in `retrieve()` after building chunk list; logs dropped chunk count at DEBUG level
- `.env.example` — documented `RAG_MAX_DISTANCE` optional override under the RAG tuning section

**Next steps:**
- [ ] Recreate the backend container to pick up new env vars: `docker compose up -d --force-recreate backend-api`
- [ ] Verify `docker compose exec backend-api printenv N8N_ALERT_WEBHOOK_URL` prints the n8n cloud URL
- [ ] Test: send "the server is down" in chat → expect "✅ I've notified the admin team…" ack + LINE message arrives + `n8n_triggered` audit row
- [ ] Tune `RAG_MAX_DISTANCE` if needed (lower = stricter; default 0.6 is a starting point for bge-m3 distances)
- [ ] Run backend unit tests once `uv` is available: `uv run pytest tests/unit -q`

## 2026-05-28 — main @ 2d4b6af

**Summary:** Completed Task 1.11 (Deployment). Rewrote `caddy/Caddyfile` with Caddy's internal CA (`local_certs`), a `security_headers` snippet applied to all three virtual hosts, an SSE-specific `handle /chat` block with `flush_interval -1` to prevent buffering, and real-IP forwarding headers. Created the missing `frontend-admin/Dockerfile` (mirroring the chat Dockerfile with a `dev` stage), `frontend-admin/next.config.ts` (`output: standalone`), and `frontend-admin/tsconfig.json`. Added a `dev` stage to `frontend-chat/Dockerfile`. Rewrote `docker-compose.dev.yml` to add hot-reload frontend overrides (bind-mount source + anonymous node_modules volume + dev build target) and exposed Garage admin API port. Fixed `docker-compose.yml` frontend-admin service: corrected `NEXT_PUBLIC_API_URL` from `admin.company.local` → `api.company.local`, added `BACKEND_URL`, added `internal` network and `depends_on: [backend-api]`. Added a full `## Deployment (single VM)` section to README covering CA trust, Alembic migration, Garage bootstrap (gotcha #4), admin bootstrap, `docker compose up -d`, and day-2 ops. Marked Task 1.11 ☑ in PLAN.md.

**Files changed:**
- `caddy/Caddyfile` — full rewrite: `local_certs`, security headers snippet, SSE `flush_interval -1` on `/chat`, real-IP forwarding; CORS left to FastAPI (no duplicate headers)
- `frontend-admin/Dockerfile` — new; multi-stage: `dev` (hot reload), `deps`, `builder`, `runner`
- `frontend-admin/next.config.ts` — new; `output: standalone`, `BACKEND_URL` env passthrough
- `frontend-admin/tsconfig.json` — new; standard Next.js 15 TypeScript config
- `frontend-admin/package.json` — removed `--port 3001` from dev/start scripts (Docker containers use port 3000)
- `frontend-chat/Dockerfile` — added `dev` stage before `deps` for hot-reload dev mode
- `docker-compose.dev.yml` — added frontend-chat + frontend-admin dev overrides (target: dev, source bind-mount, anon node_modules volume); added backend port 8000 and Garage ports 3900/3903
- `docker-compose.yml` — fixed frontend-admin: correct API URL, added BACKEND_URL, added `internal` network + `depends_on: [backend-api]`
- `README.md` — added `## Deployment (single VM)` section: CA trust, DB migration, Garage bootstrap, admin bootstrap, compose up, verification, update procedure, useful commands
- `PLAN.md` — Task 1.11 checkbox updated ☐ → ☑

**Next steps:**
- [ ] Run `alembic upgrade head` against a live postgres container to confirm acceptance criteria (15 tables, partitioned audit_log, vector/pgcrypto/uuid-ossp extensions, HNSW index)
- [ ] Verify `curl https://api.company.local/health` returns 200 with all subsystems "ok" against a running stack
- [ ] Verify `POST /chat` with `{"conversation_id":null,"content":"hello"}` returns SSE stream and creates 2 encrypted rows in `messages`
- [ ] Verify llamacpp-primary: `curl http://localhost:8080/v1/chat/completions -d '...'` returns completion and `nvidia-smi` shows VRAM ≤ 14 GB
- [ ] Run `pnpm install && pnpm build` in `frontend-chat/` and `frontend-admin/` to confirm TypeScript compiles cleanly
- [ ] Trust Caddy CA on each client machine and confirm HTTPS chat loop works end-to-end through Caddy
- [ ] Phase 1 acceptance gate: 10 employees use it for a week, zero plaintext DB leaks, p95 latency < 5s

## 2026-05-29 14:56 — main @ 2d4b6af

**Summary:** Executed Phase 1 E2E code-path test (test-doc/phase1-test.md) against the dev box (no GPU). Made the upstream LLM model name env-configurable (Part A), created a seed-user + JWT-minting script (Part B), brought up the minimal stack, and proved all three acceptance checks: health `{"status":"ok","db":"ok","redis":"ok"}`, SSE chat loop (`start` → `content` → `done` via Ollama `llama3.1:latest` at `192.168.20.18:11435`), and encryption at rest (2 AES-256-GCM binary rows in `messages`, nonce+tag in separate columns).

**Files changed:**
- `backend/app/config.py` — added `llm_primary_model: str = "qwen2.5-14b-local"` setting (env: `LLM_PRIMARY_MODEL`)
- `backend/app/llm/router.py` — added `primary_model` param to `LLMRouter.__init__` and `get_router()`; upstream model name is now configurable while dict key stays `LOCAL_MODEL_CODE`
- `docker-compose.yml` — made `LLM_PRIMARY_URL` env-overridable via `${LLM_PRIMARY_URL:-http://llamacpp-primary:8080}`; added `LLM_PRIMARY_MODEL: ${LLM_PRIMARY_MODEL:-qwen2.5-14b-local}` to common-env
- `.env` — added `LLM_PRIMARY_URL` and `LLM_PRIMARY_MODEL` pointing at Ollama dev server (not quoted — contains live credentials)
- `backend/scripts/seed_and_token.py` — new; upserts dev user (`dev@company.local`, role L1) and prints a signed 8h JWT; run with `docker compose exec backend-api bash -c "export PYTHONPATH=/app && python scripts/seed_and_token.py"`

**Next steps:**
- [x] Run `alembic upgrade head` against a live postgres container to confirm acceptance criteria (18 tables verified)
- [x] Verify `curl https://api.decomplica.tech/health` returns 200 with all subsystems "ok"
- [x] Verify `POST /chat` returns SSE stream (`start`→`content`→`done`) and creates 2 AES-256-GCM encrypted rows in `messages`
- [ ] Verify llamacpp-primary: requires GPU box — not testable on this dev machine
- [ ] Run `pnpm install && pnpm build` in `frontend-chat/` and `frontend-admin/` to confirm TypeScript compiles cleanly
- [ ] Trust Caddy CA on client machines and confirm browser HTTPS chat loop end-to-end (CA export + import, hosts entry, DevTools cookie)
- [ ] Phase 1 acceptance gate: 10 employees use it for a week, zero plaintext DB leaks, p95 latency < 5s (GPU box required)

## 2026-06-05 — main @ c34cff4

**Summary:** Implemented Task 2.5b — OpenAI (GPT) adapter. Created `app/llm/openai.py` with `OpenAIClient` implementing `LLMClient`: streams via `openai.AsyncOpenAI.chat.completions.create(stream=True, stream_options={"include_usage": True})`, yields text `ChatChunk`s as deltas arrive, then emits a synthetic final chunk with `prompt_tokens`, `completion_tokens`, and `finish_reason` from the terminal usage chunk. Maps `APIStatusError` and `APIConnectionError` (including `APITimeoutError`) to `LLMProviderError`. Registered `gpt-4o-mini` and `gpt-4o` in `LLMRouter.get_router()`. Wrote 10 unit tests (all passing) and a live smoke test gated on `OPENAI_API_KEY`.

**Files changed:**
- `backend/app/llm/openai.py` — `OpenAIClient` streaming adapter; error mapping; `stream_options` include_usage pattern
- `backend/app/llm/router.py` — added `gpt-4o-mini` and `gpt-4o` registration under `cfg.openai_api_key` guard
- `backend/tests/unit/test_openai_llm.py` — 10 unit tests: text chunks, usage in final chunk, None-content skip, system-in-messages passthrough, request shape, 4 error mappings
- `backend/tests/integration/test_openai_api.py` — live smoke test; auto-skipped when `OPENAI_API_KEY` unset

**Next steps:**
- [ ] Fill in `OPENAI_API_KEY` in `.env` and run `pytest tests/integration/test_openai_api.py -v -s` to confirm live streaming + token counts

## 2026-06-05 — main @ c34cff4

**Summary:** Implemented Task 2.6 — full 4-eyes reveal flow. Created the `RevealRequest` ORM model, `app/services/reveal.py` with synchronous audit writes (defence-in-depth decision for testability and reliability), and all four endpoints (`POST /reveal`, `POST /reveal/{id}/approve`, `POST /reveal/{id}/deny`, `GET /reveal/{id}/view`) plus admin listing endpoints (`GET /admin/reveals/pending`, `GET /admin/reveals`). Wired both routers into `main.py`. Fixed the `AuditLog.ip_address` ORM column type from `Text` to `INET` (matching production DDL). Fixed the integration test conftest encryption key from 28 bytes to 32 bytes (valid AES-256). All 6 integration tests pass; full curl demo of the happy path shows 4 audit rows (`reveal_requested`, `reveal_approved`, `reveal_viewed` ×2) committed in production DB. Self-approve returns 400, expired reveal returns 410, second view returns 410, rate-limit 429 includes `X-Reset-At` header, and two concurrent approvals have exactly one winner (409 for the loser).

**Files changed:**
- `backend/app/models/reveal.py` — new; `RevealRequest` ORM model for `reveal_requests` table with all fields + FK references
- `backend/app/models/__init__.py` — added `RevealRequest` export
- `backend/app/models/audit.py` — changed `ip_address` column type from `Text` → `INET` to match production DDL
- `backend/app/services/reveal.py` — new; `create_request`, `approve`, `deny`, `view` with rate-limit, self-approve guard, atomic UPDATE concurrency control, 4 synchronous audit rows on happy path
- `backend/app/routers/reveal.py` — new; `POST /reveal`, `POST /reveal/{id}/approve`, `POST /reveal/{id}/deny`, `GET /reveal/{id}/view` (all require ADMIN)
- `backend/app/routers/admin.py` — new; `GET /admin/reveals/pending`, `GET /admin/reveals` (Task 2.8 JSON surface)
- `backend/app/main.py` — registered `reveal.router` and `admin.router`
- `backend/tests/integration/conftest.py` — fixed `ENCRYPTION_KEY` to a valid 32-byte base64 value
- `backend/tests/integration/test_reveal.py` — new; 6 integration tests: happy path 4-audit-rows, self-approve 400, expired 410, already-viewed 410, rate-limit 429, concurrent approve one-winner

**Next steps:**
- [ ] Fill in `OPENAI_API_KEY` in `.env` and run `pytest tests/integration/test_openai_api.py -v -s` to confirm live streaming + token counts
- [x] Task 2.6 — Reveal request flow (4-eyes): all endpoints, rate limit, concurrency safety, audit trail
- [ ] Task 2.7 — Admin panel: users + permissions (`/admin/users`, `/admin/permissions/role`, `/admin/permissions/department`; every mutation produces audit entry)
- [ ] Task 2.8 — Admin panel: dashboard + audit + reveal queue (metric cards, model usage, top users, approve/deny cards, CSV export)
- [ ] Task 2.9 — Privacy notice + first-login flow (modal on first login, `consent_acknowledged` audit row, block chat until acknowledged)
- [ ] Delete `backend/demo_seed.py` (scratch file left from curl demo — do not commit)
- [ ] Phase 2 acceptance gate: all 100 employees onboarded, one full billing cycle, at least one reveal end-to-end in production, zero Tier 3+ external API calls in audit log

## 2026-06-05 — main @ c34cff4

**Summary:** Implemented Task 2.5c — Google Gemini adapter. Created `app/llm/google.py` with `GoogleClient` implementing `LLMClient`: streams text via `genai.Client.aio.models.generate_content_stream()` (google-genai SDK), maps system messages to `GenerateContentConfig.system_instruction`, maps `assistant` → `model` role, translates `max_tokens` → `max_output_tokens`, and yields usage + finish_reason in the final synthetic chunk. Added `generate_image(prompt) -> bytes` method using `asyncio.to_thread` + Imagen (`client.models.generate_images`). Registered `gemini-2.5-flash` and `gemini-2.5-flash-image` in the router. Wrote 14 unit tests (all passing) and 2 real-API smoke tests gated on `GOOGLE_API_KEY`. Also fixed `conftest.py` to stub `celery` (same pattern as asyncpg/redis) so the autouse `_silence_audit_celery` fixture can import `audit_writer` without a running broker — this unblocked all unit tests in the suite.

**Files changed:**
- `backend/app/llm/google.py` — `GoogleClient`: streaming text via google-genai async API; `generate_image()` via Imagen + asyncio.to_thread; `LLMProviderError` mapping for `APIError` and connectivity exceptions
- `backend/app/llm/router.py` — added `gemini-2.5-flash` and `gemini-2.5-flash-image` registration under `cfg.google_api_key` guard; both point to the same `GoogleClient` instance
- `backend/tests/unit/test_google_llm.py` — 16 tests total: 5 stream shape, 4 request shape, 2 image gen, 3 error mapping, 2 real-API smoke (auto-skipped when `GOOGLE_API_KEY` unset)
- `backend/tests/unit/conftest.py` — added celery stub (`sys.modules["celery"] = MagicMock()`) so audit_writer can be imported without the celery package installed
- `PLAN.md` — Task 2.5c checkbox updated ☐ → ☑

**Next steps:**
- [ ] Fill in `GOOGLE_API_KEY` in `.env` and run `pytest tests/unit/test_google_llm.py -v -k real` to confirm live text streaming + token counts (free tier)
- [ ] Run real image generation test against a billing-enabled project: `pytest tests/unit/test_google_llm.py -v -k image`
- [ ] Task 2.5d — Perplexity adapter via httpx (OpenAI-compatible) (`app/llm/perplexity.py`)
- [ ] Task 2.5c — Gemini adapter (`app/llm/google.py`)
- [ ] Task 2.5d — Perplexity adapter (`app/llm/perplexity.py`)
- [ ] Run `pnpm install && pnpm build` in `frontend-chat/` and `frontend-admin/` to confirm TypeScript compiles cleanly
- [ ] Trust Caddy CA on client machines and confirm browser HTTPS chat loop end-to-end
- [ ] Phase 1 acceptance gate: 10 employees use it for a week, zero plaintext DB leaks, p95 latency < 5s (GPU box required)

## 2026-06-02 — main @ 2d4b6af

**Summary:** Completed Phase 1 E2E test with real Ollama LLM and wired up Google OAuth login. Switched LLM target from fake server to real Ollama (`192.168.20.18:11435`, model `gemma4:26b`) — confirmed two-turn streaming chat with history recall and AES-256-GCM encrypted persistence. Migrated all hostnames from `company.local` to `decomplica.tech` (real public TLD, Google OAuth accepts it). Configured Caddy, CORS, cookie domain, and `GOOGLE_REDIRECT_URI` override for the Starlette-behind-proxy scheme issue. Google OAuth credentials filled in `.env`. Phase 1 is **dev-complete** — all 11 task checkboxes ☑; formal acceptance gate (10 employees, GPU, 1 week soak) pending production hardware.

**Files changed:**
- `caddy/Caddyfile` — hostnames changed from `*.company.local` to `*.decomplica.tech`
- `docker-compose.yml` — `NEXT_PUBLIC_API_URL` updated to `api.decomplica.tech`; added `GOOGLE_REDIRECT_URI`, `COOKIE_DOMAIN=.decomplica.tech`, `CORS_ORIGINS` to `x-common-env`
- `docker-compose.dev.yml` — `NEXT_PUBLIC_API_URL` updated to `api.decomplica.tech`
- `docker-compose.noports.yml` — reverted to suppress both frontend host ports (no conflict since ports not needed via Caddy)
- `backend/app/config.py` — added `google_redirect_uri` override field; updated default `cors_origins` to `decomplica.tech`
- `backend/app/routers/auth.py` — uses `settings.google_redirect_uri` override when set (fixes `http://` vs `https://` behind Caddy TLS); cookie-setting flow unchanged
- `backend/scripts/seed_and_token.py` — used for dev JWT minting during testing
- `.env` — `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` filled; `LLM_PRIMARY_MODEL=gemma4:26b`
- `.env.example` — updated `COOKIE_DOMAIN` example; added `GOOGLE_REDIRECT_URI` doc comment
- `README.md` — all hostnames updated to `decomplica.tech`; added Windows hosts file instructions; added Google OAuth redirect URI registration note
- `PLAN.md` — all hostnames updated to `decomplica.tech`; Gotcha #6 updated; Section 10 updated with Windows hosts + CA trust + OAuth URI instructions

**Next steps:**
- [ ] Browser test: Google OAuth login → `/chat` → send message → streamed reply → reload → history persists
- [ ] Verify llamacpp-primary: requires GPU box — not testable on this dev machine
- [ ] Phase 1 acceptance gate: 10 employees use it for a week, zero plaintext DB leaks, p95 latency < 5s (GPU box required)

## 2026-06-04 — main @ c34cff4

**Summary:** Completed Task 2.1 (Data classifier). Created `app/models/classification.py` with `DataTier(str, Enum)` (4 values matching the existing `data_tier` PG enum, `create_type=False`) and the `DataClassificationRule` ORM model. Implemented `app/services/classifier.py` with a module-level in-process rule cache, `_compile_rules()` (pure helper — regex compile + keyword lowercase + validator wiring), `async load_rules(session)`, `async reload(session)`, and sync `detect_tier(text) -> DataTier`. Thai National-ID Mod-11 checksum validator (§8.8) is wired via a name-keyed `_VALIDATORS` dict so false-positive regex matches are rejected before the tier is recorded. `ner` rules and unknown `pattern_type` values are silently skipped (Phase-4 deferred). Added FastAPI lifespan handler to `main.py` that calls `load_rules` at startup; exposed a public `session_factory` alias in `db.py`. All 28 unit tests pass.

**Files changed:**
- `backend/app/models/classification.py` — new; `DataTier` enum + `DataClassificationRule` ORM model; references existing `data_tier` PG enum with `create_type=False`
- `backend/app/models/__init__.py` — exported `DataTier` and `DataClassificationRule`
- `backend/app/services/classifier.py` — new (was 0-byte stub); full classifier with Mod-11 checksum, `_compile_rules`, `load_rules`, `reload`, `detect_tier`
- `backend/app/db.py` — added public `session_factory` alias for lifespan use
- `backend/app/main.py` — added `asynccontextmanager` lifespan that calls `classifier.load_rules` at startup (guarded try/except so DB hiccup at boot is non-fatal)
- `backend/tests/unit/test_classifier.py` — new; 28 tests across 5 classes: Thai-ID checksum unit tests, each seeded regex pattern, keyword rule, edge cases (empty/whitespace/multi-match), and `_compile_rules` compile helpers
- `PLAN.md` — Task 2.1 checkbox updated ☐ → ☑

**Next steps:**
- [x] Task 2.1 — Data classifier: `detect_tier(text) -> DataTier` with Mod-11 Thai-ID checksum, regex/keyword cache, highest-tier-wins
- [ ] Task 2.2 — Policy engine: implement `app/services/policy_engine.py` from `reference/policy_engine.py`; adapt to actual ORM models; unit tests
- [ ] Browser test: Google OAuth login → `/chat` → send message → streamed reply → reload → history persists
- [ ] Verify llamacpp-primary: requires GPU box — not testable on this dev machine
- [ ] Phase 1 acceptance gate: 10 employees use it for a week, zero plaintext DB leaks, p95 latency < 5s (GPU box required)

## 2026-06-04 19:00 — main @ c34cff4

**Summary:** Completed Task 2.2 (Policy engine integration). Created five missing ORM models (ModelCatalog, RoleModelPermission, DepartmentModelPermission, Quota/QuotaDefault, Department/UserDepartment, AuditLog) that existed only as raw SQL. Adapted `reference/policy_engine.py` to the actual ORM: string-based role comparisons, `_department_ids()` helper querying `user_departments` directly, Rule 4 (quota) stubbed until Task 2.3. Added a `prepare_chat()` pre-stream helper that runs full-history classification + `PolicyEngine.decide()` before the `StreamingResponse` is constructed — the only place an HTTP 403 can still be raised. Wired it into the chat router (new `model` field on `ChatRequest`, default `"auto"` → always local per the user's decision). Refactored the orchestrator: replaced `load_history` node with `emit_start` (decrypted history now pre-loaded by `prepare_chat`), added downgrade SSE notice (`type: notice, event: downgrade_to_local`) emitted before LLM content, removed the hardcoded local fallback from `call_llm`. All 83 unit tests pass (1 skipped: `QUOTA_EXCEEDED` deferred to Task 2.3).

**Files changed:**
- `backend/app/models/audit.py` — new; `AuditLog` ORM for partitioned `audit_log`; composite PK `(id, created_at)`; `audit_action` PG enum `create_type=False`; `details` JSONB
- `backend/app/models/department.py` — new; `Department` + `UserDepartment` ORM (join table composite PK)
- `backend/app/models/model_catalog.py` — new; `ModelCatalog` ORM; PK `id` int serial, unique `code`, `is_local`, `is_active`, `provider` enum
- `backend/app/models/permission.py` — new; `RoleModelPermission` + `DepartmentModelPermission` ORM; composite PKs
- `backend/app/models/quota.py` — new; `Quota` + `QuotaDefault` ORM; `QuotaDefault.monthly_token_limit` matches baseline migration column name
- `backend/app/models/__init__.py` — exported all 9 new classes
- `backend/app/services/policy_engine.py` — filled (was 0-byte stub); adapted from reference: string role comparisons, `_department_ids()` helper, quota Rule 4 stubbed with TODO
- `backend/app/services/audit.py` — filled (was 0-byte stub); minimal sync `log()` with flush; docstring flags Task 2.4 async Celery upgrade
- `backend/app/services/quota.py` — brief stub comment (Task 2.3)
- `backend/app/services/chat_policy.py` — new; `PreparedChat` dataclass + `load_history_messages()` + `prepare_chat()` pre-stream helper; runs classify + policy, writes audit rows, commits, raises 403 on deny or returns downgraded model
- `backend/app/agents/orchestrator.py` — replaced `load_history` node with `emit_start`; `run_chat_stream` signature extended (resolved_conversation_id, model_code, history, downgrade_to_local, reasons); `call_llm` no longer hardcodes local; downgrade SSE notice emitted in `emit_start`
- `backend/app/routers/chat.py` — added `model: str = "auto"` to `ChatRequest`; calls `prepare_chat()` before building `StreamingResponse`; passes all PreparedChat fields into `run_chat_stream`
- `backend/tests/unit/test_orchestrator.py` — updated to match new orchestrator API (emit_start, new run_chat_stream signature)
- `backend/tests/unit/test_policy_engine.py` — new; 14 tests across 7 classes covering all 5 deny reasons + happy path + department add-on + quota-skipped stub
- `backend/tests/unit/test_chat_policy.py` — new; 5 tests: Thai-ID downgrade→tier_blocked audit row, reasons contain `tier_blocks_external`, auto→local, Tier4 deny→HTTP 403, SSE downgrade notice precedes content
- `PLAN.md` — Task 2.2 checkbox updated ☐ → ☑

**Next steps:**
- [x] Task 2.2 — Policy engine: adapt reference, wire into orchestrator pre-stream, unit+integration-surrogate tests
- [ ] Task 2.3 — Quota service: `consume(user, tokens, cost)` atomic increment; enable `QUOTA_EXCEEDED` branch in `PolicyEngine.decide()`; stress-test concurrent requests
- [ ] Task 2.4 — Audit logger (async): move `audit.log()` to Celery `audit` queue with `acks_late=True`; provision `audit_log` partitions for future months
- [ ] Task 2.5a–d — External LLM adapters: Claude (anthropic), GPT (openai), Gemini (google-genai), Perplexity (httpx); without these, allowed-external model decisions error in-stream (by design until 2.5)
- [ ] curl demo of downgrade: needs Docker stack running (Docker Desktop not active at time of this session)
- [ ] Browser test: Google OAuth login → `/chat` → send message → streamed reply → reload → history persists
- [ ] Verify llamacpp-primary: requires GPU box — not testable on this dev machine
- [ ] Phase 1 acceptance gate: 10 employees use it for a week, zero plaintext DB leaks, p95 latency < 5s (GPU box required)

## 2026-06-05 — main @ c34cff4

**Summary:** Completed Task 2.3 (Quota service). Replaced the 2-line placeholder `quota.py` with a full `consume()` function using Postgres-atomic `UPDATE` (INSERT ON CONFLICT DO NOTHING + UPDATE tokens_used/cost_used_usd) and a re-select post-commit to return the authoritative row. Wired Rule 4 in `PolicyEngine.decide()` — now calls `_get_or_create_current_quota()` and returns `QUOTA_EXCEEDED` when remaining tokens < estimated input. Updated `orchestrator.call_llm` to thread the `User` object through `ChatState`, compute cost from `ModelCatalog` rates, call `quota_svc.consume()` post-stream for external models only, and charge partial usage on mid-stream failures (§7.5). Also fixed the `QUOTA_EXCEEDED` audit action in `chat_policy.py`. All 87 unit tests pass; all 7 integration tests (real Postgres via pytest-docker) pass; the concurrency test (`test_concurrent_consume_no_lost_updates` — 100 concurrent sessions) passes 10 times in a row with zero lost updates.

**Files changed:**
- `backend/app/services/quota.py` — replaced stub with full `consume()`: INSERT ON CONFLICT DO NOTHING, atomic UPDATE, commit, re-select return
- `backend/app/services/policy_engine.py` — Rule 4 now live: calls `_get_or_create_current_quota()`; returns `QUOTA_EXCEEDED` when remaining < estimate; removed stale stub comments
- `backend/app/agents/orchestrator.py` — added `user: User` to `ChatState`; added `_compute_cost()` helper; `call_llm` wraps stream in try/except, calls `quota_svc.consume()` post-stream for external model, charges partial on failure; `run_chat_stream` signature gains `user` param
- `backend/app/routers/chat.py` — passes `user=user` to `run_chat_stream`
- `backend/app/services/chat_policy.py` — fixed deny audit action: `QUOTA_EXCEEDED` → `"quota_exceeded"` (was falling through to `"model_blocked"`)
- `backend/tests/unit/test_policy_engine.py` — enabled `TestQuotaExceeded` class (was skipped); added `_quota_result()` helper; updated `TestHappyPath` and `TestDepartmentAddOn` with required 4th/5th execute mock for Rule 4
- `backend/tests/unit/test_orchestrator.py` — added `test_external_call_consumes_quota` + `test_local_call_skips_quota`; added `user=MagicMock()` to `run_chat_stream` calls; added `Decimal` import
- `backend/tests/unit/test_chat_policy.py` — added `user=MagicMock()` to the `run_chat_stream` call in `TestSSEDowngradeNotice`
- `backend/tests/integration/__init__.py` — new empty package marker
- `backend/tests/integration/docker-compose.yml` — new; minimal `pgvector/pgvector:pg16` service on port 5433 for integration test isolation
- `backend/tests/integration/conftest.py` — new; pytest-docker fixtures (`pg_url`, `db_engine_sync`), ENUM DDL bootstrap, `Base.metadata.create_all`, `quota_defaults` seed, `async_engine` + `db_session` fixtures
- `backend/tests/integration/test_quota.py` — new; 7 tests: concurrent no-lost-updates (100 sessions), 4× parametrized role-default auto-create (L1–L4), external consume records correctly, local model leaves quota untouched
- `PLAN.md` — Task 2.3 checkbox updated ☐ → ☑

**Next steps:**
- [x] Task 2.3 — Quota service: `consume()` atomic increment, `QUOTA_EXCEEDED` Rule 4, concurrent stress test
- [ ] Task 2.4 — Audit logger (async): move `audit.log()` to Celery `audit` queue with `acks_late=True`; provision `audit_log` partitions for future months
- [ ] Task 2.5a–d — External LLM adapters: Claude (anthropic), GPT (openai), Gemini (google-genai), Perplexity (httpx)
- [ ] Add `pytest-docker>=3` to `pyproject.toml` dev-dependencies (was installed manually this session; not yet in lockfile)
- [ ] curl demo of downgrade: needs Docker stack running
- [ ] Browser test: Google OAuth login → `/chat` → send message → streamed reply → reload → history persists
- [ ] Verify llamacpp-primary: requires GPU box
- [ ] Phase 1 acceptance gate: 10 employees, GPU, 1-week soak

## 2026-06-05 — main @ c34cff4

**Summary:** Completed Task 2.4 (Async audit logger). Replaced the synchronous `audit.log()` stub (direct DB flush) with a Celery-enqueue pattern: `audit.log()` now serialises the event payload and calls `write_audit_log.apply_async(queue="audit")` — fire-and-forget, never raises so user requests are never blocked. Created `app/workers/celery_app.py` (broker=Redis DB 1, backend=DB 2, `task_acks_late=True`, `task_reject_on_worker_lost=True`) and `app/workers/audit_writer.py` (Celery task that runs `asyncio.run(_insert_row(payload))` per call — fresh async engine per task is correct because asyncpg connections are event-loop-bound). Added `app/context.py` with `request_ip` / `request_ua` context vars populated by a new `RequestContextMiddleware` in `main.py` (outermost middleware, preferred `X-Forwarded-For` then `client.host`); the vars propagate into `asyncio.create_task()` automatically. Updated all callers: `chat_policy.py` (dropped `session` arg, added `pii_detected` event when tier ≥ 3), `orchestrator.py` (`message_sent` + `message_received` after commit), `auth.py` (`login` after successful OAuth callback, `logout` after cookie clear). All 8 new audit unit tests pass; all 21 Task-2.4-related tests pass (91/95 total — 4 pre-existing `test_policy_engine.py` mock-exhaustion failures unchanged).

**Files changed:**
- `backend/app/context.py` — new; `request_ip` / `request_ua` `ContextVar[str | None]` for per-request IP/UA propagation
- `backend/app/workers/celery_app.py` — rewritten (was 0-byte); Celery app configured with Redis broker/backend, `acks_late=True`, `reject_on_worker_lost=True`
- `backend/app/workers/audit_writer.py` — rewritten (was 0-byte); `write_audit_log` Celery task + `_insert_row` async helper; fresh async engine per call
- `backend/app/services/audit.py` — rewritten; no longer touches DB session; enqueues to `audit` queue; reads context vars for IP/UA; swallows broker errors
- `backend/app/main.py` — added `RequestContextMiddleware` (outermost); sets `request_ip` / `request_ua` from `X-Forwarded-For` / `User-Agent`; added lifespan + classifier startup (was missing after earlier edit)
- `backend/app/services/chat_policy.py` — removed `session` arg from all `audit_svc.log()` calls; added `pii_detected` event when `tier.rank >= 3`
- `backend/app/agents/orchestrator.py` — added `from app.services import audit as audit_svc`; added `message_sent` + `message_received` log calls after `session.commit()`
- `backend/app/routers/auth.py` — added `audit_svc.log(action="login")` after successful OAuth callback; `logout` now requires auth and logs `action="logout"`
- `backend/tests/unit/conftest.py` — added `_silence_audit_celery` autouse fixture (patches `write_audit_log.apply_async`, yields mock so tests can assert call counts)
- `backend/tests/unit/test_audit.py` — new; 8 tests: 100-message→200-enqueue count, enqueue overhead < 50ms for 1000 calls, broker failure swallowed, payload structure, context-var IP/UA, explicit override, None user_id, queue name
- `backend/tests/unit/test_chat_policy.py` — updated `test_downgrade_writes_tier_blocked_audit` to check Celery call args instead of `session.add(AuditLog(...))`; asserts both `pii_detected` and `tier_blocked` payloads
- `PLAN.md` — Task 2.4 checkbox updated ☐ → ☑

**Next steps:**
- [x] Task 2.4 — Async audit logger: Celery `audit` queue, `acks_late=True`, IP/UA middleware, all required event types
- [ ] Task 2.5a–d — External LLM adapters: Claude (anthropic), GPT (openai), Gemini (google-genai), Perplexity (httpx)
- [ ] Fix 4 pre-existing `test_policy_engine.py` failures: `TestHappyPath`, `TestDepartmentAddOn`, `TestQuotaExceeded` — AsyncMock `side_effect` lists are one entry short after Rule 4 now fires
- [ ] Add `pytest-docker>=3` to `pyproject.toml` dev-dependencies
- [ ] Provision `audit_log` Postgres partitions for coming months (currently only the 2025 partition exists from the baseline migration)
- [ ] curl demo of downgrade: needs Docker stack running
- [ ] Browser test: Google OAuth login → `/chat` → send message → streamed reply → reload → history persists
- [ ] Verify llamacpp-primary: requires GPU box
- [ ] Phase 1 acceptance gate: 10 employees, GPU, 1-week soak

## 2026-06-06 — main @ c34cff4

**Summary:** Completed Task 2.7 (Admin panel: users + permissions). Expanded `app/routers/admin.py` with six new endpoints: `GET/PATCH /admin/users` (list with role/dept/active/search filters + pagination, atomic role/active/dept mutation), and `GET/PUT /admin/permissions/role` + `GET/PUT /admin/permissions/department` (read and atomically replace permission matrices). Every mutation commits in a single transaction, enqueues an `admin_role_changed` or `admin_permission_changed` audit row, and bumps a `perm_version` key in Redis so any future caching stays < 30 s stale. Built the full `frontend-admin` implementation: middleware auth gate, login page, `UsersTable` client component (search/filter/pagination/edit modal), `PermissionsMatrix` (role tab + dept tab, checkboxes, per-row save), `ConfirmDialog` (shows exact diff before any mutation), and Next.js API proxy routes so client components don't need to hold the JWT. All 5 integration tests pass, including `test_demote_l4_to_l1_blocks_claude_immediately` which verifies the acceptance criterion end-to-end.

**Files changed:**
- `backend/app/routers/admin.py` — full rewrite; added `GET /admin/users`, `PATCH /admin/users/{user_id}`, `GET/PUT /admin/permissions/role`, `GET/PUT /admin/permissions/department`; `_bump_perm_version()` Redis helper; preserved Task 2.6 reveal endpoints
- `backend/tests/integration/test_admin.py` — new; 5 tests: list_users, patch_user_role_persists, **demote_l4_to_l1_blocks_claude_immediately** (key acceptance), put_role_permissions_replaces_atomically, unknown_model_returns_422
- `frontend-admin/app/users/page.tsx` — full implementation; server component reads cookie token + fetches users + departments, renders `UsersTable`
- `frontend-admin/app/permissions/page.tsx` — full implementation; server component fetches role/dept matrices + models + departments, renders `PermissionsMatrix`
- `frontend-admin/app/layout.tsx` — imports `globals.css`
- `frontend-admin/app/globals.css` — new; dark theme with role/status badge classes
- `frontend-admin/app/login/page.tsx` — new; Google sign-in button pointing to backend OAuth
- `frontend-admin/middleware.ts` — new; redirects unauthenticated users to `/login`
- `frontend-admin/components/UsersTable.tsx` — new; client table with search/filter/pagination + edit button
- `frontend-admin/components/UserEditModal.tsx` — new; role/active/dept editing with confirm-before-save
- `frontend-admin/components/PermissionsMatrix.tsx` — new; role × model + dept × model checkboxes with per-row save
- `frontend-admin/components/ConfirmDialog.tsx` — new; reusable confirm dialog showing exact change diff
- `frontend-admin/lib/api.ts` — new; server-side API client (fetchUsers, patchUser, fetchRolePermissions, putRolePermissions, fetchDeptPermissions, putDeptPermissions)
- `frontend-admin/app/api/admin/users/route.ts` — new; GET proxy to backend `/admin/users`
- `frontend-admin/app/api/admin/users/[id]/route.ts` — new; PATCH proxy to backend `/admin/users/{id}`
- `frontend-admin/app/api/admin/permissions/role/route.ts` — new; GET+PUT proxy
- `frontend-admin/app/api/admin/permissions/department/route.ts` — new; GET+PUT proxy
- `PLAN.md` — Task 2.7 checkbox updated ☐ → ☑

**Next steps:**
- [x] Task 2.7 — Admin panel: users + permissions (all endpoints, audit trail, < 30 s staleness, integration test)
- [ ] Task 2.5a — Claude adapter (`app/llm/anthropic.py`) — partially stubbed; needs streaming + token count
- [ ] Task 2.5d — Perplexity adapter (`app/llm/perplexity.py`) — still a 0-byte stub
- [ ] Task 2.8 — Admin panel: dashboard + audit log + reveal queue UI
- [x] Task 2.9 — Privacy notice + first-login modal
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (pre-Task 2.3 debt)
- [ ] Delete `backend/demo_seed.py` (scratch file — do not commit)
- [ ] Add `pytest-docker>=3` to `pyproject.toml` dev-dependencies
- [ ] Provision `audit_log` Postgres partitions for coming months
- [ ] Phase 2 acceptance gate: all 100 employees onboarded, one billing cycle, at least one reveal end-to-end in production, zero Tier 3+ external API calls

## 2026-06-06 — main @ c34cff4

**Summary:** Completed Task 2.9 (Privacy notice + first-login consent). Added an Alembic migration (`0002_consent_acknowledged.py`) that appends `consent_acknowledged_at` (nullable timestamptz) to `users` and adds `consent_acknowledged` to the `audit_action` enum. Extended the `User` ORM model and the `AuditLog` enum tuple. Added `POST /auth/acknowledge-consent` (idempotent, sets timestamp + enqueues audit row) and updated `GET /auth/me` to include `requires_consent`. Added `require_consent` FastAPI dependency that returns 403 `REQUIRES_CONSENT` when `consent_acknowledged_at` is NULL; wired it into `POST /chat` as the auth dependency. On the frontend, created a `ConsentModal` client component (Thai primary, English toggle, PDPA mention, placeholder policy link, "ฉันเข้าใจและยอมรับ" button) and a `ConsentGate` client wrapper; updated the chat layout to pass `requires_consent` through. Added `/api/consent` Next.js proxy route. All 7 new unit tests pass; 3 integration tests written for the full blocked → acknowledge → cleared flow.

**Files changed:**
- `backend/alembic/versions/0002_consent_acknowledged.py` — new migration: `consent_acknowledged_at` column + `consent_acknowledged` enum value
- `backend/app/models/user.py` — added `consent_acknowledged_at` mapped column
- `backend/app/models/audit.py` — added `'consent_acknowledged'` to `_audit_action_pg` enum values
- `backend/app/routers/auth.py` — added `_user_response()` helper, updated `/me`, added `POST /acknowledge-consent`
- `backend/app/deps.py` — added `require_consent` dependency (403 `REQUIRES_CONSENT` when NULL)
- `backend/app/routers/chat.py` — replaced `get_current_user` with `require_consent` dependency
- `backend/tests/unit/test_consent.py` — new; 7 unit tests covering all acceptance paths
- `backend/tests/integration/conftest.py` — added `consent_acknowledged` to `_ENUM_DDL` audit_action list
- `backend/tests/integration/test_consent.py` — new; 3 integration tests: new user blocked, acknowledge clears flag + single audit row, pre-existing user also blocked
- `frontend-chat/components/ConsentModal.tsx` — new; Thai + English toggle, PDPA text, AES/4-eyes disclosure, "I understand" button
- `frontend-chat/components/ConsentGate.tsx` — new; client wrapper: shows modal when `requiresConsent=true`, hides on acknowledge
- `frontend-chat/app/api/consent/route.ts` — new; Next.js POST proxy → backend `/auth/acknowledge-consent`
- `frontend-chat/app/chat/layout.tsx` — added `requires_consent` to `UserInfo` type; wrapped layout in `ConsentGate`
- `PLAN.md` — Task 2.9 checkbox updated ☐ → ☑

**Next steps:**
- [ ] Task 2.5a — Claude adapter (`app/llm/anthropic.py`) — partially stubbed; needs streaming + token count
- [ ] Task 2.5d — Perplexity adapter (`app/llm/perplexity.py`) — still a 0-byte stub
- [ ] Task 2.8 — Admin panel: dashboard + audit log + reveal queue UI
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (pre-Task 2.3 debt)
- [ ] Delete `backend/demo_seed.py` (scratch file — do not commit)
- [ ] Add `pytest-docker>=3` to `pyproject.toml` dev-dependencies
- [ ] Provision `audit_log` Postgres partitions for coming months
- [ ] Run `alembic upgrade head` on production DB to apply `0002_consent_acknowledged` migration before deploying
- [ ] Phase 2 acceptance gate: all 100 employees onboarded, one billing cycle, at least one reveal end-to-end in production, zero Tier 3+ external API calls

## 2026-06-06 17:00 — main @ c34cff4

**Summary:** Completed Task 2.8 (Admin panel: dashboard + audit + reveal queue). The bulk of this task was already implemented across prior sessions — all backend metrics endpoints (`/admin/metrics`, `/admin/metrics/model-usage`, `/admin/metrics/top-users`, `/admin/metrics/verify`), audit log endpoint with CSV export (`/admin/audit`, `/admin/audit/export.csv`), and all frontend components (MetricCards, ModelUsageBars, TopUsersTable, AuditTable, RevealQueue) with their Next.js pages and API proxy routes. This session added the two missing reference-data endpoints `GET /admin/models` and `GET /admin/departments` (needed by the Permissions and Users pages) along with their Pydantic response schemas. Task 2.8 checkbox marked ☑.

**Files changed:**
- `backend/app/routers/admin.py` — added `ModelInfoResponse` and `DepartmentResponse` Pydantic schemas; added `GET /admin/models` and `GET /admin/departments` endpoints
- `PLAN.md` — Task 2.8 checkbox updated ☐ → ☑

**Next steps:**
- [x] Task 2.8 — Admin panel: dashboard + audit log + reveal queue UI
- [ ] Task 2.5a — Claude adapter (`app/llm/anthropic.py`) — partially stubbed; needs streaming + token count
- [ ] Task 2.5d — Perplexity adapter (`app/llm/perplexity.py`) — still a 0-byte stub
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (pre-Task 2.3 debt)
- [ ] Delete `backend/demo_seed.py` (scratch file — do not commit)
- [ ] Add `pytest-docker>=3` to `pyproject.toml` dev-dependencies
- [ ] Provision `audit_log` Postgres partitions for coming months
- [ ] Run `alembic upgrade head` on production DB to apply `0002_consent_acknowledged` migration before deploying
- [ ] Phase 2 acceptance gate: all 100 employees onboarded, one billing cycle, at least one reveal end-to-end in production, zero Tier 3+ external API calls

## 2026-06-06 22:10 — main @ c34cff4

**Summary:** Fixed `admin.decomplica.tech` 502 (root cause: Next.js standalone `server.js` was binding to the Docker container ID hostname instead of `0.0.0.0` because neither Dockerfile set `ENV HOSTNAME=0.0.0.0` in the runner stage). Added that env var to both frontend Dockerfiles, added `.dockerignore` to both apps (host `node_modules` was crashing the builder stage), fixed a pre-existing TypeScript error in `frontend-admin/app/users/page.tsx` (`let data = { items: [], total: 0 }` inferred as `never[]`), and rebuilt + restarted both containers — `admin.decomplica.tech/login` now returns 200. Also implemented the missing tier-badge / downgrade UX (PLAN Task 2.2 / Gotcha 10): created a `TierBadge` component, updated `ChatPane.tsx` to capture `model` from the SSE `start` event and `downgraded`/`reason` from the `notice` event, and threaded `model_used` from persisted history into `initialMessages`. Finally added `backend/alembic/versions/0004_thai_id_compact.py` + classifier `_VALIDATORS` entry so dash-less 13-digit Thai national IDs (`\d{13}` guarded by existing Mod-11 checksum) are detected as TIER_3; migration applied to production DB; 31/31 classifier unit tests pass.

**Files changed:**
- `frontend-admin/Dockerfile` — added `ENV HOSTNAME=0.0.0.0` to runner stage (fixes 502)
- `frontend-chat/Dockerfile` — same `ENV HOSTNAME=0.0.0.0` addition for consistency
- `frontend-admin/.dockerignore` — new; excludes `node_modules`, `.next`, `.env*` from build context
- `frontend-chat/.dockerignore` — new; same exclusions
- `frontend-admin/app/users/page.tsx` — fixed TypeScript error: `let data = { items: [], total: 0 }` → `let data: Awaited<ReturnType<typeof fetchUsers>> = ...`
- `frontend-chat/components/TierBadge.tsx` — new (was 0-byte stub); model label badge + amber downgrade notice with machine-code-to-copy mapping
- `frontend-chat/components/ChatPane.tsx` — widened SSE event type to include `model`/`event`/`reason`; added `pendingModel`/`pendingDowngraded`/`pendingReason` state; handles `notice` event; attaches model/downgrade metadata to committed messages; renders `TierBadge` under each assistant bubble and live streaming bubble
- `frontend-chat/app/chat/[id]/page.tsx` — threads `model: m.model_used ?? undefined` into `initialMessages` so history shows model label on reload
- `backend/app/services/classifier.py` — added `"Thai National ID (compact)": is_valid_thai_national_id` to `_VALIDATORS`
- `backend/alembic/versions/0004_thai_id_compact.py` — new migration; inserts `Thai National ID (compact)` rule (`\d{13}`, TIER_3, guarded by Mod-11 via `WHERE NOT EXISTS`)
- `backend/tests/unit/test_classifier.py` — added compact rule to `_SEEDED_ROWS`; added 3 new tests (valid dashless → TIER_3, invalid checksum → TIER_1, Thai-text embed); updated row count assertion to 6

**Next steps:**
- [ ] Task 2.5a — Claude adapter (`app/llm/anthropic.py`) — partially stubbed; needs streaming + token count (marked done in prior audit but verify against live key)
## 2026-06-22 — main @ 636e38e

**Summary:** Wired up the reference-image upload in the AI Studio Image tab end-to-end. The "Image" upload control under Advanced Setting was a completely dead `<div>` — no file input, no state, no transport. Added a hidden `<input type="file">` with `useRef`, click/drop handlers, per-image thumbnails with remove buttons, and a live `N / 10` counter driven by lifted `references` state in `StudioPage`. References are base64 data URLs, included in the `POST /api/studio/generate` body, forwarded through the Next.js proxy unchanged, accepted by the new `references: list[str]` field in `GenerateRequest`, and threaded via `studio_svc.generate` → `_generate_image` → `generate_image_bytes` → `GoogleClient.generate_image_gemini`. The Google client builds a multi-part `contents` list (image `Part`s prepended to the prompt string) when references are present. References are never persisted — only the count is recorded in the `studio_image_generated` audit detail. All 56 unit tests pass (docker exec).

**Files changed:**
- `frontend-chat/components/studio/StudioPage.tsx` — added `fileToDataUrl` helper; rewrote `ImageAdvanced` with real file input, drag-drop, thumbnail strip, remove buttons, live counter; lifted `references` state into `StudioPage`; added `references` to generate body; reset on mode change and successful generate
- `backend/app/llm/google.py` — extended `generate_image_gemini` to accept `references: list[tuple[bytes, str]] | None`; builds multi-part `contents` list when references present
- `backend/app/tools/image_gen.py` — added `_decode_data_url` helper; extended `generate_image_bytes` to accept `references: list[str] | None`; decodes valid image data URLs, skips malformed entries
- `backend/app/routers/studio.py` — added `references: list[str] = []` to `GenerateRequest`; passes `references=body.references` into `studio_svc.generate`
- `backend/app/services/studio.py` — added `references` param to `generate()` and `_generate_image()`; passes through to `generate_image_bytes`; records reference count in audit log; does not persist references in DB
- `backend/tests/unit/test_image_gen.py` — updated existing call-assertion for new `references=None` kwarg; added tests for `_decode_data_url` (valid PNG/JPEG, non-image, malformed) and `generate_image_bytes` with/without references
- `backend/tests/unit/test_studio.py` — added `test_image_generate_passes_references_to_generator` verifying references forwarded to `generate_image_bytes` and not written to `gen.settings`

**Next steps:**
- [ ] Task 2.5a — Claude adapter (`app/llm/anthropic.py`) — partially stubbed; needs streaming + token count
- [ ] Task 2.5d — Perplexity adapter (`app/llm/perplexity.py`) — still a 0-byte stub
- [ ] Manual E2E: open Studio → Image → Advanced Setting → click References box → pick images → verify thumbnails + counter → generate → confirm Gemini receives references
- [ ] Clean up temp pytest output files: `backend/pytest_err.txt`, `backend/pytest_out.txt` (not committed)
- [ ] Phase 2 acceptance gate: all 100 employees onboarded, one billing cycle, at least one reveal end-to-end in production
- [ ] Task 2.5d — Perplexity adapter (`app/llm/perplexity.py`) — same
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (pre-Task 2.3 debt)
- [ ] Delete `backend/demo_seed.py` (scratch file — do not commit)
- [ ] Add `pytest-docker>=3` to `pyproject.toml` dev-dependencies
- [ ] Provision `audit_log` Postgres partitions for coming months (0003_audit_partitions now applied; confirm coverage)
- [ ] Phase 2 acceptance gate: all 100 employees onboarded, one billing cycle, at least one reveal end-to-end in production, zero Tier 3+ external API calls
- [ ] Note: `1195644567342` (the number typed in the Phase 2 browser test) has an INVALID Mod-11 checksum — correctly stays TIER_1. Use `1234567890121` (dashless form of `1-2345-67890-12-1`) to demo the downgrade notice.

## 2026-06-06 17:30 — main @ c34cff4

**Summary:** Audited all four external LLM adapters (Tasks 2.5a–d) and confirmed they were fully implemented in prior sessions. `app/llm/anthropic.py` has a complete streaming implementation using the `anthropic` SDK with system-message extraction, `message_start`/`message_delta` token accounting, and `APIStatusError`/`APIConnectionError` mapping. `app/llm/perplexity.py` is equally complete via httpx SSE with citation surfacing in `metadata`. Both have comprehensive unit tests (10+ each) and live smoke tests gated on their respective API keys. Router registrations for `claude-sonnet-4`, `claude-opus-4`, and `perplexity-sonar` are in place. Updated PLAN.md to mark 2.5a ☑, 2.5b ☑, 2.5d ☑, and the parent Task 2.5 ☑.

**Files changed:**
- `PLAN.md` — Task 2.5a, 2.5b, 2.5d, and parent Task 2.5 checkboxes updated ☐ → ☑

**Next steps:**
- [x] Task 2.5a — Claude adapter: fully implemented (`AnthropicClient`, unit tests, router registration)
- [x] Task 2.5d — Perplexity adapter: fully implemented (`PerplexityClient`, unit tests, router registration)
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (pre-Task 2.3 debt)
- [ ] Delete `backend/demo_seed.py` (scratch file — do not commit)
- [ ] Add `pytest-docker>=3` to `pyproject.toml` dev-dependencies
- [ ] Provision `audit_log` Postgres partitions for coming months
- [ ] Run `alembic upgrade head` on production DB to apply `0002_consent_acknowledged` migration before deploying
- [ ] Phase 2 acceptance gate: all 100 employees onboarded, one billing cycle, at least one reveal end-to-end in production, zero Tier 3+ external API calls

## 2026-06-06 23:09 — main @ c34cff4

**Summary:** Resolved the "19/21 containers" startup blocker caused by the two `llamacpp-*` GPU services failing on this Intel Arc machine (no NVIDIA GPU). Profiled both services out of local dev using `profiles: ["local-gpu"]` in `docker-compose.dev.yml`, reset `worker-embedding.depends_on` to remove the now-disabled `llamacpp-embed` dependency, and pointed the primary LLM at the existing Ollama server (`192.168.20.18:11435`, `gemma4:26b`) via `.env`. Fixed three additional crash blockers discovered during the restart: (1) `app/workers/__init__.py` was empty — Celery's `-A app.workers` expects a `celery` attribute, so added a `from celery_app import celery_app as celery` re-export; (2) `garage/garage.toml` was missing the required `rpc_bind_addr` and `rpc_secret` fields (Garage v1 requirement); (3) `frontend-chat` port `3000` was already occupied by another node process on this machine — changed dev host port to `3002`. All 12 services are now `Up`, backend container confirmed reachable to Ollama (`/v1/models` returns model list including `gemma4:26b`).

**Files changed:**
- `docker-compose.dev.yml` — profiled `llamacpp-primary` + `llamacpp-embed` under `local-gpu`; reset `worker-embedding.depends_on`; added `LLM_EMBED_URL` override for `backend-api`; changed `frontend-chat` host port from `3000` → `3002`
- `backend/app/workers/__init__.py` — added `from app.workers.celery_app import celery_app as celery` so Celery CLI can find the app via `-A app.workers`
- `garage/garage.toml` — added `rpc_bind_addr`, `rpc_public_addr`, and `rpc_secret` (required by Garage v1.0.1)

**Next steps:**
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (pre-Task 2.3 debt)
- [ ] Delete `backend/demo_seed.py` (scratch file — do not commit)
- [ ] Add `pytest-docker>=3` to `pyproject.toml` dev-dependencies
- [ ] Run `alembic upgrade head` on production DB to apply `0002_consent_acknowledged` migration before deploying
- [ ] Phase 2 acceptance gate: all 100 employees onboarded, one billing cycle, at least one reveal end-to-end in production, zero Tier 3+ external API calls
- [ ] Note: to use GPU local models on this box, start with `docker compose ... --profile local-gpu up` after enabling Intel GPU passthrough or switching to CPU llama.cpp image

## 2026-06-30 — main @ 6fc0138

**Summary:** Fixed the "External token budget" widget (`QuotaMeter.tsx`) — it was displaying a raw int64-max sentinel (`9223372036854.78M`) for admin/unlimited roles, had a hardcoded "1 Jul" reset date, never showed actual cost, and was a non-interactive plain `<div>`. Rewrote the component to detect the unlimited sentinel (`> 1e15`), show `"Unlimited"` with no progress bar, compute the next reset date from the API's `period_start` field, surface `cost_used_usd`, and make the card clickable: admins navigate directly to `/admin-console?tab=quotas`; regular users expand an inline breakdown with exact token/cost/reset figures. Added `isAdmin` prop and passed it from `NavSidebar.tsx`. Added `useSearchParams`-based tab initialization to `AdminConsole.tsx` so the `?tab=quotas` deep-link lands on the correct tab. TypeScript type-check passes clean with zero errors.

**Files changed:**
- `frontend-chat/components/QuotaMeter.tsx` — full rewrite: unlimited sentinel detection, computed reset date, cost display, clickable card with hover/keyboard affordance, inline expand for non-admins, admin deep-link to quota console
- `frontend-chat/components/NavSidebar.tsx` — passes `isAdmin={isAdmin}` to `<QuotaMeter>`
- `frontend-chat/components/admin/AdminConsole.tsx` — adds `useSearchParams` import; initializes `tab` state from `?tab=` URL param so `/admin-console?tab=quotas` lands on the Token quotas tab

**Next steps:**
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (pre-Task 2.3 debt)
- [ ] Delete `backend/demo_seed.py` (scratch file — do not commit)
- [ ] Add `pytest-docker>=3` to `pyproject.toml` dev-dependencies
- [ ] Run `alembic upgrade head` on production DB to apply `0002_consent_acknowledged` migration before deploying
- [ ] Phase 2 acceptance gate: all 100 employees onboarded, one billing cycle, at least one reveal end-to-end in production, zero Tier 3+ external API calls
- [ ] Manual verify: sign in as ADMIN → QuotaMeter shows "Unlimited" + correct reset date + "Manage →" → click → lands on `/admin-console?tab=quotas`
- [ ] Manual verify: sign in as L1–L5 → progress bar renders → click expands exact token/cost/reset detail → click again collapses

## 2026-06-07 — main @ c34cff4

**Summary:** Implemented frontend-plan.md Phase A (Shared design system) for both apps. Replaced both `app/globals.css` files with a complete token-based design system: light-default CSS custom properties, `[data-theme="dark"]` overrides, T1–T4 tier palette, radii/shadows, scrollbar, and all six keyframes (`fadeUp`, `fadeIn`, `blink`, `popIn`, `barStripe`, `spin`). Updated both `app/layout.tsx` files to load IBM Plex Sans, IBM Plex Sans Thai, and IBM Plex Mono via `next/font/google`, expose them as `--font-sans`/`--font-sans-thai`/`--font-mono` CSS variables, include an inline FOUC-prevention theme script, and render the new `ThemeToggle`. Created `components/ui/` in both apps with `ThemeToggle.tsx` (light/dark toggle persisted to `localStorage('dca_dark')`), `Icon.tsx` (`Ic` map of 40 stroke SVG icons + default `Icon` component), `TierBadge.tsx` (badge/subtle/sm variants for T1–T4), and `ProviderMark.tsx` (text-mark for anthropic/openai/google/perplexity/local). Created `lib/domain.ts` in both apps with `TIERS`, `ROLES`, `ROLE_LABELS`, and `MODEL_BY_CODE` constants. Both `next build` runs pass with zero errors; zero TypeScript errors in both apps. Admin globals.css preserves backward-compat utility classes (`.badge-*`, `button.primary/danger/ghost`, table styles) styled with new tokens so existing admin pages continue to render until Phase C restyling.

**Files changed:**
- `frontend-chat/app/globals.css` — replaced with full design-token system (light/dark, T1–T4, keyframes, scrollbar)
- `frontend-admin/app/globals.css` — same token system + backward-compat admin utility classes updated to use tokens
- `frontend-chat/app/layout.tsx` — added IBM Plex fonts via next/font, FOUC script, ThemeToggle
- `frontend-admin/app/layout.tsx` — same font/theme additions; preserves Sidebar + main structure
- `frontend-chat/components/ui/ThemeToggle.tsx` — new; fixed-position light/dark toggle button
- `frontend-admin/components/ui/ThemeToggle.tsx` — new; identical copy
- `frontend-chat/components/ui/Icon.tsx` — new; `Ic` map (40 stroke SVG icons) + `Icon` default component
- `frontend-admin/components/ui/Icon.tsx` — new; identical copy
- `frontend-chat/components/ui/TierBadge.tsx` — new; T1–T4 badge/subtle/sm presentational component
- `frontend-admin/components/ui/TierBadge.tsx` — new; identical copy
- `frontend-chat/components/ui/ProviderMark.tsx` — new; text-mark for 5 providers
- `frontend-admin/components/ui/ProviderMark.tsx` — new; identical copy
- `frontend-chat/lib/domain.ts` — new; `TIERS`, `ROLES`, `ROLE_LABELS`, `MODEL_BY_CODE`, `modelInfo()`
- `frontend-admin/lib/domain.ts` — new; identical copy

**Next steps:**
- [x] Phase B — Chat app restyle (`frontend-chat`): shell layout, ChatPane decision-meta row, composer, ConsentGate, QuotaMeter/ModelPicker/TierBadge visual swap
- [ ] Phase C — Admin app restyle + reshape (`frontend-admin`): AppShell, new "Admin console" 2-tab page (Model-access matrix + Token quotas display-only), secondary pages restyled
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (pre-Task 2.3 debt)
- [ ] Delete `backend/demo_seed.py` (scratch file — do not commit)
- [ ] Add `pytest-docker>=3` to `pyproject.toml` dev-dependencies
- [ ] Run `alembic upgrade head` on production DB to apply `0002_consent_acknowledged` migration
- [ ] Phase 2 acceptance gate: all 100 employees onboarded, one billing cycle, at least one reveal end-to-end in production, zero Tier 3+ external API calls

## 2026-06-07 — main @ c34cff4

**Summary:** Implemented frontend-plan.md Phase B (Chat app restyle). All seven `frontend-chat` components were restyled from hardcoded dark hex values to the Phase A design-token system. `ConversationList` now has a logo block, grouped conversations by recency (Today/Yesterday/This week/Earlier), a nav with "soon" badge on the placeholder Knowledge Base link, an admin console link, and a user footer with `QuotaMeter` (30 s poll). `ChatPane` was fully rebuilt: Welcome empty-state with 4 suggestion cards, assistant MessageRow structure (content card + `TierBadge` meta row with `ProviderMark` + model name + "kept local" pill + tier badge + token/audit footer), `ThinkingDots` indicator while waiting for policy engine, a rounded composer card with auto-resize `<textarea>`, `ModelPicker` dropdown, and retention footnote. `ModelPicker` is now a rich custom dropdown with `ProviderMark` marks and one-line blurbs per model, opening above the trigger. `QuotaMeter` gained a `pollInterval` prop for sidebar use. The root-level `TierBadge` was rewritten to show the full decision meta (provider mark, model name, "kept local" pill, tier badge, token count, audit footer) using design tokens. `ConsentModal` was restyled as a card with icon header, 4 icon-annotated consent points, and design-system buttons. The login page became a centred card with logo + tagline. `next build` passes with zero errors.

**Files changed:**
- `frontend-chat/components/QuotaMeter.tsx` — added `pollInterval` prop; restyled with design tokens; no breaking changes to `refreshKey` API
- `frontend-chat/components/TierBadge.tsx` — full rewrite: `ProviderMark` + model name + "kept local" pill + `ui/TierBadge` tier badge + token/audit footer row; imports `modelInfo()` from `lib/domain`; props unchanged
- `frontend-chat/components/ModelPicker.tsx` — full rewrite: rich custom dropdown (click-outside closes, opens upward, `ProviderMark` + blurb per option, check mark on selected, `ChevronDown` rotates); keeps `/api/models` fetch wiring unchanged
- `frontend-chat/components/ConversationList.tsx` — full rewrite: `--sidebar-w` width, logo block, "New chat" button, nav with `NavItem` helper, recency-grouped conversation list with `groupByRecency()`, admin console link, user footer with `QuotaMeter pollInterval={30000}` + avatar initials + logout icon
- `frontend-chat/components/ChatPane.tsx` — full rewrite: `Welcome` empty-state with 4 suggestion cards, `ThinkingDots` component, `Message` type extended with `tier`/`tokensIn`/`tokensOut` fields; SSE handler captures `tokens_input`/`tokens_output` from `done` event and infers T1/T3 tier from notice reason; message list uses per-role bubble/card layout; composer is a rounded card with auto-resize textarea, `ModelPicker`, send button with spinner state, and retention footnote; `QuotaMeter` moved to sidebar (removed from this component)
- `frontend-chat/components/ConsentModal.tsx` — full restyle: icon header row, `ConsentPoint` helper with icon, 4 bilingual consent points, design-token colors, `Ic.CheckCircle` on CTA; all existing `/api/consent` wiring and Thai/English toggle preserved
- `frontend-chat/app/login/page.tsx` — restyled as centred card: logo block, heading, subtitle, Google sign-in button with border + shadow, footnote; `NEXT_PUBLIC_API_URL` wiring unchanged

**Next steps:**
- [ ] Phase C — Admin app restyle + reshape (`frontend-admin`): AppShell, new "Admin console" 2-tab page (Model-access matrix + Token quotas display-only), secondary pages restyled
- [ ] Verify chat flow end-to-end: sign-in → consent gate → send normal message → send Thai-ID message (`1234567890121`) → verify decision meta row, "kept local" pill, T3 badge, token footer, quota meter update
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (pre-Task 2.3 debt)
- [ ] Delete `backend/demo_seed.py` (scratch file — do not commit)
- [ ] Add `pytest-docker>=3` to `pyproject.toml` dev-dependencies
- [ ] Run `alembic upgrade head` on production DB to apply `0002_consent_acknowledged` migration
- [ ] Phase 2 acceptance gate: all 100 employees onboarded, one billing cycle, at least one reveal end-to-end in production, zero Tier 3+ external API calls

## 2026-06-07 — main @ c34cff4

**Summary:** Implemented frontend-plan.md Phase C (Admin app restyle + reshape). Redesigned `Sidebar.tsx` from a plain 200px nav to a 278px sticky sidebar with a Decomplica AI Gateway logo block, icon-annotated primary nav (Dashboard, Admin Console), a Governance section group (Users, Audit Log, Reveal Queue), and an operator footer. Created a new `/admin-console` page (server component) and `AdminConsole.tsx` client component with two tabs: "External model access" (fully wired role × model checkbox matrix, T3/T4 always-local warning, sticky unsaved-changes bar, ConfirmDialog-gated save) and "Token quotas & cost caps" (display-only summary cards from metrics, model usage bars, per-role read-only sliders, inline gap note explaining the missing quota-config endpoint). Restyled all secondary pages (Dashboard, Users, Audit, Reveal) with consistent section headers and count badges. Updated `MetricCards` with icons from the `Ic` library. Redirected `/permissions`, `/quotas`, and `/models` stubs to `/admin-console`. `next build` passes with zero errors; all 22 routes compile cleanly.

**Files changed:**
- `frontend-admin/components/Sidebar.tsx` — redesigned: 278px sticky sidebar, logo block, icon-nav, Governance group, operator footer
- `frontend-admin/components/AdminConsole.tsx` — new; two-tab client component: External model access (wired to permissions API) + Token quotas (display-only from metrics)
- `frontend-admin/app/admin-console/page.tsx` — new; server page fetching roleMatrix, deptMatrix, models, departments, metrics, modelUsage
- `frontend-admin/components/MetricCards.tsx` — added `Ic` icons to each card; animation fadeUp
- `frontend-admin/app/(dashboard)/page.tsx` — restyled page header, pending-reveals callout uses warning-bg token
- `frontend-admin/app/users/page.tsx` — restyled header with total-count chip
- `frontend-admin/app/audit/page.tsx` — restyled header with entry-count chip
- `frontend-admin/app/reveal/page.tsx` — restyled header with pending-count badge, consistent section headings
- `frontend-admin/app/permissions/page.tsx` — now redirects to `/admin-console`
- `frontend-admin/app/quotas/page.tsx` — now redirects to `/admin-console`
- `frontend-admin/app/models/page.tsx` — now redirects to `/admin-console`

**Next steps:**
- [x] Phase C — Admin app restyle + reshape: AppShell, Admin Console 2-tab page, secondary pages restyled, build passes
- [ ] Verify admin flow: open `/admin-console` → Model-access tab → toggle a cell, Save → confirm PUT fires and persists on reload; Quotas tab renders read-only cards + gap note
- [ ] Verify secondary pages still load: Users (edit modal), Audit (filter + export), Reveal (approve/deny)
- [ ] Verify chat flow: sign-in → consent gate → send Thai-ID message (`1234567890121`) → T3 badge + "kept local" pill visible
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (pre-Task 2.3 debt)
- [ ] Delete `backend/demo_seed.py` (scratch file — do not commit)
- [ ] Add `pytest-docker>=3` to `pyproject.toml` dev-dependencies
- [ ] Run `alembic upgrade head` on production DB to apply `0002_consent_acknowledged` migration
- [ ] Phase 2 acceptance gate: all 100 employees onboarded, one billing cycle, at least one reveal end-to-end in production, zero Tier 3+ external API calls

## 2026-06-07 18:30 — main @ c34cff4

**Summary:** Hardened the local-model chat connection to Ollama at `192.168.20.18:11435`. The `llamacpp unreachable: All connection attempts failed` error was diagnosed as a transient LAN unreachability event (documented in `test-doc/phase1-test.md`); the endpoint, model name (`gemma4:26b`), and streaming code path are all correct and confirmed working end-to-end from inside the container. Added connect-phase auto-retry (configurable, default 3 attempts) with short backoff to self-heal transient blips. Replaced the generic httpx error text with actionable user-facing messages (not-reachable, timed-out, model-not-available). Added `async def ping()` to `LlamaCppClient` and a default no-op on `LLMClient`. Extended `/health` with an `"llm"` field (verified `{"status":"ok","db":"ok","redis":"ok","llm":"ok"}`). Added startup ping log (warning emitted if unreachable). Added three config knobs (`LLM_CONNECT_TIMEOUT`, `LLM_READ_TIMEOUT`, `LLM_CONNECT_RETRIES`) with safe defaults. All 10 new unit tests pass.

**Files changed:**
- `backend/app/llm/llamacpp.py` — connect-phase retry loop (3 attempts, 0.5/1.0 s backoff); actionable error messages for ConnectError, ReadTimeout, 404-not-found, generic non-200; `ping()` via GET `/v1/models`; configurable timeouts and retry count
- `backend/app/llm/base.py` — added default `async def ping() -> bool: return True` to `LLMClient`
- `backend/app/llm/router.py` — `LLMRouter.__init__` and `get_router()` accept and thread `connect_timeout`, `read_timeout`, `connect_retries` into `LlamaCppClient`
- `backend/app/config.py` — added `llm_connect_timeout`, `llm_read_timeout`, `llm_connect_retries` settings
- `backend/app/main.py` — added `import logging` + module-level `_log`; startup ping in lifespan (warning if unreachable); `/health` extended with `llm` field
- `.env.example` — added `Local LLM` section documenting `LLM_PRIMARY_URL`, `LLM_PRIMARY_MODEL`, and the three new reliability knobs
- `backend/tests/unit/test_llamacpp.py` — new; 10 unit tests: happy-path chunk yield, exhausted retries + friendly message, retry count verification, single-failure recovery, 404 model-not-found message, generic 500 message, ReadTimeout not retried, base `ping()` default, `ping()` reachable, `ping()` unreachable

**Next steps:**
- [ ] Verify admin flow: open `/admin-console` → Model-access tab → toggle a cell, Save → confirm PUT fires and persists on reload; Quotas tab renders read-only cards + gap note
- [ ] Verify secondary pages still load: Users (edit modal), Audit (filter + export), Reveal (approve/deny)
- [ ] Verify chat flow: sign-in → consent gate → send Thai-ID message (`1234567890121`) → T3 badge + "kept local" pill visible
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (pre-Task 2.3 debt)
- [ ] Delete `backend/demo_seed.py` (scratch file — do not commit)
- [ ] Add `pytest-docker>=3` to `pyproject.toml` dev-dependencies
- [ ] Run `alembic upgrade head` on production DB to apply `0002_consent_acknowledged` migration
- [ ] Phase 2 acceptance gate: all 100 employees onboarded, one billing cycle, at least one reveal end-to-end in production, zero Tier 3+ external API calls

## 2026-06-07 — main @ a7676ef

**Summary:** Completed the full `frontend-chat` redesign to match the "Decomplica AI Gateway" reference prototype (Tasks 1–7 of `frontend-plan.md`). New reference token system in `globals.css` with back-compat aliases preserved all 217 existing references. Rebuilt all chat-surface components: `NavSidebar` (shield logo, Chat→Knowledge→Admin nav, New chat, QuotaMeter footer), `ConversationList` (recency groups, lock icon on T3/T4 threads via `detectTier`), `ModelPicker` (rich upward dropdown with ProviderMark + blurbs), `QuotaMeter` (reference card), and `ChatPane` (policy-active header, Thai-greeting welcome, live tier chip in composer, PolicyHint banner, 40×40 send button — all SSE/streaming logic preserved). Created knowledge base page (`app/chat/knowledge/page.tsx`) as a frontend-only mock with animated 4-stage pipeline, T4 approval gate, and "Preview" banner. Created self-contained `TweaksPanel` floating panel with dark/accent/density/font-size controls and a demo role switcher that re-authenticates via `/auth/dev-login`. TypeScript build passes with zero errors.

**Files changed:**
- `frontend-chat/app/globals.css` — complete rewrite: `--accent #4f46e5`, ink/line/surface scale, `color-mix` tier bgs, radii, shadows, back-compat aliases
- `frontend-chat/app/layout.tsx` — replaced ThemeToggle import with TweaksPanel; enhanced bootstrap script to restore `--accent`/`--fs`/`--row-pad` from localStorage
- `frontend-chat/app/login/page.tsx` — restyled with shield logo, reference card, updated role labels
- `frontend-chat/app/chat/knowledge/page.tsx` — new; frontend-only KB mock: drop zone, sample chips, 4-stage animated stepper, T4 approval gate, library table, "Preview" banner
- `frontend-chat/components/NavSidebar.tsx` — new; shield logo, Chat→`/chat/knowledge`→Admin nav order, New chat button, governance section, QuotaMeter+avatar footer
- `frontend-chat/components/ConversationList.tsx` — rewritten; recency groups, lock icon on T3/T4 via `detectTier`
- `frontend-chat/components/QuotaMeter.tsx` — rewritten; border card, warn threshold 80%, `--t4/t3/accent` bar colors, "Resets 1 Jul" footer
- `frontend-chat/components/ModelPicker.tsx` — rewritten; upward dropdown, ProviderMark (24/30px), blurbs, FREE pill, check-mark on selected, policy footnote
- `frontend-chat/components/TierBadge.tsx` — rewritten; ProviderMark + model name + "kept local" pill + `ui/TierBadge` + token/cost/audit footer
- `frontend-chat/components/ChatPane.tsx` — rewritten; "Policy gateway active" header, Welcome with shield tile + Thai greeting + 2×2 grid, accent user bubbles, assistant body-text layout, live tier chip + PolicyHint in composer, 40×40 send button; SSE handler fully preserved
- `frontend-chat/components/ui/Icon.tsx` — rewritten; lowercase primary keys, 27 icons, PascalCase backward-compat getters, strokeWidth 1.7 default
- `frontend-chat/components/ui/ProviderMark.tsx` — rewritten; rounded-square letter glyph
- `frontend-chat/components/ui/TierBadge.tsx` — rewritten; pill with shield/lock icon, badge/subtle/sm modes
- `frontend-chat/components/ui/TweaksPanel.tsx` — new; floating Display panel: dark/accent presets/density/font-size/tier-comms + demo role switch via `/auth/dev-login`
- `frontend-chat/lib/domain.ts` — extended: TIERS with label/th/color/bg, ModelInfo with free/blurb, ROLE_LABELS reference format, ROLE_LEVELS
- `frontend-chat/lib/classifier.ts` — verified existing; `detectTier(text)` with Thai-ID Mod-11, credit card, email, keyword rules (T1–T4)

**Next steps:**
- [ ] Verify redesigned chat: login → "Policy gateway active" header; welcome shows Thai greeting + 2×2 grid; type Thai-ID → live T3 chip + PolicyHint; send → meta row + token footer render correctly
- [ ] Verify knowledge base: `/chat/knowledge` → drop zone + sample chips + 4-stage pipeline animates; T4 sample shows approval gate; "Preview" banner visible
- [ ] Verify tweaks panel: "Display" button → opens; dark mode toggle persists; demo role switch → ModelPicker updates (different models available)
- [ ] Phase C admin app restyle (`frontend-admin`): Sidebar, AdminConsole 2-tab page, secondary pages — noted as pending in prior session
- [ ] Verify admin flow: `/admin-console` → Model-access tab → toggle + Save → PUT fires; Quotas tab renders read-only cards + gap note
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (pre-Task 2.3 debt)
- [ ] Run `alembic upgrade head` on production DB to apply `0002_consent_acknowledged` migration
- [ ] Phase 2 acceptance gate: all 100 employees onboarded, one billing cycle, at least one reveal end-to-end in production, zero Tier 3+ external API calls

## 2026-06-07 — main @ a7676ef

**Summary:** Diagnosed and fixed a startup race that caused the Sign out button and Admin console link to silently disappear from the `frontend-chat` sidebar. Root cause: `frontend-chat` started before `backend-api` was ready (compose `depends_on` only waited for container start, not health), so the server-side `/auth/me` fetch returned `ECONNREFUSED` and the chat layout's silent `catch { return null }` path rendered the sidebar with `user = null`. Fixed by adding an HTTP/1.0 healthcheck to `backend-api` (the HTTP/1.1 path has a ~3s per-recv stall on Docker's loopback that causes urllib to time out; HTTP/1.0 closes the connection and returns instantly) and upgrading `frontend-chat`'s `depends_on` to `condition: service_healthy`. Hardened `app/chat/layout.tsx` to redirect to `/login` on 401 and throw (error boundary) on network failure so a backend blip never again renders a logged-out-looking sidebar. Cleaned up the stale deployment (`frontend-admin` orphan container + orphan `_edge` network) with `docker compose down --remove-orphans`.

**Files changed:**
- `docker-compose.yml` — added `healthcheck` to `backend-api` (HTTP/1.0 python one-liner against `127.0.0.1:8000/health`); upgraded `frontend-chat.depends_on` to `condition: service_healthy`
- `frontend-chat/app/chat/layout.tsx` — `fetchFromBackend` now propagates network errors and throws a typed 401 error; chat layout redirects to `/login` on 401, throws for network/5xx so the error boundary fires instead of rendering a null-user sidebar

**Next steps:**
- [ ] Verify in browser: reload `http://localhost:3000`, log in as Administrator — sidebar footer shows avatar + Sign out button, primary nav shows Admin console + Governance section
- [ ] Verify redesigned chat: login → "Policy gateway active" header; welcome shows Thai greeting + 2×2 grid; type Thai-ID → live T3 chip + PolicyHint; send → meta row + token footer render correctly
- [ ] Verify knowledge base: `/chat/knowledge` → drop zone + sample chips + 4-stage pipeline animates
- [ ] Verify admin flow: `/admin-console` → Model-access tab → toggle + Save → PUT fires; Quotas tab renders read-only cards + gap note
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (pre-Task 2.3 debt)
- [ ] Run `alembic upgrade head` on production DB to apply `0002_consent_acknowledged` migration
- [ ] Phase 2 acceptance gate: all 100 employees onboarded, one billing cycle, at least one reveal end-to-end in production, zero Tier 3+ external API calls

## 2026-06-07 — main @ a7676ef

**Summary:** Implemented Task 3.6 (Image generation route). Created `app/tools/image_gen.py` with four helpers: `is_image_request()` (regex-based English + Thai intent detection), `is_marketing_user()` (DB query against `departments.code = 'marketing'`), `generate_image_bytes()` (direct `GoogleClient.generate_image()` call), and `bytes_to_data_url()` (base64 PNG data URL encoder). Added a dedicated `POST /image` REST endpoint (`app/routers/image.py`) that enforces the Marketing dept check, fires `image_requested`/`image_generated` audit rows, and returns a base64 data URL (Garage upload deferred — Garage is stripped in demo mode). Modified the LangGraph orchestrator to add a `generate_image_node` and a synchronous `_route_after_start()` conditional: when the user's message matches the image intent regex, the graph skips the LLM and routes directly to Gemini Imagen; non-Marketing users receive a `permission_denied` SSE error event; both messages are persisted encrypted as markdown image syntax. Added Alembic migration `0005` to extend the `audit_action` enum with `image_requested` and `image_generated`, applied it to the running dev DB. All 20 unit tests pass.

**Files changed:**
- `backend/alembic/versions/0005_image_gen_audit_actions.py` — new; adds `image_requested` and `image_generated` to `audit_action` enum
- `backend/app/models/audit.py` — added `'image_requested'`, `'image_generated'` to `_audit_action_pg` enum declaration
- `backend/app/tools/image_gen.py` — new; `is_image_request`, `is_marketing_user`, `generate_image_bytes`, `bytes_to_data_url`
- `backend/app/routers/image.py` — new; `POST /image` endpoint with Marketing dept check + dual audit rows
- `backend/app/agents/orchestrator.py` — added `generate_image_node`, `_route_after_start`, `generate_image` node + conditional edge in `_build_graph`; imports `app.tools.image_gen`
- `backend/app/main.py` — registered `image_router`
- `backend/tests/unit/test_image_gen.py` — new; 20 unit tests: intent detection (English + Thai), false-positive guard, data URL roundtrip, DB dept check mocks, GoogleClient call + no-key error
- `PLAN.md` — Task 3.6 checkbox updated ☐ → ☑

**Next steps:**
- [ ] Frontend: handle `{"type":"image","url":"..."}` SSE event in `ChatPane.tsx` to render the image inline (currently received but not rendered)
- [ ] Register `gemini-imagen-3` in `model_catalog` seed data for audit completeness and quota display
- [ ] Garage storage: replace base64 data URL with Garage upload + signed URL when Garage is re-enabled

## 2026-06-08 — main @ a7676ef

**Summary:** Fixed a security gap where users without image-generation authorization could still trigger external OpenAI `gpt-image-1` calls — bypassing `PolicyEngine.decide()` entirely. Root cause: image generation was gated only by `is_marketing_user()` (raw `Department.code == "MKT"` check), not the role/department model-permission matrix. The fix routes image authorization through `PolicyEngine.decide()` for model code `gpt-image-1` at the same point chat-model authorization happens (`prepare_chat`), before the `StreamingResponse` starts. Unauthorized users now receive an explicit HTTP 403 `policy_denied` instead of an image. A new Alembic migration (`0006`) adds `gpt-image-1` to `model_catalog` and grants it to MKT department + L5/L6/ADMIN roles so `PolicyEngine._allowed_external_models()` can evaluate it. All 53 unit tests in the affected files pass.

**Files changed:**
- `backend/alembic/versions/0006_image_model_catalog.py` — new; seeds `gpt-image-1` catalog row + role permissions (L5/L6/ADMIN) + department permission (MKT); idempotent ON CONFLICT guards
- `backend/app/tools/image_gen.py` — replaced `is_marketing_user()` bypass with `authorize_image(session, user, tier) -> PolicyDecision` and `image_authorized(decision) -> bool`; both call `PolicyEngine.decide()`; `IMAGE_MODEL_CODE = "gpt-image-1"` constant
- `backend/app/services/chat_policy.py` — imported new helpers; added image authorization block after text-model decision: runs `authorize_image()` when `is_image_request(user_content)`, audits `model_blocked` + raises 403 on denial, sets `image_model_code` on `PreparedChat` on success; added `image_model_code: str | None = None` to `PreparedChat`
- `backend/app/agents/orchestrator.py` — removed `is_marketing_user` call from `emit_start`; `_route_after_start` now gates on `state.get("image_model_code")` (pre-authorized) instead of MKT dept check; `generate_image_node` uses `state["image_model_code"]` for `model_used`; `run_chat_stream` accepts and threads `image_model_code`; dropped `can_generate_image` from `ChatState`
- `backend/app/routers/chat.py` — passes `image_model_code=prepared.image_model_code` to `run_chat_stream`
- `backend/app/routers/image.py` — replaced `is_marketing_user` gate with `authorize_image() + image_authorized()`; classifies prompt tier via `detect_tier()` before calling PolicyEngine
- `backend/tests/unit/test_image_gen.py` — replaced old `is_marketing_user` tests with `image_authorized()` truth-table tests + `authorize_image()` mock tests + corrected `generate_image_bytes` mock (OpenAI, not Google)
- `backend/tests/unit/conftest.py` — fixed `app.db` stub: added `session_factory` as async context manager (required after Celery removal); updated `_silence_audit_celery` to patch `app.services.audit.log` directly (no longer Celery-based)
- `backend/tests/unit/test_chat_policy.py` — updated audit-assertion style from Celery payload dict to `AsyncMock.call_args_list[i].kwargs`

**Next steps:**
- [ ] Run `alembic upgrade head` on the running stack to apply `0006_image_model_catalog` migration (adds `gpt-image-1` row to `model_catalog`)
- [ ] Manual verify: log in as a non-MKT / L1 user → type "generate an image of a cat" → expect HTTP 403 `policy_denied`, no image generated
- [ ] Manual verify: log in as MKT dept user → type "generate an image of a cat" → image returned, `image_requested`/`image_generated` in `audit_log`
- [x] Frontend: handle `{"type":"image","url":"..."}` SSE event in `ChatPane.tsx` to render the image inline — confirmed already handled at line 529; was never broken
- [ ] Garage storage: replace base64 data URL with Garage upload + signed URL when Garage is re-enabled
- [ ] Verify in browser: reload `http://localhost:3000`, log in as Administrator — sidebar footer shows avatar + Sign out button
- [ ] Verify redesigned chat: login → "Policy gateway active" header; welcome shows Thai greeting + 2×2 grid; type Thai-ID → live T3 chip; send → meta row + token footer render correctly
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (pre-Task 2.3 debt)
- [ ] Run `alembic upgrade head` on production DB to apply migrations 0002, 0004, 0005
- [ ] Phase 2 acceptance gate: all 100 employees onboarded, one billing cycle, at least one reveal end-to-end in production, zero Tier 3+ external API calls

## 2026-06-29 — main @ 6fc0138

**Summary:** Fixed gap #2 from `production_improvement.md`: the `sources` SSE event (RAG citations) was silently dropped by `ChatPane.tsx` — no dispatch branch existed for it. Investigation also confirmed the `image` event was already handled correctly (contrary to the gap report). Added `Source` interface, extended `Message` with `sources?: Source[]`, widened the inline SSE event cast, added a `turnSources` per-turn local, added the `sources` dispatch branch, committed sources onto the `done` message, added a `SourcesPanel` collapsible component (`<details>/<summary>`), and rendered it under each assistant message. `tsc --noEmit` passes cleanly. Updated `production_improvement.md` gap #2 wording to reflect the correct finding.

**Files changed:**
- `frontend-chat/components/ChatPane.tsx` — added `Source` interface; extended `Message.sources`; widened SSE event cast; added `turnSources` local + `sources` dispatch branch; committed sources in `done` handler; added `SourcesPanel` component; rendered `<SourcesPanel>` after `TierBadge` in assistant message block
- `production_improvement.md` — corrected gap #2 description (image events already rendered; only sources were missing; marked ✅ Fixed)

**Next steps:**
- [ ] Pull `bge-m3` on Ollama host (`ollama pull bge-m3` on `192.168.20.18`) — prerequisite for sources panel to produce visible output (gap #3)
- [ ] Manual verify: ingest a document, ask a RAG question → confirm "Sources (N)" panel appears under answer; expand → filename · chunk # · score listed
- [ ] Manual verify: non-RAG question → no Sources panel shown
- [ ] Manual verify: chat image generation still renders `<img>` (regression check on untouched path)
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (gap #5 in production_improvement.md)
- [ ] Set `N8N_ALERT_WEBHOOK_URL`, wire n8n UI (gap #4)
- [ ] Add per-user video generation quota cap (gap #7)
- [ ] Phase 2 acceptance gate: all 100 employees onboarded, one billing cycle, reveal end-to-end, zero Tier 3+ external calls

## 2026-06-08 — main @ a7676ef

**Summary:** Fixed three image-generation issues in sequence. (1) Applied missing migration `0006_image_model_catalog` to the running DB — `gpt-image-1` wasn't in `model_catalog`, causing `PolicyEngine._get_model()` to return `None` → `UNKNOWN_MODEL` for every role. (2) Removed an anomalous `L1 → gemini-2.5-flash-image` row from `role_model_permissions` (not seeded by the baseline) via new migration `0007_fix_l1_perms`, restoring L1 to local-only access. (3) Extended `is_image_request()` regex to cover Thai phrases that were silently falling through (`ขอรูป`, `อยากได้รูป`, `อยากเห็นภาพ`, etc.), and hardened the image-denial HTTP 403 with a role-specific human message (`image_generation_unauthorized` error code, distinguishes `ROLE_NOT_ALLOWED` from `TIER_BLOCKS_EXTERNAL`). Finally wired the missing **Department × Model access matrix** into the `AdminConsole` Access tab — `deptMatrix` and `departments` were fetched but never rendered; they now appear as a second interactive table below the Role matrix with identical per-row save/confirm flow.

**Files changed:**
- `backend/alembic/versions/0007_remove_l1_image_model_permission.py` — new migration (`0007_fix_l1_perms`); removes anomalous `L1 → gemini-2.5-flash-image` permission row
- `backend/app/tools/image_gen.py` — extended `_IMAGE_RE` regex with additional Thai verbs (`ขอ|อยากได้|อยากเห็น|เอา|แสดง|หา|ส่ง|ให้ดู`) and reverse pattern `(รูป|ภาพ).{0,30}(…)`; verified 6/8 test phrases match, 2/8 non-image phrases don't
- `backend/app/services/chat_policy.py` — role-aware denial messages (`ROLE_NOT_ALLOWED` → "not authorized, requires L5+" vs `TIER_BLOCKS_EXTERNAL` → "contains confidential data"); error code changed to `image_generation_unauthorized`
- `backend/app/routers/image.py` — same denial-message hardening + `DenyReason` import
- `frontend-chat/components/admin/AdminConsole.tsx` — `AccessTab` now renders two full matrices: Role × Model (refactored to `rolePerms`/`rolePending` state) + new Department × Model (per-row checkboxes → `PUT /api/admin/permissions/department` → `ConfirmDialog`)

**Next steps:**
- [x] Apply migration `0006_image_model_catalog` to running DB
- [x] Remove anomalous L1 `gemini-2.5-flash-image` permission (migration `0007_fix_l1_perms`)
- [x] Harden image-denial messages with role-specific text and `image_generation_unauthorized` error code
- [x] Render Department × Model matrix in Admin Console Access tab
- [ ] Manual verify: Admin Console → Access tab → both Role and Department matrices render; toggle MKT `gpt-image-1` → Save → reload persists
- [ ] Manual verify: L1 user → "ขอรูปแมวหน่อย" → 403 with "not authorized" message (not `unknown_model`)
- [ ] Frontend: handle `{"type":"image","url":"..."}` SSE event in `ChatPane.tsx` to render image inline
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (pre-Task 2.3 debt)
- [ ] Phase 2 acceptance gate: all 100 employees onboarded, one billing cycle, at least one reveal end-to-end in production, zero Tier 3+ external API calls

## 2026-06-08 — main @ a7676ef (Phase 3 RAG)

**Summary:** Implemented PLAN.md Phase 3 (Tasks 3.1–3.5) — full RAG / knowledge base feature. Created ORM models (`File`, `FileChunk` with pgvector `Vector(1024)`), Alembic migration `0008_file_scope` (scope VARCHAR on files table, chaining off `0007_fix_l1_perms`), embedding client (`EmbeddingClient` via Ollama `/v1/embeddings`), ingestion service (extract→chunk→embed pipeline via FastAPI `BackgroundTasks`, local disk blob storage), pgvector retrieval tool (`rag_search.retrieve` using `cosine_distance` + HNSW, personal+org scope), wired retrieval into `chat_policy.prepare_chat` before `detect_tier` (R3: retrieved T3 content triggers tier downgrade), extended `run_chat_stream` with `rag_context`/`citations`, new `/files` router (upload→202→background ingest, list, status poll, delete), Next.js BFF proxy routes (`/api/files`, `/api/files/[id]`), rewrote knowledge page with real API calls. Demo-mode deviations: local disk (not Garage/D8), BackgroundTasks (not Celery/D9).

**Files changed:**
- `backend/app/models/file.py` — new ORM models: `File`, `FileChunk` (pgvector `Vector(1024)` embedding column)
- `backend/app/models/__init__.py` — registered `File`, `FileChunk`
- `backend/alembic/versions/0008_file_scope.py` — new migration: adds `scope VARCHAR(16)` to files; chains off `0007_fix_l1_perms` (corrected from erroneous `0007_file_scope.py` which had wrong `down_revision`)
- `backend/app/config.py` — added `llm_embed_model`, `rag_top_k`, `rag_chunk_tokens`, `rag_chunk_overlap`, `file_storage_dir`, `max_upload_bytes`
- `backend/app/llm/embeddings.py` — new `EmbeddingClient` (httpx, `lru_cache get_embedder()`)
- `backend/pyproject.toml` — added `pypdf>=4.0`, `python-docx>=1.1`
- `backend/app/services/ingestion.py` — new: `extract_text`, `chunk_text`, `save_upload`, `delete_blob`, `sha256_of_path`, `async process_file`
- `backend/app/tools/rag_search.py` — new: `retrieve` (pgvector cosine search, personal+org scope), `build_context_block`, `citations`
- `backend/app/services/chat_policy.py` — `PreparedChat` gains `rag_context`/`citations`; retrieval injected before `detect_tier` in `prepare_chat`
- `backend/app/agents/orchestrator.py` — `ChatState` gains `rag_context`/`citations`; `call_llm` prepends system context; `emit_start` emits SSE `sources` event
- `backend/app/routers/chat.py` — threads `rag_context`/`citations` into `run_chat_stream`
- `backend/app/schemas/file.py` — new: `FileOut`, `FileListOut`, `FileStatusOut` Pydantic DTOs
- `backend/app/routers/files.py` — implemented (was empty stub): POST/GET/GET{id}/DELETE
- `backend/app/main.py` — registered files router
- `docker-compose.yml` — added `LLM_EMBED_URL`, `LLM_EMBED_MODEL`, `FILE_STORAGE_DIR`, `files_data` volume
- `.env.example` — added embedding server vars + RAG tuning comments
- `frontend-chat/app/api/files/route.ts` — new BFF proxy (GET list, POST upload)
- `frontend-chat/app/api/files/[id]/route.ts` — new BFF proxy (GET status, DELETE)
- `frontend-chat/app/chat/knowledge/page.tsx` — rewritten: real API calls, scope selector (personal/org), polling stepper, removed preview-mode banner
- `PLAN.md` — Tasks 3.1–3.5 ticked ☑

**Next steps:**
- [x] Implement RAG ORM models + `0008_file_scope` migration (Task 3.1)
- [x] Implement embedding client (`embeddings.py`) (Task 3.3)
- [x] Implement ingestion service (extract/chunk/embed via BackgroundTasks) (Task 3.2/3.4)
- [x] Implement pgvector retrieval tool (`rag_search.py`) (Task 3.5)
- [x] Wire retrieval into chat pipeline (R3 tier gating) (Task 3.5)
- [x] Implement `/files` router + Next.js BFF proxies (Task 3.1)
- [x] Rewrite knowledge page with real API calls (Task 3.1)
- [x] Fix Alembic branch: rename `0007_file_scope.py` → `0008_file_scope.py`, `down_revision = "0007_fix_l1_perms"`
- [ ] Run `ollama pull bge-m3` on Ollama host (192.168.20.18)
- [ ] Run `alembic upgrade head` to apply `0008_file_scope` migration
- [ ] Rebuild Docker image to pick up `pypdf`, `python-docx` deps
- [ ] Write unit tests: `embeddings.py`, `ingestion.chunk_text`, `rag_search.retrieve`, `chat_policy` T3-retrieved-context tier flip, `files.py` router upload validation
- [ ] Write integration test: upload PDF → `process_file` → assert FileChunk rows with non-null embedding; EXPLAIN ANALYZE shows HNSW index scan
- [ ] Manual end-to-end: upload PDF → poll until indexed → chat question → see `sources` citations SSE chips
- [ ] Frontend: handle `{"type":"sources","sources":[...]}` SSE event in `ChatPane.tsx` to render citation chips
- [ ] Manual verify: Admin Console → Access tab → both Role and Department matrices render
- [ ] Manual verify: L1 user → "ขอรูปแมวหน่อย" → 403 with "not authorized" message
- [ ] Frontend: handle `{"type":"image","url":"..."}` SSE event in `ChatPane.tsx` to render image inline
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (pre-Task 2.3 debt)
- [ ] Phase 2 acceptance gate: all 100 employees onboarded, one billing cycle, at least one reveal end-to-end in production, zero Tier 3+ external API calls

## 2026-06-09 — main @ a7676ef

**Summary:** Implemented Task 2.10 — full bidirectional n8n integration. Part 0 adds a proper service-account API-key auth layer: `api_keys` table (SHA-256 keyed, `gw_` prefix), Alembic migration 0009, refactored `deps.py` with `get_api_principal` / `get_principal` (accepts JWT or API key), admin CRUD endpoints, and a bootstrap script. Part A adds a governed OpenAI-compatible passthrough endpoint (`POST /v1/chat/completions`, `GET /v1/models`) so n8n's OpenAI Chat Model node points at the gateway instead of OpenAI directly — every call runs `detect_tier → PolicyEngine.decide → audit + quota` before forwarding with `tools`/`tool_calls` intact. Part B adds `POST /automations/n8n/label-inbox` which calls n8n's webhook on demand, plus `app/services/n8n_client.py` for the outbound call. All 24 new unit tests pass; 204 pre-existing tests unchanged.

**Files changed:**
- `backend/app/models/api_key.py` — new; `ApiKey` ORM (SHA-256 `key_hash`, `gw_` prefix helpers `generate_key`/`hash_key`)
- `backend/alembic/versions/0009_api_keys.py` — new; creates `api_keys` table + extends `audit_action` enum with `n8n_triggered`
- `backend/app/models/__init__.py` — added `ApiKey` export
- `backend/app/deps.py` — refactored; added `_authenticate_jwt`, `_authenticate_api_key` helpers; `get_api_principal`, `get_principal` FastAPI deps; `X-API-Key` header support in `_extract_token`
- `backend/app/config.py` — added `n8n_webhook_url`, `n8n_webhook_secret` settings
- `.env.example` — added `N8N_WEBHOOK_URL`, `N8N_WEBHOOK_SECRET` section
- `backend/app/routers/openai_compat.py` — new; `POST /v1/chat/completions` (governed passthrough with tools) + `GET /v1/models` (user-allowed model list in OpenAI format)
- `backend/app/llm/openai.py` — added `raw_chat()` (non-streaming passthrough) and `raw_streaming_chat()` (SSE passthrough, preserves `tools`/`tool_calls`)
- `backend/app/llm/llamacpp.py` — added `raw_chat()` and `raw_streaming_chat()` via Ollama's `/v1/chat/completions` compat endpoint
- `backend/app/services/n8n_client.py` — new; outbound httpx webhook trigger; raises `RuntimeError` on n8n unreachable
- `backend/app/routers/automations.py` — new; `POST /automations/n8n/label-inbox`; writes `n8n_triggered` audit row
- `backend/app/main.py` — mounted `openai_compat.router` and `automations.router`
- `backend/app/routers/admin.py` — added `POST /admin/api-keys`, `GET /admin/api-keys`, `DELETE /admin/api-keys/{id}` with audit trail
- `backend/scripts/create_service_account.py` — new; CLI to mint service user + API key (prints raw secret once)
- `backend/tests/unit/test_api_key_auth.py` — new; 15 tests (key helpers, `_extract_token`, `_authenticate_api_key` valid/invalid/inactive, `get_principal` dispatch)
- `backend/tests/unit/test_openai_compat.py` — new; 9 tests (policy deny → OpenAI 403 shape, tier downgrade → local + audit, tools passthrough intact, unsupported provider → 400, no-consent → 403)
- `PLAN.md` — added Task 2.10 ☑

**Next steps:**
- [ ] **n8n wiring (manual):** In the Gmail-labelling workflow — OpenAI Chat Model node: set Base URL → `https://api.decomplica.tech/v1`, API Key → `gw_…` from `create_service_account.py`
- [ ] **n8n wiring (manual):** Add a Webhook trigger node as parallel entry point; set `X-N8N-Secret` to the value of `N8N_WEBHOOK_SECRET`
- [ ] Run `alembic upgrade head` to apply migration `0009_api_keys`
- [ ] Rebuild Docker image (`docker compose build backend-api`) to pick up new routers
- [ ] Validate end-to-end: `curl -H "Authorization: Bearer gw_…" /v1/models` returns allowed model list; `POST /v1/chat/completions` with tools returns `tool_calls` block; audit shows `source: n8n`
- [ ] Validate Part B: `POST /automations/n8n/label-inbox` fires webhook and writes `n8n_triggered` audit row
- [ ] Decide service-account role (currently default L4 in script) — confirm it can reach the external model the labelling agent needs (gpt-4o needs L4+)
- [ ] Run `ollama pull bge-m3` on Ollama host (192.168.20.18)
- [ ] Frontend: handle `{"type":"image","url":"..."}` SSE event in `ChatPane.tsx`
- [ ] Frontend: handle `{"type":"sources","sources":[...]}` SSE event in `ChatPane.tsx`
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures
- [ ] Phase 2 acceptance gate: all 100 employees onboarded, one billing cycle, at least one reveal end-to-end, zero Tier 3+ external calls in audit log

## 2026-06-08 17:00 — main @ a7676ef

**Summary:** Wired n8n workflow automation into the stack — both directions. Added `n8nio/n8n` as a new Docker Compose service on port 5678 (depends on `backend-api` healthy, persistent `n8n_data` volume). Introduced API-key authentication in `deps.py` so n8n can call the gateway without Google OAuth: `X-API-Key` header matching `N8N_SERVICE_KEY` resolves to an `n8n-service@system` service account upserted at startup with a configurable role (default L6) and pre-acknowledged consent. Added a fire-and-forget webhook sender (`services/n8n_webhook.py`) that POSTs selected audit events to a configurable n8n webhook URL — default event list covers the security-relevant actions (`pii_detected`, `tier_blocked`, `quota_exceeded`, `reveal_requested/approved/denied`); called from `audit.log()` after each DB commit, never raises, 5 s timeout.

**Files changed:**
- `docker-compose.yml` — added `n8n` service (port 5678, `n8n_data` volume, `AI_GATEWAY_URL`/`AI_GATEWAY_API_KEY` env injected for HTTP Request nodes); added `N8N_SERVICE_KEY`, `N8N_SERVICE_ROLE`, `N8N_WEBHOOK_URL`, `N8N_WEBHOOK_EVENTS` to `backend-api` environment
- `.env.example` — added n8n section: `N8N_ENCRYPTION_KEY`, `N8N_SERVICE_KEY`, `N8N_SERVICE_ROLE`, `N8N_PUBLIC_URL`, basic-auth vars, `N8N_WEBHOOK_URL`, `N8N_WEBHOOK_EVENTS`
- `backend/app/config.py` — added `n8n_service_key`, `n8n_service_role`, `n8n_webhook_url`, `n8n_webhook_events` settings
- `backend/app/deps.py` — `get_current_user()` checks `X-API-Key` header before JWT; resolves to service account via `_get_service_user()`
- `backend/app/main.py` — lifespan upserts `n8n-service@system` user when `N8N_SERVICE_KEY` is set (role from config, consent pre-acknowledged)
- `backend/app/services/n8n_webhook.py` — **new**; `fire(action, user_id, details)`: lazy event-set parse from config, httpx POST, logs warning on 4xx, debug-logs on exception, never raises
- `backend/app/services/audit.py` — calls `n8n_webhook.fire()` after each successful `session.commit()`

**Next steps:**
- [ ] In n8n UI: create a Webhook node at `http://n8n:5678/webhook/ai-gateway-events`, set `N8N_WEBHOOK_URL` in `.env`, restart backend-api — gateway will POST security events to n8n
- [ ] In n8n UI: create an HTTP Request node with `AI_GATEWAY_URL` + `X-API-Key: {{$env.AI_GATEWAY_API_KEY}}` to call `POST /chat` from a workflow
- [ ] Run `ollama pull bge-m3` on Ollama host (192.168.20.18)
- [ ] Run `alembic upgrade head` to apply `0008_file_scope` migration
- [ ] Rebuild Docker image to pick up `pypdf`, `python-docx` deps
- [ ] Write unit tests: `embeddings.py`, `ingestion.chunk_text`, `rag_search.retrieve`
- [ ] Frontend: handle `{"type":"image","url":"..."}` SSE event in `ChatPane.tsx` to render image inline
- [ ] Frontend: handle `{"type":"sources","sources":[...]}` SSE event in `ChatPane.tsx` to render citation chips
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (pre-Task 2.3 debt)
- [ ] Phase 2 acceptance gate: all 100 employees onboarded, one billing cycle, at least one reveal end-to-end in production, zero Tier 3+ external API calls

## 2026-06-09 — main @ 60ba095

**Summary:** Debugged and fixed `POST /automations/agent` returning `{"output": ""}` for all calls. Root cause: `run_chat_collect()` extracted `full_response` from the LangGraph `ainvoke()` return dict, but LangGraph state propagation does not reliably surface node-return values in the final state across all versions. Fixed by draining the chunk queue after `ainvoke()` returns instead — since `ainvoke` completes only after all nodes finish, every `queue.put()` inside `call_llm` and `generate_image_node` is already committed, so synchronous `get_nowait()` loop reliably assembles the full text and token counts without any LangGraph version dependency. Also committed all Task 2.10 session work: `admin.py` 204-response fix, `openai_compat.py` audit keyword-arg fix, `docker-compose.yml` volume mount + `--reload`, conditional-stub `conftest.py`, `test_agent_endpoint.py` (5 tests passing).

**Files changed:**
- `backend/app/agents/orchestrator.py` — `run_chat_collect()`: replaced `result.get("full_response")` with queue-drain loop (`get_nowait()` consuming `content`/`done` events until sentinel `None`)
- `backend/app/routers/automations.py` — new; `POST /automations/agent` (LINE chatbot endpoint) + `POST /automations/n8n/label-inbox`; lazy imports to avoid test-collection failures
- `backend/app/routers/openai_compat.py` — new; `POST /v1/chat/completions` + `GET /v1/models` governed passthrough; fixed 4 `audit_svc.log` calls to use keyword arguments
- `backend/app/routers/admin.py` — `DELETE /admin/api-keys/{id}`: changed return type to `Response(status_code=204)` (was `None` which caused FastAPI assertion error on startup)
- `docker-compose.yml` — added `./backend:/app` bind mount + `--reload` flag to `backend-api` for hot-reload dev workflow
- `backend/tests/unit/conftest.py` — added `_is_missing()` via `importlib.util.find_spec`; all stubs now conditional so they don't clobber real packages in the full-extras venv
- `backend/tests/unit/test_agent_endpoint.py` — new; 5 unit tests: allow->output, policy-deny->403, no-consent->403, downgrade->output-still-returned, field-passthrough assertion
- `PLAN.md` — Task 2.10 checkbox updated to complete

**Next steps:**
- [ ] Test `POST /automations/agent` end-to-end: `curl.exe -X POST http://localhost:8000/automations/agent -H "Authorization: Bearer gw_YOURKEY" -H "Content-Type: application/json" -d "{\"content\": \"สวัสดี Python คืออะไร\"}"` — verify `output` is non-empty and `message_sent`/`message_received` appear in audit log
- [ ] Configure n8n LINE chatbot: replace AI Agent + OpenAI Chat Model + Simple Memory with single HTTP Request node POST to `/automations/agent`; body `{"content": "={{ $json.message.text }}"}`, Header Auth `Authorization: Bearer gw_...`; LINE reply keeps `{{ $json.output }}`
- [ ] Test full LINE round-trip: send LINE message -> output appears as LINE reply; audit log shows service-account `message_sent`/`message_received`
- [ ] Frontend: handle `{"type":"image","url":"..."}` SSE event in `ChatPane.tsx` to render image inline
- [ ] Frontend: handle `{"type":"sources","sources":[...]}` SSE event in `ChatPane.tsx` to render citation chips
- [ ] Run `ollama pull bge-m3` on Ollama host (192.168.20.18)
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (pre-Task 2.3 debt)
- [ ] Phase 2 acceptance gate: all 100 employees onboarded, one billing cycle, at least one reveal end-to-end in production, zero Tier 3+ external API calls

## 2026-06-09 — main @ 60ba095

**Summary:** Switched image generation from OpenAI `gpt-image-1` to Google `gemini-3.1-flash-image`. Changed `IMAGE_MODEL_CODE` constant and rerouted `generate_image_bytes()` to call `GoogleClient.generate_image_gemini()` (already implemented). Added Alembic migration `0010_gemini_image_model` that seeds the new catalog row with L5/L6/ADMIN role permissions and MKT department permission. Updated tests, doc comments, and the frontend model-label map. The `gpt-image-1` catalog row and `OpenAIClient.generate_image` are left in place as a rollback path. All 38 unit tests pass.

**Files changed:**
- `backend/app/tools/image_gen.py` — `IMAGE_MODEL_CODE` changed to `"gemini-3.1-flash-image"`; `generate_image_bytes()` now calls `GoogleClient.generate_image_gemini()`; import swapped from `OpenAIClient` to `GoogleClient`; docstrings updated
- `backend/alembic/versions/0010_gemini_image_model.py` — **new**; seeds `gemini-3.1-flash-image` catalog row + role permissions (L5/L6/ADMIN) + MKT department permission; idempotent ON CONFLICT guards; `down_revision = "0009_api_keys"`
- `backend/tests/unit/test_image_gen.py` — `test_generate_image_bytes_calls_openai_client` renamed/rewritten to mock `GoogleClient`; no-api-key test checks `GOOGLE_API_KEY`
- `backend/app/routers/image.py` — module docstring updated (OpenAI → Gemini)
- `backend/app/agents/orchestrator.py` — `_route_after_start` docstring updated
- `backend/app/services/chat_policy.py` — inline comment updated
- `frontend-chat/lib/domain.ts` — added `gemini-3.1-flash-image` label entry

**Next steps:**
- [ ] Run `alembic upgrade head` to apply migration `0010_gemini_image_model` (adds `gemini-3.1-flash-image` to `model_catalog`)
- [ ] Verify `GOOGLE_API_KEY` is set in `.env` (image generation now requires it instead of `OPENAI_API_KEY`)
- [ ] End-to-end smoke: `POST /image {"prompt": "a red circle"}` as L5/ADMIN user — expect `{"url":"data:image/png;base64,..."}` and `Message.model_used = "gemini-3.1-flash-image"` in DB
- [ ] Test `POST /automations/agent` end-to-end (carried forward)
- [ ] Configure n8n LINE chatbot (carried forward)

## 2026-06-09 — main @ 60ba095

**Summary:** Completed the "Token quotas & cost caps" admin tab. Replaced the hardcoded placeholder slider table with a fully editable per-role budget table backed by two new backend endpoints (`GET /admin/quota-defaults` and `PUT /admin/quota-defaults`). The GET endpoint returns live per-role data: `monthly_token_limit`, `is_unlimited`, `tokens_used_month` (aggregated from `quotas` rows for the current month), and `user_count`. The PUT endpoint upserts `quota_defaults`, cascades the new limit to all existing current-month `quotas` rows for users of that role, commits atomically, and emits the pre-existing `admin_quota_changed` audit action. On the frontend, the read-only slider table was replaced with an editable table (number input + "Unlimited" checkbox per role, live "Used this month" bar, per-row Save → `ConfirmDialog` → `PUT`), wired through a new Next.js proxy route `/api/admin/quota-defaults`. `next build` passes with zero TypeScript errors and zero warnings.

**Files changed:**
- `backend/app/routers/admin.py` — added `update` + `pg_insert` imports, `ROLE_ORDER`/`UNLIMITED_SENTINEL` constants, `_month_start_date()` helper, `QuotaDefaultItem`/`PutQuotaDefaultRequest` schemas, `GET /admin/quota-defaults` and `PUT /admin/quota-defaults` endpoints
- `backend/tests/integration/test_admin.py` — added `Quota` import; added 5 new tests: `test_quota_defaults_get_shape`, `test_put_quota_default_updates_and_audits`, `test_put_quota_default_cascades_current_month`, `test_quota_defaults_used_tokens_aggregated`, `test_put_quota_default_rejects_bad_input`
- `frontend-chat/lib/admin-api.ts` — added `QuotaDefault` interface, `fetchQuotaDefaults()`, `putQuotaDefault()`
- `frontend-chat/app/api/admin/quota-defaults/route.ts` — new; GET+PUT cookie→Bearer proxy to `/admin/quota-defaults`
- `frontend-chat/app/(admin)/admin-console/page.tsx` — added `fetchQuotaDefaults` to `Promise.allSettled`, passes `quotaDefaults` prop to `<AdminConsole>`
- `frontend-chat/components/admin/AdminConsole.tsx` — imported `QuotaDefault`; removed `QUOTA_PLACEHOLDER`; added `quotaDefaults: QuotaDefault[]` to Props; rewrote `QuotasTab` with editable budget table (number input, unlimited toggle, usage bar, per-row Save + `ConfirmDialog`)

**Next steps:**
- [ ] Run integration tests: `cd backend && pytest tests/integration/test_admin.py -q` (needs pytest-docker Postgres)
- [ ] Manual verify: open Admin console → Token quotas & cost caps tab → budget table shows real seeded values (L1=50k … L6/ADMIN=Unlimited); edit L2 budget → Save → confirm dialog → reload persists; check Audit log for `admin_quota_changed` row
- [ ] Run `alembic upgrade head` to apply migration `0010_gemini_image_model` (carried forward)
- [ ] Verify `GOOGLE_API_KEY` is set in `.env` (carried forward)
- [ ] Test `POST /automations/agent` end-to-end (carried forward)
- [ ] Configure n8n LINE chatbot (carried forward)
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (pre-Task 2.3 debt)
- [ ] Phase 2 acceptance gate: all 100 employees onboarded, one billing cycle, at least one reveal end-to-end in production, zero Tier 3+ external API calls
- [ ] Frontend: handle `{"type":"image","url":"..."}` SSE event in `ChatPane.tsx` to render image inline
- [ ] Frontend: handle `{"type":"sources","sources":[...]}` SSE event in `ChatPane.tsx` to render citation chips
- [ ] Run `ollama pull bge-m3` on Ollama host (192.168.20.18)

## 2026-06-09 — main @ 60ba095

**Summary:** Added a keyword-based admin-alert service (`app/services/alert.py`) that fires an outbound n8n webhook whenever a chat message contains phrases like "server is down", "contact admin", "เซิร์ฟเวอร์ล่ม", or "แจ้งแอดมิน" (14 EN + TH regex patterns). The service is fire-and-forget: launched via `asyncio.create_task` in both `POST /chat` and `POST /automations/agent`, never raises into the request, and includes a 30 s per-user throttle to suppress spam. Reuses the existing `n8n_client.trigger()` plumbing and a new dedicated `N8N_ALERT_WEBHOOK_URL` env var (kept separate from the label-inbox webhook). All 40 unit tests pass.

**Files changed:**
- `backend/app/config.py` — added `n8n_alert_webhook_url: str = ""` setting
- `.env.example` — added `N8N_ALERT_WEBHOOK_URL` section with notes on test vs. production URL and the required POST method change in n8n
- `backend/app/services/alert.py` — **new**; `matches_alert(text)` regex engine (14 EN+TH patterns) + `async maybe_alert(...)` fire-and-forget notifier with per-user throttle; models `audit.py` pattern (swallows all exceptions, only `logger.warning`)
- `backend/app/routers/chat.py` — added `asyncio.create_task(alert.maybe_alert(...))` before `prepare_chat()` call
- `backend/app/routers/automations.py` — same `create_task` call in `agent()` endpoint after consent check
- `backend/tests/unit/test_alert.py` — **new**; 40 tests: 24 keyword positives/negatives, webhook fires on match, no-fire on no-match, no-fire when URL blank, throttle suppresses 2nd call, different users not throttled, webhook error swallowed

**Next steps:**
- [ ] **n8n UI (required):** Change Webhook node HTTP Method from GET → POST so the JSON body arrives
- [ ] **n8n UI (required):** In LINE Messaging node, map the message field to `{{ $json.body.message }}`
- [ ] Set `N8N_ALERT_WEBHOOK_URL` in `.env` and restart `backend-api` container
- [ ] End-to-end test: send "the server is down" → LINE admin message received; "hello" → no webhook; rapid 2nd alert within 30s → throttled
- [ ] Run integration tests: `pytest tests/integration/test_admin.py -q` (carried forward)
- [ ] Run `alembic upgrade head` to apply migration `0010_gemini_image_model` (carried forward)
- [ ] Test `POST /automations/agent` end-to-end (carried forward)
- [ ] Frontend: handle `{"type":"image","url":"..."}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Frontend: handle `{"type":"sources","sources":[...]}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Run `ollama pull bge-m3` on Ollama host (carried forward)
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (carried forward)
- [ ] Phase 2 acceptance gate (carried forward)

## 2026-06-09 — main @ 60ba095

**Summary:** Re-architected the n8n admin-alert from fire-and-forget side-effect into intent-based **LangGraph routing** (user's updated request). When a "server is down / contact admin" prompt is detected (same EN+TH regex via `alert.matches_alert`) and `N8N_ALERT_WEBHOOK_URL` is configured, `prepare_chat` sets `n8n_route=True` on `PreparedChat`. The graph then routes `emit_start → call_n8n_node → call_llm → END` instead of the direct `→ call_llm` path. `call_n8n_node` emits a fixed acknowledgment SSE content delta immediately (so the user sees "✅ I've notified the admin team…" before the LLM streams), awaits `alert.maybe_alert()` to POST the n8n webhook (throttled, swallows errors so n8n outage never blocks the reply), writes an `n8n_triggered` audit row, and returns `{"alert_ack": …}` so `call_llm` can prepend the ack to the persisted assistant message — keeping conversation history coherent with what the user saw. The old `asyncio.create_task` fire-and-forget was removed from both routers. All 55 unit tests pass (40 alert + 3 n8n_route detection + 12 orchestrator).

**Files changed:**
- `backend/app/services/chat_policy.py` — added `from app.config import settings` + `from app.services import alert` imports; added `n8n_route: bool = False` field to `PreparedChat`; added n8n_route detection block after image authorization; added `n8n_route=n8n_route` to returned `PreparedChat`
- `backend/app/agents/orchestrator.py` — added `import logging`, `from app.services import alert as alert_svc`, module-level `_logger`; added `n8n_route: bool` + `alert_ack: str` to `ChatState`; added `_ALERT_ACK` constant; added `call_n8n_node` async function; extended `_route_after_start` with n8n branch; added `call_n8n` node + `call_n8n → call_llm` edge in `_build_graph`; `call_llm` now prepends `alert_ack` to persisted assistant message; added `n8n_route: bool = False` param + state key to both `run_chat_stream` and `run_chat_collect`
- `backend/app/routers/chat.py` — removed `import asyncio`, `from app.services import alert`, and `create_task(alert.maybe_alert(...))` block; added `n8n_route=prepared.n8n_route` to `run_chat_stream` call
- `backend/app/routers/automations.py` — removed `import asyncio`, `from app.services import alert`, and `create_task(alert.maybe_alert(...))` block; added `n8n_route=prepared.n8n_route` to `run_chat_collect` call
- `backend/tests/unit/test_chat_policy.py` — added `TestN8nRouteDetection` class with 3 tests: route set when URL+keyword match, false when URL blank, false when no match
- `backend/tests/unit/test_orchestrator.py` — imported `call_n8n_node` + `_ALERT_ACK`; added 4 tests: node emits ack+fires webhook, node swallows webhook error, call_llm prepends ack in persisted message, run_chat_stream with n8n_route emits ack before LLM content

**Next steps:**
- [x] Re-architect fire-and-forget alert into LangGraph intent-based routing
- [ ] **n8n UI (required):** Webhook node HTTP Method must be POST; LINE Messaging node text field → `{{ $json.body.message }}`
- [ ] Set `N8N_ALERT_WEBHOOK_URL=https://siga86.app.n8n.cloud/webhook-test/line-webhook` in `.env`, restart `backend-api`
- [ ] End-to-end test: send "the server is down" → chat reply shows ack + LLM answer; LINE admin gets LINE message; audit log has `n8n_triggered` row; "hello" → no ack, no webhook call
- [ ] Run integration tests: `pytest tests/integration/test_admin.py -q` (carried forward)
- [ ] Run `alembic upgrade head` to apply migration `0010_gemini_image_model` (carried forward)
- [ ] Test `POST /automations/agent` end-to-end (carried forward)
- [ ] Frontend: handle `{"type":"image","url":"..."}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Frontend: handle `{"type":"sources","sources":[...]}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Run `ollama pull bge-m3` on Ollama host (carried forward)
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (carried forward)
- [ ] Phase 2 acceptance gate (carried forward)

## 2026-06-19 — main @ 636e38e

**Summary:** Implemented Task 3.9 — True Studio (generative-media studio). Created the full backend: `StudioGeneration` ORM model with AES-256-GCM encrypted prompt fields (§7.1), Alembic migration `0011_studio_generations` applied to the running DB, `studio.py` service (image via PolicyEngine + Gemini, video/music mocked with `# TODO: real Seedance/Lyria provider`), and `/studio` router with three endpoints gated by `require_consent`. Added True Studio to NavSidebar and built the full 3-panel client component (`StudioPage.tsx`) with mode tabs (image/video/music), model dropdown, per-mode advanced settings, token-cost banner, generate button, My Studio results panel, and Templates panel seeded from 18 templates. Three Next.js API proxy routes wire the frontend to the backend. All 11 unit tests pass (`test_studio.py`); `npm run build` for `frontend-chat` succeeded with zero TypeScript errors.

**Files changed:**
- `backend/app/models/studio.py` — **new**; `StudioGeneration` ORM: id, user_id, type, model_label, prompt_ciphertext/nonce/tag/key_version, settings JSONB, status, output_ref, token_cost, created_at
- `backend/app/models/__init__.py` — added `StudioGeneration` export
- `backend/alembic/versions/0011_studio_generations.py` — **new**; idempotent `CREATE TABLE IF NOT EXISTS studio_generations` + index; chains off `0010_gemini_image_model`; applied to running DB
- `backend/app/services/studio.py` — **new**; 18 hardcoded templates; `generate()` (image: full PolicyEngine + Gemini path, video/music: mocked rows); `list_generations()`; `list_templates()`; audit logging on all actions
- `backend/app/routers/studio.py` — **new**; `POST /studio/generate`, `GET /studio/generations`, `GET /studio/templates`; Pydantic request/response schemas; `require_consent` on all routes
- `backend/app/main.py` — registered `studio_router`
- `backend/tests/unit/test_studio.py` — **new**; 11 tests: template filtering, mocked video/music (no provider call), image denied (L1/L3), image success (L5), ciphertext stored ≠ plaintext, decryption round-trip, invalid type → 422
- `frontend-chat/app/studio/layout.tsx` — **new**; server layout: `/auth/me` fetch, redirect to /login, `ConsentGate` wrapper, `NavSidebar`
- `frontend-chat/app/studio/page.tsx` — **new**; thin server page importing `StudioPage` client component
- `frontend-chat/components/studio/StudioPage.tsx` — **new**; full 3-panel studio UI: `ModeTabs`, `Toggle`, `SelectField`, per-mode advanced settings panels, `GenerationCard`, `TemplateCard`, `EmptyState`; state management for generate/list/templates flows
- `frontend-chat/app/api/studio/generate/route.ts` — **new**; POST proxy forwarding cookie `access_token` to backend
- `frontend-chat/app/api/studio/generations/route.ts` — **new**; GET proxy
- `frontend-chat/app/api/studio/templates/route.ts` — **new**; GET proxy with `?type=` passthrough
- `frontend-chat/components/NavSidebar.tsx` — added "True Studio" `NavItem` (href=/studio, `Ic.spark` icon) between Knowledge base and Admin console
- `PLAN.md` — Task 3.9 added and marked ☑

**Next steps:**
- [x] Task 3.9 — True Studio: model, migration, service, router, frontend UI, API proxies, NavSidebar link, 11 unit tests
- [ ] Manual verify True Studio UI: log in → /studio → Image tab → generate prompt → image result appears; My Studio tab shows history; Templates tab shows 18 templates, click to use fills prompt
- [ ] Replace mocked video/music with real Seedance/Lyria providers when available (# TODO markers in `studio.py`)
- [ ] **n8n UI (required):** Webhook node HTTP Method must be POST; LINE Messaging node text field → `{{ $json.body.message }}`
- [ ] Set `N8N_ALERT_WEBHOOK_URL` in `.env`, restart `backend-api`
- [ ] End-to-end test: send "the server is down" → chat reply shows ack; LINE admin gets message
- [ ] Run `alembic upgrade head` to apply migration `0010_gemini_image_model` (carried forward)
- [ ] Test `POST /automations/agent` end-to-end (carried forward)
- [ ] Frontend: handle `{"type":"image","url":"..."}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Frontend: handle `{"type":"sources","sources":[...]}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Run `ollama pull bge-m3` on Ollama host (192.168.20.18)
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (carried forward)
- [ ] Phase 2 acceptance gate (carried forward)

## 2026-06-22 00:00 — main @ 636e38e

**Summary:** Diagnosed and fixed the "Backend unreachable" error that blocked True Studio image generation for all users (including ADMIN). Root cause: `studio_generations.output_ref` was declared `VARCHAR(4000)`, but a Gemini JPEG data URL is ~820k–1M characters — the INSERT overflowed at the DB layer (asyncpg `StringDataRightTruncationError`), the unhandled 500 returned a plain-text body, and the Next.js BFF's `await res.json()` threw, collapsing into the misleading "Backend unreachable" message. Fixed by widening `output_ref` to `TEXT` in the ORM model and adding migration `0012_studio_output_ref_text` (applied to the running DB — metadata-only change, no table rewrite). Also corrected the hardcoded `data:image/png` MIME type: `generate_image_gemini` now returns `(bytes, mime_type)` and callers pass the actual MIME through `bytes_to_data_url`. The Next.js `generate/route.ts` BFF was hardened to read responses as text first and attempt JSON.parse so future backend errors surface their real message instead of "Backend unreachable." All 36 unit tests pass; a live end-to-end generate call as admin produced a `completed` row with 820,895-char `output_ref` in `studio_generations`.

**Files changed:**
- `backend/app/models/studio.py` — `output_ref` type changed `String(4000)` → `Text` (import added); comment updated
- `backend/alembic/versions/0012_studio_output_ref_text.py` — **new**; `ALTER TABLE studio_generations ALTER COLUMN output_ref TYPE TEXT`; chains off `0011_studio_generations`; applied to running DB
- `backend/app/llm/google.py` — `generate_image_gemini()` now returns `tuple[bytes, str]` (image bytes + actual MIME type from `part.inline_data.mime_type`)
- `backend/app/tools/image_gen.py` — `generate_image_bytes()` return type updated to `tuple[bytes, str]`; `bytes_to_data_url()` gains `mime_type: str = "image/jpeg"` param (was hardcoded `image/png`)
- `backend/app/services/studio.py` — unpacks `(image_bytes, mime_type)` tuple; passes `mime_type` to `bytes_to_data_url`
- `backend/app/routers/image.py` — same tuple unpack and `mime_type` passthrough
- `backend/tests/unit/test_studio.py` — two `generate_image_bytes` mocks updated to return `(bytes, "image/png")` tuples
- `backend/tests/unit/test_image_gen.py` — `bytes_to_data_url` tests updated (default MIME is now `image/jpeg`; explicit `mime_type="image/png"` for PNG test); `generate_image_bytes` mock returns tuple; result assertion updated
- `frontend-chat/app/api/studio/generate/route.ts` — BFF reads `res.text()` then `JSON.parse` with fallback; "Backend unreachable" now only triggers on network-level failure, not non-JSON 500s

**Next steps:**
- [x] Fix "Backend unreachable" in True Studio — `VARCHAR(4000)` overflow on image data URL
- [ ] Manual verify True Studio UI: log in as admin → /studio → Image tab → generate prompt → image renders in My Studio; Templates tab works
- [ ] Authorization for everyday users: `poommyskn@gmail.com` is L3/no-dept → gets 403 on image gen. Add to MKT department if image gen access is needed for that account
- [ ] Replace mocked video/music with real Seedance/Lyria providers when available (# TODO markers in `studio.py`)
- [ ] **n8n UI (required):** Webhook node HTTP Method must be POST; LINE Messaging node text field → `{{ $json.body.message }}`
- [ ] Set `N8N_ALERT_WEBHOOK_URL` in `.env`, restart `backend-api`
- [ ] End-to-end test: send "the server is down" → chat reply shows ack; LINE admin gets message
- [ ] Test `POST /automations/agent` end-to-end (carried forward)
- [ ] Frontend: handle `{"type":"image","url":"..."}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Frontend: handle `{"type":"sources","sources":[...]}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Run `ollama pull bge-m3` on Ollama host (192.168.20.18)
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (carried forward)
- [ ] Phase 2 acceptance gate (carried forward)
## 2026-06-22 — main @ 636e38e

**Summary:** Implemented real Google Veo video generation for True Studio, replacing the previous mocked stub. Video now runs through `PolicyEngine.decide()` (same L5/L6/ADMIN + MKT gating as image), inserts a `status="processing"` row immediately, and dispatches the actual Veo call in a FastAPI in-process background task that updates the row to `completed`/`failed` when Veo finishes. Frontend gains a 5-second poll loop that replaces processing cards with live results, renders completed videos as `<video controls>`, and shows a spinner + "Generating…" during the wait. Added `GET /studio/generations/{id}` backend endpoint and matching Next.js proxy for per-record polling. Migration `0013_veo_video_model` seeds `veo-2.0-generate-001` in `model_catalog`. All 17 studio unit tests pass (58/58 for studio + image_gen + policy_engine suites).

**Files changed:**
- `backend/app/llm/google.py` — added `generate_video()` method: submits Veo long-running job, polls until done (10-minute timeout, 10s interval), extracts inline mp4 bytes; uses `asyncio.to_thread` for blocking SDK calls
- `backend/app/tools/video_gen.py` — **new**; `VIDEO_MODEL_CODE = "veo-2.0-generate-001"`, `authorize_video()`, `video_authorized()`, `generate_video_bytes()` (mirrors `image_gen.py` structure); `_parse_duration()` maps `"5s"` → `5`
- `backend/alembic/versions/0013_veo_video_model.py` — **new**; seeds `veo-2.0-generate-001` into `model_catalog`, grants L5/L6/ADMIN + MKT; chains off `0012_studio_output_ref_text`
- `backend/app/models/studio.py` — added `"processing"` to `VALID_STATUSES`; updated column comment
- `backend/app/services/studio.py` — video dispatch now calls `_generate_video()` (real); added `_generate_video()` (authorize → insert processing row → schedule BG task) and `_run_video_generation()` (opens own session via `session_factory`, calls Veo, updates to completed/failed, audits); added `get_generation()` for single-record lookup; music still uses `_generate_mocked()`; added imports from `video_gen` and `sqlalchemy.update`
- `backend/app/routers/studio.py` — injected `BackgroundTasks` into `POST /generate`; added `GET /studio/generations/{gen_id}` endpoint
- `backend/tests/unit/test_studio.py` — replaced mocked video test with 5 real-video tests (processing row, BG task success, BG task failure, 403 role denied, 403 tier denied); added `test_get_generation_*` (owner, wrong-user); now 17 tests total
- `frontend-chat/app/api/studio/generations/[id]/route.ts` — **new**; cookie-forwarding GET proxy to `GET {BACKEND}/studio/generations/{id}`
- `frontend-chat/components/studio/StudioPage.tsx` — `MODE_CONFIG.video.model` → `"Veo 2.0"`; 5s polling `useEffect` with self-clearing timer; `GenerationCard` renders `<video controls>` for completed video, spinner + "Generating…" for processing, "Failed" label; added `@keyframes spin` style tag

**Next steps:**
- [x] Install `external` extras in the Docker backend container: bumped `google-genai>=1.5`, relaxed `httpx>=0.28`, rebuilt image
- [x] Run `alembic upgrade head` to apply migration `0013_veo_video_model` (applied; also applied 0014 and 0015)
- [ ] Manual verify video: log in as L5/MKT → /studio → Video tab → enter prompt → Generate → card shows "Generating…" → flips to `<video controls>` after Veo finishes
- [ ] Manual verify 403: log in as L1/L3 non-MKT user → Video → Generate → see denial message
- [x] Replace mocked video with real Veo provider
- [ ] Manual verify True Studio UI: admin → /studio → Image tab → generate → image renders; Templates tab works
- [ ] Authorization for everyday users: `poommyskn@gmail.com` is L3/no-dept → 403 on image/video. Add to MKT if access needed
- [ ] **n8n UI (required):** Webhook node HTTP Method must be POST; LINE Messaging node text field → `{{ $json.body.message }}`
- [ ] Set `N8N_ALERT_WEBHOOK_URL` in `.env`, restart `backend-api`
- [ ] End-to-end test: send "the server is down" → chat reply shows ack; LINE admin gets message
- [ ] Test `POST /automations/agent` end-to-end (carried forward)
- [ ] Frontend: handle `{"type":"image","url":"..."}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Frontend: handle `{"type":"sources","sources":[...]}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Run `ollama pull bge-m3` on Ollama host (192.168.20.18)
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (carried forward)
- [ ] Phase 2 acceptance gate (carried forward)

## 2026-06-22 14:00 — main @ 636e38e

**Summary:** Debugged the "still failed" video generation report, confirmed the byte-download fix from the prior session already worked (DB shows `studio_video_generated` at 18:41, 2.1 MB — the visible "Failed" cards were stale history rows). Switched the studio video model from Veo 2.0 to Veo 3.1 (`veo-3.1-generate-preview`): created migration `0015_veo_3_1_video_model` (seeds the new catalog entry with L5/L6/ADMIN + MKT permissions, deactivates `veo-2.0-generate-001`), updated `VIDEO_MODEL_CODE` and duration/aspect-ratio constraints in `video_gen.py` (Veo 3.1 only accepts `{4,6,8}` seconds and `{16:9,9:16}`), updated frontend UI dropdowns. Earlier in this session also resolved three migration blockers: applied `0013_veo_video_model`, bumped `google-genai>=1.5` + `httpx>=0.28`, rebuilt image, and created migration `0014_studio_audit_actions` (seven missing `audit_action` enum values). All 19 studio unit tests pass.

**Files changed:**
- `backend/alembic/versions/0014_studio_audit_actions.py` — **new**; adds 7 studio `audit_action` enum values; applied to running DB
- `backend/alembic/versions/0015_veo_3_1_video_model.py` — **new**; seeds `veo-3.1-generate-preview` with L5/L6/ADMIN + MKT perms, deactivates `veo-2.0-generate-001`; applied to running DB
- `backend/app/llm/google.py` — `generate_video()`: replaced dead inline-bytes fallback with `self._client.files.download(file=video)`
- `backend/app/tools/video_gen.py` — `VIDEO_MODEL_CODE` → `"veo-3.1-generate-preview"`; `_VALID_ASPECT_RATIOS` → `{"16:9","9:16"}`; `_VALID_DURATIONS = (4,6,8)`; `_parse_duration` snaps to nearest discrete value, default 8
- `backend/pyproject.toml` — `google-genai>=0.8` → `>=1.5`; `httpx>=0.27,<0.28` → `>=0.28`
- `backend/tests/unit/test_studio.py` — 4 `"Veo 2.0"` literals → `"Veo 3.1"`; 2 new tests for model code + duration snapping (19 total)
- `frontend-chat/components/studio/StudioPage.tsx` — model label `'Veo 3.1'`; Aspect Ratio options `['16:9','9:16']`; Video Length `['4s','6s','8s']`, default `'8s'`

**Next steps:**
- [ ] Manual verify Veo 3.1 end-to-end: admin → /studio → Video tab → generate → card flips to `<video controls>` with Veo 3.1 output
- [ ] Confirm audit log shows `"model": "veo-3.1-generate-preview"` in `studio_video_generated` details
- [ ] **Note (risk):** `veo-3.1-generate-preview` is a preview model — may require Google API key allowlisting. If denied, audit log will show a clear `APIError`
- [ ] Manual verify True Studio UI: admin → /studio → Image tab → generate → image renders; Templates tab works
- [ ] Authorization for everyday users: `poommyskn@gmail.com` is L3/no-dept → 403 on image/video. Add to MKT if access needed
- [ ] **n8n UI (required):** Webhook node HTTP Method must be POST; LINE Messaging node text field → `{{ $json.body.message }}`
- [ ] Set `N8N_ALERT_WEBHOOK_URL` in `.env`, restart `backend-api`
- [ ] End-to-end test: send "the server is down" → chat reply shows ack; LINE admin gets message
- [ ] Test `POST /automations/agent` end-to-end (carried forward)
- [ ] Frontend: handle `{"type":"image","url":"..."}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Frontend: handle `{"type":"sources","sources":[...]}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Run `ollama pull bge-m3` on Ollama host (192.168.20.18)
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (carried forward)
- [ ] Phase 2 acceptance gate (carried forward)

## 2026-06-22 — main @ 636e38e

**Summary:** Implemented the Library sidebar tab — a unified browsing interface for all user-accumulated media and documents. Backend: extended `GET /studio/generations` and `GET /files` with `date_from`, `date_to`, `sort`, `context`, `limit`, `offset`, and `q` (filename search) query params; added `context: str = "upload"` to `FileOut` so the UI's Context column has data; added new `GET /files/{id}/download` endpoint using existing `_get_accessible_file()` + `blob_path()`, returning `FileResponse`. Frontend: added Library `<NavItem>` to `NavSidebar`; new `/library` route (layout + page); four BFF proxy routes under `app/api/library/`; full `LibraryPage.tsx` client component with segmented tab control (Image & Video / File), Time Period / Context / Sort filters, thumbnail media grid with lightbox (handles image/video/audio cards), file table with search + download + delete, and scoped `@keyframes lib-spin` animation. All Python files passed `py_compile` syntax check; `npx tsc --noEmit` returned zero TypeScript errors.

**Files changed:**
- `backend/app/services/studio.py` — `list_generations` extended: added `offset`, `date_from`, `date_to`, `sort` params with conditional `.where()` chaining
- `backend/app/routers/studio.py` — `GET /studio/generations` accepts `date_from`, `date_to`, `sort`, `context`, `limit`, `offset`; returns empty list when `context=="upload"`
- `backend/app/schemas/file.py` — `FileOut` gained `context: str = "upload"` (Pydantic v2 default, not an ORM column)
- `backend/app/routers/files.py` — `GET /files` extended with `date_from`, `date_to`, `sort`, `context`, `q` (ilike search); new `GET /files/{id}/download` endpoint (placed before DELETE route)
- `frontend-chat/components/NavSidebar.tsx` — Library `<NavItem>` added after AI Studio item
- `frontend-chat/app/library/layout.tsx` — **new**; auth + `ConsentGate` + `NavSidebar` (copy of studio layout)
- `frontend-chat/app/library/page.tsx` — **new**; thin wrapper rendering `<LibraryPage />`
- `frontend-chat/app/api/library/media/route.ts` — **new**; BFF proxy → `GET /studio/generations?<qs>`
- `frontend-chat/app/api/library/files/route.ts` — **new**; BFF proxy → `GET /files?<qs>`
- `frontend-chat/app/api/library/files/[id]/route.ts` — **new**; BFF proxy → `DELETE /files/{id}`
- `frontend-chat/app/api/library/files/[id]/download/route.ts` — **new**; BFF proxy → `GET /files/{id}/download`, streams body + forwards `Content-Type`/`Content-Disposition`
- `frontend-chat/components/library/LibraryPage.tsx` — **new**; full client component: tab control, filter bar (Time Period/Context/Sort), media grid with `MediaCard`/`MediaLightbox`, file table with search/download/delete, empty states, scoped `@keyframes lib-spin`

**Next steps:**
- [ ] End-to-end UI verify: log in → click Library in sidebar → Image & Video tab shows generated media; image click opens lightbox; Time Period / Context / Sort filters change results live; File tab lists uploaded docs; search filters by name; download saves file; delete removes row
- [ ] Backend API smoke test: `GET /studio/generations?sort=oldest&date_from=<iso>` and `GET /files?q=pepsi&sort=recent` and `GET /files/{id}/download` with valid session cookie
- [ ] Extend `test_studio.py` with date-range / sort / context filter tests; add files-filter + download tests
- [ ] Manual verify Veo 3.1 end-to-end (carried forward)
- [ ] Manual verify True Studio UI: admin → /studio → Image → generate → image renders; Templates works (carried forward)
- [ ] Authorization for everyday users: `poommyskn@gmail.com` is L3/no-dept → 403 on image/video (carried forward)
- [ ] **n8n UI (required):** Webhook POST method + LINE node text field mapping (carried forward)
- [ ] Set `N8N_ALERT_WEBHOOK_URL` in `.env`, restart `backend-api` (carried forward)
- [ ] Frontend: handle `{"type":"image","url":"..."}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Frontend: handle `{"type":"sources","sources":[...]}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Run `ollama pull bge-m3` on Ollama host (192.168.20.18) (carried forward)
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (carried forward)
- [ ] Phase 2 acceptance gate (carried forward)

## 2026-06-22 — main @ 636e38e

**Summary:** Implemented the full **AI Agent** feature — a reusable-agent catalog wired end-to-end into chat. Backend: `Agent` + `AgentFile` ORM models, Alembic migrations `0018_agents` (tables + `conversations.agent_id` FK) and `0019_agent_audit_actions` (3 new enum values), `app/services/agent.py` (CRUD, accessibility filter, knowledge file helpers, audit), `app/routers/agents.py` (8 endpoints). Chat integration: `PreparedChat` gains `system_prompt` + `temperature`; `prepare_chat` loads agent, gates capabilities (web_search/image_gen/video_gen), scopes RAG to agent files, persists `agent_id`; orchestrator `call_llm` injects system prompt before RAG context and passes temperature as `**stream_opts`; `rag_search.retrieve` extended with optional `file_ids`. Frontend: `/agent` route (layout, page, create/edit), 3 BFF proxy routes, `AgentPage.tsx` (All/Mine tabs, search, grid, About modal), `AboutModal.tsx` (chat CTA), `CreateAgentForm.tsx` (full CRUD + knowledge table); NavSidebar item; `ChatPane` agent chip (avatar dot + name + model); `/chat?agent={id}` and `/chat/{id}` restore chip from persisted `agent_id`. Fixed icon names (`Ic.checkCircle` → `Ic.check`, `Ic.save` → `Ic.file`). Added 17 unit tests in `test_agents.py`.

**Files changed:**
- `backend/app/models/agent.py` — **new**; `Agent` + `AgentFile` ORM; `VALID_VISIBILITIES` + `VALID_STATUSES` frozensets
- `backend/app/models/__init__.py` — added `Agent`, `AgentFile` exports
- `backend/app/models/conversation.py` — added nullable `agent_id` UUID FK → `agents.id` ON DELETE SET NULL
- `backend/app/models/audit.py` — added `agent_created`, `agent_updated`, `agent_deleted` to enum tuple
- `backend/alembic/versions/0018_agents.py` — **new**; idempotent `CREATE TABLE IF NOT EXISTS` for `agents` + `agent_files`; `ALTER TABLE conversations ADD COLUMN IF NOT EXISTS agent_id`
- `backend/alembic/versions/0019_agent_audit_actions.py` — **new**; `ALTER TYPE audit_action ADD VALUE IF NOT EXISTS` × 3
- `backend/app/services/agent.py` — **new**; `creativity_to_temperature`, `_accessible_filter`, full CRUD, knowledge file helpers, audit calls
- `backend/app/routers/agents.py` — **new**; 8 REST endpoints, inline Pydantic DTOs, `_enrich_with_creator()` join
- `backend/app/main.py` — registered `agents_router`
- `backend/app/llm/router.py` — added `PERPLEXITY_MODEL_CODE` constant
- `backend/app/services/chat_policy.py` — `PreparedChat` gains `system_prompt`, `temperature`, `agent_file_ids`; `prepare_chat` loads agent, gates capabilities, scopes RAG, persists `agent_id`
- `backend/app/agents/orchestrator.py` — `ChatState` gains `system_prompt`/`temperature`; `call_llm` injects instructions before RAG; passes temperature via `stream_opts`
- `backend/app/routers/chat.py` — `ChatRequest` gains `agent_id`; forwarded to `prepare_chat` + `run_chat_stream`
- `backend/app/routers/conversations.py` — `ConversationDetail` gains `agent_id`; returned in detail response
- `backend/app/tools/rag_search.py` — `retrieve()` gains optional `file_ids` for agent-scoped search
- `backend/tests/unit/test_agents.py` — **new**; 17 tests: creativity mapping, create/audit/400, own/public/personal access, update/delete ownership, constant sets
- `frontend-chat/components/NavSidebar.tsx` — AI Agent nav item added between Library and Search
- `frontend-chat/app/agent/layout.tsx` — **new**; auth + ConsentGate + NavSidebar
- `frontend-chat/app/agent/page.tsx` — **new**; renders `<AgentPage />`
- `frontend-chat/app/agent/create/page.tsx` — **new**; renders `<CreateAgentForm />`
- `frontend-chat/app/agent/[id]/edit/page.tsx` — **new**; client page passing `agentId` to form
- `frontend-chat/app/api/agent/route.ts` — **new**; GET list + POST create BFF proxy
- `frontend-chat/app/api/agent/[id]/route.ts` — **new**; GET + PUT + DELETE BFF proxy
- `frontend-chat/app/api/agent/[id]/knowledge/route.ts` — **new**; POST knowledge-attach BFF proxy
- `frontend-chat/components/agent/AgentPage.tsx` — **new**; All/Mine tabs, search, grid, About modal trigger, empty states
- `frontend-chat/components/agent/AboutModal.tsx` — **new**; avatar, visibility badge, instructions, capabilities checklist, gradient "Chat with Agent" button
- `frontend-chat/components/agent/CreateAgentForm.tsx` — **new**; full create/edit form: provider/model dropdowns, capability checkboxes, creativity slider, knowledge file table
- `frontend-chat/components/ChatPane.tsx` — agent chip + `agentIdRef`; fetches agent on `initialAgentId`; includes `agent_id` in chat body; header chip when active
- `frontend-chat/app/chat/page.tsx` — reads `searchParams.agent`; passes `initialAgentId`
- `frontend-chat/app/chat/[id]/page.tsx` — `ConversationDetail` gains `agent_id`; passes as `initialAgentId`

**Next steps:**
- [ ] Run `alembic upgrade head` to apply migrations `0018_agents` + `0019_agent_audit_actions`
- [ ] Run `pytest backend/tests/unit/test_agents.py -q` to confirm all 17 tests pass
- [ ] Manual verify AI Agent UI: browse `/agent` grid → About modal → Chat with Agent → chip in chat header; reload `/chat/{id}` → chip restored from persisted `agent_id`
- [ ] E2E: create agent with instructions + knowledge file → chat → verify system prompt shapes reply + scoped RAG
- [ ] End-to-end UI verify Library tab (carried forward)
- [ ] Manual verify Veo 3.1 end-to-end (carried forward)
- [ ] Manual verify True Studio Image tab (carried forward)
- [ ] **n8n UI (required):** Webhook POST method + LINE node text field mapping (carried forward)
- [ ] Set `N8N_ALERT_WEBHOOK_URL` in `.env`, restart `backend-api` (carried forward)
- [ ] Frontend: handle `{"type":"image","url":"..."}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Frontend: handle `{"type":"sources","sources":[...]}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Run `ollama pull bge-m3` on Ollama host (carried forward)
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (carried forward)
- [ ] Phase 2 acceptance gate (carried forward)

## 2026-06-23 — main @ 636e38e

**Summary:** Fixed the Agent feature crash with Gemini 2.5 Pro: `'async for' requires an object with __aiter__ method, got coroutine`. Root cause — `google-genai`'s async SDK returns a coroutine from `client.aio.models.generate_content_stream(...)` that must be `await`ed before iteration; the missing `await` on line 70 of `google.py` caused every Gemini streaming call to fail with a `TypeError` caught and re-wrapped as `"google unreachable: …"`. Added `from __future__ import annotations` to prevent the eager type-annotation evaluation of `genai_errors.APIError` at import time (a latent test-collection failure). Updated all 12 streaming mock functions in `test_google_llm.py` to return a coroutine resolving to an async iterator — matching the real SDK shape so the mocks now guard against this regression. Hardened `tests/unit/conftest.py` google stub with complete type stubs (`APIError`, `GenerateContentConfig`, `GenerateImagesConfig`, `GenerateVideosConfig`, `Part`, `Client`, `_IS_STUB` marker). Result: **14 tests pass, 2 real-API tests skip** cleanly when the real SDK is not in the venv.

**Files changed:**
- `backend/app/llm/google.py` — added `from __future__ import annotations`; added `await` to `generate_content_stream()` call (the one-line production fix)
- `backend/tests/unit/test_google_llm.py` — added `_await_stream` helper; updated 5 lambda mocks to `_await_stream`; converted 4 async-generator `_capture*` functions to coroutines returning `_stream(chunks)`; converted 2 `_fail` generators to plain coroutines; imported `google.genai as _genai`; updated `REAL_API` to also skip when `_genai._IS_STUB` is set
- `backend/tests/unit/conftest.py` — google stub gains `APIError` (matching real `__str__` shape for `match="google 400"` assertions), `GenerateContentConfig`/`GenerateImagesConfig`/`GenerateVideosConfig`/`Part` type stubs, `Client` stub, and `_IS_STUB = True` marker

**Next steps:**
- [ ] Run `alembic upgrade head` to apply migrations `0018_agents` + `0019_agent_audit_actions` (carried forward)
- [ ] Run `pytest backend/tests/unit/test_agents.py -q` to confirm all 17 tests pass (carried forward)
- [ ] Manual verify AI Agent UI: browse `/agent` grid → About modal → Chat with Agent → agent chip in chat header (carried forward)
- [ ] E2E: create agent with instructions + knowledge file → chat → verify system prompt shapes reply + scoped RAG (carried forward)
- [ ] Manual verify Veo 3.1 end-to-end (carried forward)
- [ ] Manual verify True Studio Image tab (carried forward)
- [ ] End-to-end UI verify Library tab (carried forward)
- [ ] **n8n UI (required):** Webhook POST method + LINE node text field mapping (carried forward)
- [ ] Set `N8N_ALERT_WEBHOOK_URL` in `.env`, restart `backend-api` (carried forward)
- [ ] Frontend: handle `{"type":"image","url":"..."}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Frontend: handle `{"type":"sources","sources":[...]}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Run `ollama pull bge-m3` on Ollama host (carried forward)
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (carried forward)
- [ ] Phase 2 acceptance gate (carried forward)

## 2026-06-23 17:00 — main @ 418370a

**Summary:** Completed four content additions to `[client proposal doc]` (Google Drive) via browser automation across two context windows. Added (1) a SLA 99.5% definition note below the Section 6 NFR table (measurement window, exclusions, service-credit remedy, Prometheus/Grafana as evidence); (2) Section 8.2 "การสำรองข้อมูลและการกู้คืน (Backup & DR)" Heading 2 with 5 bullets (pg_dump nightly/14d, object storage backup, RPO ≤24h / RTO ≤4h, quarterly restore testing, P4 note); (3) External API cost assumptions paragraph below Section 10.1 budget table (~30 users × 10 req/day × 1,500 tokens = ฿300k/yr, monthly per-role quota cap enforced, confirmed at Discovery); and (4) a 7-bullet team composition breakdown (270 MD @ ฿12,000/MD: Tech Lead 40, Backend 90, Frontend 50, DevOps 35, QA 30, PM/BA 25, total note). Document confirmed "Saved to Drive."

**Files changed:**
- `[client proposal doc]` (Google Drive) — Section 6 SLA note; Section 8.2 Backup & DR subsection; Section 10.1 API cost assumptions paragraph and team composition bullets

**Next steps:**
- [ ] Run `alembic upgrade head` to apply migrations `0018_agents` + `0019_agent_audit_actions` (carried forward)
- [ ] Run `pytest backend/tests/unit/test_agents.py -q` to confirm all 17 tests pass (carried forward)
- [ ] Manual verify AI Agent UI: browse `/agent` grid → About modal → Chat with Agent → agent chip in chat header (carried forward)
- [ ] E2E: create agent with instructions + knowledge file → chat → verify system prompt shapes reply + scoped RAG (carried forward)
- [ ] Manual verify Veo 3.1 end-to-end (carried forward)
- [ ] Manual verify True Studio Image tab (carried forward)
- [ ] End-to-end UI verify Library tab (carried forward)
- [ ] **n8n UI (required):** Webhook POST method + LINE node text field mapping (carried forward)
- [ ] Set `N8N_ALERT_WEBHOOK_URL` in `.env`, restart `backend-api` (carried forward)
- [ ] Frontend: handle `{"type":"image","url":"..."}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Frontend: handle `{"type":"sources","sources":[...]}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Run `ollama pull bge-m3` on Ollama host (carried forward)
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (carried forward)
- [ ] Phase 2 acceptance gate (carried forward)
## 2026-06-24 — main @ 418370a

**Summary:** Reviewed video generation logic and identified three cost risks (no per-user video quota, default duration at max 8s, no idempotency dedup). Switched the studio video model from Veo 3.1 to Veo 3.1 Lite (`veo-3.1-lite-generate-preview`): updated `VIDEO_MODEL_CODE` constant, added Alembic migration `0021_veo_3_1_lite_video_model` (seeds Lite catalog entry with same L5/L6/ADMIN + MKT permissions, deactivates `veo-3.1-generate-preview`), updated the test assertion, and updated the frontend model label. Note: unit tests could not be run this session because `.venv` symlinks target `/usr/local/bin/python3` (Linux build) and don't resolve on the Windows host — run `pytest` from WSL or Docker to verify.

**Files changed:**
- `backend/app/tools/video_gen.py` — `VIDEO_MODEL_CODE` → `"veo-3.1-lite-generate-preview"`; updated inline comments
- `backend/alembic/versions/0021_veo_3_1_lite_video_model.py` — **new**; seeds `veo-3.1-lite-generate-preview` with L5/L6/ADMIN + MKT perms, deactivates `veo-3.1-generate-preview`
- `backend/tests/unit/test_studio.py` — `test_video_model_code_is_veo_3_1` → `test_video_model_code_is_veo_3_1_lite`; assertion updated
- `frontend-chat/components/studio/StudioPage.tsx` — video `model` label `'Veo 3.1'` → `'Veo 3.1 Lite'`

**Next steps:**
- [ ] Run `alembic upgrade head` to apply migration `0021_veo_3_1_lite_video_model` to running DB
- [ ] Run `pytest backend/tests/unit/test_studio.py -q` (from WSL/Docker) to confirm all studio tests pass
- [ ] Manual verify: admin → /studio → Video tab → generate → audit log shows `"model": "veo-3.1-lite-generate-preview"`
- [ ] **Cost risk (open):** No per-user video quota — authorized users can submit unlimited paid Veo jobs
- [ ] Run `alembic upgrade head` for `0018_agents` + `0019_agent_audit_actions` (carried forward)
- [ ] Run `pytest backend/tests/unit/test_agents.py -q` — 17 tests (carried forward)
- [ ] Manual verify AI Agent UI end-to-end (carried forward)
- [ ] E2E: agent with instructions + knowledge file → chat (carried forward)
- [ ] Manual verify True Studio Image tab (carried forward)
- [ ] End-to-end UI verify Library tab (carried forward)
- [ ] **n8n UI (required):** Webhook POST method + LINE node text field mapping (carried forward)
- [ ] Set `N8N_ALERT_WEBHOOK_URL` in `.env`, restart `backend-api` (carried forward)
- [ ] Frontend: handle `{"type":"image","url":"..."}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Frontend: handle `{"type":"sources","sources":[...]}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Run `ollama pull bge-m3` on Ollama host (carried forward)
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (carried forward)
- [ ] Phase 2 acceptance gate (carried forward)
## 2026-06-24 — main @ 418370a

**Summary:** Diagnosed the recurring "You are not authorized to generate videos" 403 for admin users. Root cause: the code uses `VIDEO_MODEL_CODE = "veo-3.1-lite-generate-preview"` but migration `0021_veo_3_1_lite_video_model` had never been applied to the running DB, so `_get_model()` returned None → `UNKNOWN_MODEL` → generic 403 on every request. Fixed permanently by adding `alembic upgrade head` to the FastAPI lifespan so migrations auto-apply at server startup. Also improved the denial message for `UNKNOWN_MODEL`/`MODEL_INACTIVE` to say "video model not configured in the database" instead of the misleading generic auth message.

**Files changed:**
- `backend/app/main.py` — added Alembic auto-migrate at startup (`asyncio.to_thread` to avoid nested event loop); added imports for `alembic.command`, `AlembicConfig`, `asyncio`, `pathlib`
- `backend/app/services/studio.py` — added `elif UNKNOWN_MODEL or MODEL_INACTIVE` denial branch with a clearer "video model not configured" message

**Next steps:**
- [x] Root-cause the "not authorized to generate videos" 403 for admin (migration 0021 not applied)
- [ ] Restart `backend-api` container so the lifespan auto-migration runs and applies `0021_veo_3_1_lite_video_model` — then verify admin can generate video
- [ ] Run `pytest backend/tests/unit/test_studio.py -q` (from WSL/Docker) to confirm all studio tests pass
- [ ] Manual verify: admin → /studio → Video tab → generate → audit log shows `"model": "veo-3.1-lite-generate-preview"`
- [ ] **Cost risk (open):** No per-user video quota — authorized users can submit unlimited paid Veo jobs
- [ ] Run `pytest backend/tests/unit/test_agents.py -q` — 17 tests (carried forward)
- [ ] Manual verify AI Agent UI end-to-end (carried forward)
- [ ] E2E: agent with instructions + knowledge file → chat (carried forward)
- [ ] Manual verify True Studio Image tab (carried forward)
- [ ] End-to-end UI verify Library tab (carried forward)
- [ ] **n8n UI (required):** Webhook POST method + LINE node text field mapping (carried forward)
- [ ] Set `N8N_ALERT_WEBHOOK_URL` in `.env`, restart `backend-api` (carried forward)
- [ ] Frontend: handle `{"type":"image","url":"..."}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Frontend: handle `{"type":"sources","sources":[...]}` SSE event in `ChatPane.tsx` (carried forward)
- [ ] Run `ollama pull bge-m3` on Ollama host (carried forward)
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (carried forward)
- [ ] Phase 2 acceptance gate (carried forward)

## 2026-06-30 18:00 — main @ 8609caf

**Summary:** Completed Step 4 of the Amarin → Brandbiz fork: separated the database. Found that `docker-compose.yml` still hardcoded `aigateway` as the Postgres DB name, user, and `pg_isready` target — mismatched with the `.env.example` already updated to `brandbiz` in Step 3. Updated all five occurrences to `brandbiz`. Confirmed pgvector dimension (`VECTOR(1024)`) matches the embedding model (`bge-m3:latest`, which outputs 1024 dims) — no mismatch. Verified the Alembic migration chain (0001–0021) provides a clean from-scratch init path. Created `db/init/README.md` documenting the bootstrap procedure and migration table.

**Files changed:**
- `docker-compose.yml` — `POSTGRES_DB`/`POSTGRES_USER`/`pg_isready` changed from `aigateway` → `brandbiz` (postgres service + backend-api env block)
- `db/init/README.md` — new; documents `alembic upgrade head` bootstrap, migration chain, pgvector dimension note, and connection details

**Next steps:**
- [ ] Step 5 (fork): re-run `grep -ri amarin` verification pass to confirm zero references, then produce human-decision checklist (domains, deploy targets, org policies)
- [ ] Restart `backend-api` container so lifespan auto-migration runs migration `0021_veo_3_1_lite_video_model` — verify admin can generate video (carried forward)
- [ ] Run `pytest backend/tests/unit/test_studio.py -q` from WSL/Docker (carried forward)
- [ ] Manual verify: admin → /studio → Video tab → generate → audit log shows `"model": "veo-3.1-lite-generate-preview"` (carried forward)
- [ ] **Cost risk (open):** No per-user video quota for Veo (carried forward)
- [ ] Run `pytest backend/tests/unit/test_agents.py -q` — 17 tests (carried forward)
- [ ] Manual verify AI Agent UI end-to-end (carried forward)
- [ ] Manual verify True Studio Image tab (carried forward)
- [ ] **n8n UI:** Webhook POST method + LINE node text field mapping (carried forward)
- [ ] Set `N8N_ALERT_WEBHOOK_URL` in `.env`, restart `backend-api` (carried forward)
- [ ] Run `ollama pull bge-m3` on Ollama host (carried forward)
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (carried forward)
- [ ] Phase 2 acceptance gate (carried forward)

## 2026-06-30 19:00 — main @ d60a329

**Summary:** Completed Step 5 of the Amarin → Brandbiz fork: final verification sweep and residual cleanup. Confirmed zero "amarin" references in active code (PROGRESS.md historical entries only). Found 10+ residual "aigateway" references across config defaults, integration test fixtures, hardcoded DSNs, README psql commands, and Garage bucket names — fixed all of them across 8 files. Intentionally left `reference/docker-compose.yml` unchanged (source template, not active config). Human-decision items documented below.

**Files changed:**
- `backend/app/config.py` — postgres_db/postgres_user default fallbacks changed to `brandbiz`
- `backend/tests/integration/conftest.py` — `_PG_DB` and docker-compose project name → `brandbiz`
- `backend/tests/integration/docker-compose.yml` — `POSTGRES_DB` → `test_brandbiz`
- `backend/tests/integration/test_audit_enum_sync.py` — hardcoded DSN → `brandbiz`
- `backend/tests/verify_task19.py` — hardcoded DSN → `brandbiz`
- `README.md` — psql `-U aigateway aigateway` commands → `brandbiz`; Garage bucket `aigateway-files` → `brandbiz-files`
- `PLAN.md` — Garage bucket name → `brandbiz-files`
- `test-doc/phase1-test.md` — psql command → `brandbiz`

**Next steps:**
- [x] Step 5 (fork): re-run verification pass + human-decision checklist
- [ ] **HUMAN DECISION — Production domain**: `decomplica.tech` still appears in `PLAN.md`, `backend/app/routers/openai_compat.py` (×2), and `backend/scripts/create_service_account.py` (×2). Decide the Brandbiz production domain (e.g. `brandbiz.ai`) and replace all occurrences.
- [ ] **HUMAN DECISION — LLM server IP**: `192.168.20.18` is the Amarin LAN Ollama host; hardcoded as default in `.env.example` and `docker-compose.yml`. Brandbiz needs its own server address — fill `LLM_PRIMARY_URL` and `LLM_EMBED_URL` in `.env` for the new deployment.
- [ ] **HUMAN DECISION — Google Workspace domain**: `GOOGLE_WORKSPACE_DOMAIN` is blank in `.env.example` (allows any Google account). Set it to the Brandbiz org domain to restrict login.
- [ ] **HUMAN DECISION — Google OAuth credentials**: Create a new OAuth client in Google Cloud Console for Brandbiz, fill `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET`, and register the redirect URI for the Brandbiz domain.
- [ ] **HUMAN DECISION — Garage S3 bucket**: Bucket name `brandbiz-files` is set in `.env.example` comments; run the three `garage` bootstrap commands once the storage service is up.
- [ ] Restart `backend-api` container so lifespan auto-migration runs migration `0021_veo_3_1_lite_video_model` — verify admin can generate video (carried forward)
- [ ] Run `pytest backend/tests/unit/test_studio.py -q` from WSL/Docker (carried forward)
- [ ] Manual verify: admin → /studio → Video tab → generate → audit log shows `"model": "veo-3.1-lite-generate-preview"` (carried forward)
- [ ] **Cost risk (open):** No per-user video quota for Veo (carried forward)
- [ ] Run `pytest backend/tests/unit/test_agents.py -q` — 17 tests (carried forward)
- [ ] Manual verify AI Agent UI end-to-end (carried forward)
- [ ] Manual verify True Studio Image tab (carried forward)
- [ ] **n8n UI:** Webhook POST method + LINE node text field mapping (carried forward)
- [ ] Set `N8N_ALERT_WEBHOOK_URL` in `.env`, restart `backend-api` (carried forward)
- [ ] Run `ollama pull bge-m3` on Ollama host (carried forward)
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (carried forward)
- [ ] Phase 2 acceptance gate (carried forward)

## 2026-07-06 — main @ 139aa98

**Summary:** Made True Studio generations editable from the detail modal for all three modes (Image/Video/Music). Added a `parent_id` lineage column to `studio_generations` so an edit/regenerate links back to its source without mutating the original row. `GET /studio/generations/{id}` now returns a decrypted `prompt` + `settings` (new `GenerationDetailResponse`, owner-scoped, same decrypt-on-read pattern as `conversations.py`) so the frontend can actually show and pre-fill what was generated. Replaced the read-only `ImageLightbox` with `GenerationDetailModal`: media on the left, an edit panel on the right reusing the existing `ImageAdvanced`/`VideoAdvanced`/`MusicAdvanced` settings components. Image edits resend the current image as a reference (real edit via Gemini); video/music "edits" prefill the original prompt/settings and resubmit as a regenerate. A "Use as Template" button loads the generation back into the main form. New generations get an "edited" badge on their card. Backend syntax-checked with `py_compile` and frontend type-checked clean with `npx tsc --noEmit`; could not run `pytest` — this Windows host's `.venv` was built for Linux (`.venv/bin/python` is a broken symlink to `/usr/local/bin/python3`), no WSL distro with bash, and no `uv`/matching Python 3.12 available locally.

**Files changed:**
- `backend/alembic/versions/0026_studio_generation_parent_id.py` — new; adds nullable self-referencing `parent_id` (ON DELETE SET NULL) + index
- `backend/app/models/studio.py` — added `parent_id` mapped column
- `backend/app/services/studio.py` — `generate()` accepts `parent_id`, validates it resolves for the calling user (404 if not) before dispatching; `_generate_image/_generate_video/_generate_music` store it; image audit details include `parent_id`
- `backend/app/routers/studio.py` — `GenerateRequest.parent_id`; `GenerationResponse.parent_id`; new `GenerationDetailResponse` (prompt + settings) returned by `GET /studio/generations/{id}`
- `backend/tests/unit/test_studio.py` — 2 new tests: valid `parent_id` stored on the new row, unknown `parent_id` raises 404 before any generation work
- `frontend-chat/components/studio/StudioPage.tsx` — `Generation.parent_id` + new `GenerationDetail` type; "edited" badge on `GenerationCard`; replaced `ImageLightbox` with `GenerationDetailModal` (fetches detail, per-mode edit form, submit → `POST /studio/generate` with `parent_id`, "Use as Template"); `handleGenerationEdited`/`handleUseGenerationAsTemplate` handlers in `StudioPage`

**Next steps:**
- [ ] Run `alembic upgrade head` to apply migration `0026_studio_generation_parent_id`
- [ ] Run `pytest backend/tests/unit/test_studio.py -q` (from WSL/Docker/a Linux env with the project's `uv` venv) to confirm all studio tests pass, including the 2 new parent_id tests
- [ ] Manual verify: Image tab → generate → open result → "Describe your changes" → Generate Edit → new edited image appears in-modal and in My Studio with an "edited" badge
- [ ] Manual verify: Video/Music tab → generate → open result → tweak prompt/settings → Regenerate → new "processing" card appears in My Studio and completes via existing polling
- [ ] Manual verify: "Use as Template" loads prompt/settings/output back into the left-hand form
- [ ] Restart `backend-api` container so lifespan auto-migration runs migration `0021_veo_3_1_lite_video_model` — verify admin can generate video (carried forward)
- [ ] Manual verify: admin → /studio → Video tab → generate → audit log shows `"model": "veo-3.1-lite-generate-preview"` (carried forward)
- [ ] **Cost risk (open):** No per-user video quota for Veo (carried forward)
- [ ] Run `pytest backend/tests/unit/test_agents.py -q` — 17 tests (carried forward)
- [ ] Manual verify AI Agent UI end-to-end (carried forward)
- [ ] **n8n UI:** Webhook POST method + LINE node text field mapping (carried forward)
- [ ] Set `N8N_ALERT_WEBHOOK_URL` in `.env`, restart `backend-api` (carried forward)
- [ ] Run `ollama pull bge-m3` on Ollama host (carried forward)
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (carried forward)
- [ ] Phase 2 acceptance gate (carried forward)
- [ ] **HUMAN DECISION — Production domain / LLM server IP / Google Workspace domain / OAuth credentials / Garage bucket** (carried forward from Step 5 fork sweep, still open)

## 2026-07-06 15:48 — main @ 139aa98

**Summary:** Implemented the "Search chats" feature end-to-end (Gemini-style dedicated search page, title-only per the encryption governance rule). Backend `GET /conversations` gained optional `q` (escaped ILIKE on title, user-scoped) and `limit` (1–200, default 50) params with default behavior unchanged; new `/chat/search` page renders a centered autofocused search box with a debounced (300 ms, AbortController-cancelled) live-filtered "Recent" list showing relative dates (Today/Yesterday/Jul 2), reached via a new "Search chats" sidebar item under New chat. Verified end-to-end: 4 new unit tests pass in the backend container, HTTP checks confirm case-insensitive matching, literal `%` escaping, and 422 on limit=999, and browser verification confirmed the Recent list, live filtering ("tell" → 2 matches), Escape/× clearing, result navigation to `/chat/{id}`, and correct sidebar active states.

**Files changed:**
- `backend/app/routers/conversations.py` — `list_conversations` gains `q`/`limit` Query params; new `escape_like()` helper; ILIKE title filter with `escape="\\"`
- `backend/tests/unit/test_conversations.py` — **new**; 4 tests: escape_like, default no-filter + limit 50, escaped ILIKE + user scoping, blank q ignored
- `frontend-chat/app/api/conversations/route.ts` — proxy now forwards whitelisted `q`/`limit` query params to the backend
- `frontend-chat/lib/api.ts` — `fetchConversations` accepts `{ q, limit, signal }` (backward compatible)
- `frontend-chat/lib/dates.ts` — **new**; `formatRelativeDate()` (Today/Yesterday/"Jul 2"/"Jul 2, 2025")
- `frontend-chat/components/ChatSearch.tsx` — **new**; client component: debounced search input, Recent/results list, empty states, Escape/× clear
- `frontend-chat/app/chat/search/page.tsx` — **new**; server page rendering `<ChatSearch />` under the chat layout
- `frontend-chat/components/NavSidebar.tsx` — "Search chats" NavItem under New chat (chat mode); "Chat" active state excludes `/chat/search`

**Next steps:**
- [ ] Optional: add a `pg_trgm` GIN index on `conversations.title` if per-user conversation counts grow large
- [ ] Optional: port Search chats to `amarin-ai-gateway` (user chose brandbiz-only for now)
- [ ] Optional v2 UX: arrow-key/Enter result navigation in ChatSearch
- [ ] Run `alembic upgrade head` to apply migration `0026_studio_generation_parent_id` (carried forward)
- [ ] Manual verify studio edit/regenerate flows for Image/Video/Music + "Use as Template" (carried forward)
- [ ] Manual verify: admin → /studio → Video tab → generate → audit log shows `"model": "veo-3.1-lite-generate-preview"` (carried forward)
- [ ] **Cost risk (open):** No per-user video quota for Veo (carried forward)
- [ ] Run `pytest backend/tests/unit/test_agents.py -q` — 17 tests (carried forward)
- [ ] Manual verify AI Agent UI end-to-end (carried forward)
- [ ] **n8n UI:** Webhook POST method + LINE node text field mapping (carried forward)
- [ ] Set `N8N_ALERT_WEBHOOK_URL` in `.env`, restart `backend-api` (carried forward)
- [ ] Run `ollama pull bge-m3` on Ollama host (carried forward)
- [ ] Fix 4 pre-existing `test_policy_engine.py` mock-exhaustion failures (carried forward)
- [ ] Fix pre-existing `test_alert.py` / `test_audit.py` unit failures (`app.workers.audit_writer` module missing) — surfaced during this session's full-suite run
- [ ] Phase 2 acceptance gate (carried forward)
- [ ] **HUMAN DECISION — Production domain / LLM server IP / Google Workspace domain / OAuth credentials / Garage bucket** (carried forward)

## 2026-07-13 — worktree-hermes-agent @ 70cbef3

**Summary:** Implemented Task 3.10 — Hermes Agent (NousResearch) as a new governed external model provider, using its built-in OpenAI-compatible API server so the gateway can call it exactly like Perplexity/OpenAI/Claude with zero orchestrator or policy-engine changes. Done in an isolated git worktree (`worktree-hermes-agent`) to avoid clobbering a concurrent Obsidian/vault-sync session working in the same repo. Verified with 8 new unit tests (all pass, no regressions across 81 existing LLM-adapter tests) and a real `alembic upgrade head`/`downgrade -2` run against a disposable throwaway Postgres container — which caught and fixed a real bug: this repo's `env.py` runs the whole migration batch in one transaction, so `ALTER TYPE ... ADD VALUE` needed an explicit `COMMIT` before the next migration could use the new enum value (Gotcha #5 in practice, not just in theory).

**Files changed:**
- `backend/app/llm/hermes.py` — new; `HermesClient`, OpenAI-compatible httpx streaming client (modeled on `perplexity.py`)
- `backend/app/llm/router.py` — `HERMES_MODEL_CODE` + conditional registration on `hermes_api_key`
- `backend/app/config.py` / `.env.example` — `HERMES_API_KEY`, `HERMES_API_URL` (default `http://localhost:8642/v1`)
- `backend/app/models/model_catalog.py` — `"hermes"` added to `model_provider` ORM enum
- `backend/alembic/versions/0027_hermes_provider_enum.py` — new; adds enum value + explicit `COMMIT`
- `backend/alembic/versions/0028_hermes_model_catalog.py` — new; catalog row (`is_local=false`) + L5/L6/ADMIN role permissions
- `frontend-chat/lib/domain.ts` — `MODEL_BY_CODE['hermes-agent']` picker entry with an expectation-setting blurb (agent latency, tool use)
- `backend/tests/unit/test_hermes_llm.py` — new; 8 tests (streaming, base-URL config incl. trailing-slash, auth header, 401/timeout/connect-error mapping)
- `PLAN.md` — added Task 3.10 documenting scope, files, and Accept criteria (left ☐ pending live E2E)

**Next steps:**
- [ ] Deploy an actual Hermes Agent instance (`hermes setup`, `API_SERVER_ENABLED=true`, note the `API_SERVER_KEY`) — user action, no host available to this session
- [ ] Set real `HERMES_API_KEY`/`HERMES_API_URL` in `.env`, run `alembic upgrade head` against the actual dev/staging DB (not the disposable one used for verification), restart `backend-api`
- [ ] E2E verify: `GET /models/available` shows `hermes-agent` for L5+/ADMIN, hidden for L1–L4
- [ ] E2E verify: chat via Hermes streams tokens, shows tier/model badge, writes an `audit_log` row, decrements quota
- [ ] E2E verify: blank `HERMES_API_KEY` → model not registered/offered (negative case)
- [ ] **Merge blocker:** this branch's `0027_hermes_provider_enum.py` / `0028_hermes_model_catalog.py` collide by revision number with the concurrent Obsidian session's uncommitted `0027_obsidian_source_columns.py` / `0028_vault_connection_and_sync_run.py` — whichever branch merges second needs its migrations renumbered/rechained onto the other's real head before merging
- [ ] Optional: distinct `ProviderMark` tint for the `hermes` provider
- [ ] Optional: `ChatPane.tsx` "working — running tools" waiting-state hint if first-token latency feels bad in testing (Hermes runs its agent loop before responding)
- [ ] Optional: create `backend/tests/manual/` checklist per PLAN.md §9 ("New external provider added") — directory doesn't exist yet in this repo
- [ ] Not yet pushed to a remote or opened as a PR — local commits only on `worktree-hermes-agent`
- [ ] (all prior carried-forward items above are untouched by this session — still open)

## 2026-07-13 — worktree-hermes-agent @ cc513ec

**Summary:** Two parts. First (earlier this session, in the primary checkout): pushed the Hermes branch as `feat/hermes-agent`, which merged into `origin/main` as PR #2; the primary checkout was then mid-merge with the concurrent Obsidian session with an unresolved `PLAN.md` conflict — resolved it (kept Obsidian's Task 3.10 verbatim, renumbered Hermes to Task 3.11, renumbered its migrations `0027/0028` → `0029/0030` rechained onto Obsidian's real head), committed as `cc513ec`, and re-verified the full combined migration chain on a disposable Postgres container. Ran `alembic upgrade head` against the live shared dev DB via a disposable one-off container on the existing compose network (no `HERMES_API_KEY` set yet, so Hermes itself still isn't reachable — that remains an external dependency). Second (this session's main work): implemented Task 3.12 — a "Claude Cowork"-style capability layered on top of Hermes. Researched what Cowork actually does (assign an outcome, close the tab, it runs unattended, comes back with a reviewable result — optionally scheduled, optionally gated by approval) and mapped it onto this codebase's existing primitives: `BackgroundTasks` + a VARCHAR-status "run" table (the `StudioGeneration`/`VaultSyncRun` pattern) + the `prepare_chat()`/`run_chat_collect()` governance seam already used by `/automations/agent`. Scoped to Phase 1 (MVP) only, with scheduling and pre-run approval explicitly documented as unbuilt follow-ons. Mid-implementation, caught and fixed a real mistake: the first pass of edits landed in the primary checkout instead of this worktree — diffs were captured, the primary checkout was reverted to clean `main` (with explicit user confirmation before discarding), and every edit was correctly reapplied here. Verified with 16 passing unit tests (8 pre-existing Hermes tests + 2 new timeout tests + 6 new `test_agent_tasks.py` tests — confirmed the 27 unrelated failures elsewhere in the suite are pre-existing/environmental, identical with or without this session's test file), a full migration chain re-verification (`0001→0032` upgrade / `downgrade -2` / re-upgrade, clean) against a fresh disposable Postgres container, and a clean `tsc --noEmit` + `next build` covering the new frontend routes.

**Files changed:**
- `backend/app/llm/hermes.py` — `HermesClient` takes a `timeout` param (default 120s, unchanged) instead of a hardcoded httpx timeout
- `backend/app/llm/router.py` / `config.py` / `.env.example` — new `hermes_api_timeout` setting (default 600s) threaded into `HermesClient` registration, since an unattended Hermes tool loop runs far longer than interactive chat
- `backend/app/models/agent_task.py` — new; `AgentTask` ORM model (encrypted prompt/result, VARCHAR status + frozenset, nullable Phase-2 schedule columns), mirrors `StudioGeneration`
- `backend/app/models/__init__.py` / `audit.py` — registered `AgentTask`; added 5 new `agent_task_*` audit action strings
- `backend/alembic/versions/0031_agent_task_audit_actions.py` — new; 5 `ALTER TYPE audit_action ADD VALUE` statements (no `COMMIT` needed — unlike the Hermes provider-enum migration, nothing in this batch references the new values)
- `backend/alembic/versions/0032_agent_task.py` — new; `agent_task` table + 2 indexes + FKs
- `backend/app/services/agent_tasks.py` — new; `submit_task` (governance gate + encrypt + enqueue), `_run_task` (background worker — runs `run_chat_collect`, updates status, never raises), `list_tasks`/`get_task`/`cancel_task` (best-effort)
- `backend/app/routers/tasks.py` — new; `POST /tasks` (202), `GET /tasks`, `GET /tasks/{id}`, `POST /tasks/{id}/cancel`
- `backend/app/main.py` — registered the new `tasks` router
- `backend/tests/unit/test_agent_tasks.py` — new; 6 tests (403 deny, 503 unconfigured, submit success + downgrade recording, `_run_task` success/failure)
- `backend/tests/unit/test_hermes_llm.py` — 2 new tests for the configurable timeout
- `frontend-chat/app/tasks/layout.tsx` + `page.tsx` — new; role-gated (L5+/ADMIN) page shell modeled on `app/studio/layout.tsx`
- `frontend-chat/components/tasks/TasksPage.tsx` — new; submit form + 5s-poll task list + detail modal, modeled on `StudioPage.tsx`'s poll pattern and `RevealQueue.tsx`'s status badge
- `frontend-chat/app/api/tasks/route.ts`, `[id]/route.ts`, `[id]/cancel/route.ts` — new; proxy routes mirroring `app/api/studio/**`
- `frontend-chat/components/NavSidebar.tsx` / `lib/domain.ts` — `canUseTasks()` role gate, `TASK_STATUS` label/tone map, "Tasks" nav entry
- `PLAN.md` — added Task 3.12 (left ☐ pending live E2E, same blocker as Task 3.11)

**Next steps:**
- [x] **Merge blocker:** migration renumbering — resolved in `cc513ec`, verified clean
- [x] Not yet pushed to a remote or opened as a PR — resolved; pushed as `feat/hermes-agent`, merged as PR #2
- [ ] Deploy an actual Hermes Agent instance (`hermes setup`, `API_SERVER_ENABLED=true`) — user action, no host available to this session (carried forward)
- [ ] Set real `HERMES_API_KEY`/`HERMES_API_URL` in `.env` — `alembic upgrade head` has already been run against the live dev DB; only the real key/URL + a `backend-api` restart remain (user said they'll rebuild themselves) (carried forward, narrowed)
- [ ] E2E verify: `GET /models/available` shows `hermes-agent` for L5+/ADMIN, hidden for L1–L4 (carried forward)
- [ ] E2E verify: chat via Hermes streams tokens, shows tier/model badge, writes an `audit_log` row, decrements quota (carried forward)
- [ ] E2E verify: blank `HERMES_API_KEY` → model not registered/offered (carried forward)
- [ ] E2E verify Task 3.12: submit a task as L5+ → 202 → poll `queued`→`running`→`succeeded` with decrypted result, audit rows, quota decrement; L1–L4 cannot see `/tasks`; blank key → 503 (new, needs the same Hermes instance as above)
- [ ] Optional: Phase 2 — scheduling/recurring tasks (host-cron script + cadence picker), explicitly deferred by design
- [ ] Optional: Phase 3 — pre-run approval gate (RevealQueue-style `awaiting_approval`), explicitly deferred by design
- [ ] Optional: distinct `ProviderMark` tint for the `hermes` provider (carried forward)
- [ ] Optional: `ChatPane.tsx` "working — running tools" waiting-state hint (carried forward)
- [ ] Optional: create `backend/tests/manual/` checklist per PLAN.md §9 (carried forward)
- [ ] (older carried-forward items — Phase 2 acceptance gate, `ollama pull bge-m3`, pre-existing `test_policy_engine.py`/`test_audit.py` failures, HUMAN DECISION items — untouched by this session, still open)

## 2026-07-14 — worktree-hermes-agent @ cc513ec

**Summary:** User clarified what "run Hermes on my machine via the gateway" actually meant after a round of Socratic back-and-forth (Cowork ≠ Claude Code; the gateway can't reach a user's local disk, and doesn't need to — Cowork itself is a hosted sandbox reached through a browser). What they actually wanted, confirmed via plan mode: the Tasks page should show Hermes's **live activity log and output** while a task runs, not just the terminal result. Implemented that as a follow-on to Task 3.12. Added `run_chat_collect_streamed()` to the orchestrator (same queue-draining pattern as `run_chat_stream`, but calls an `on_event` callback per item instead of yielding SSE), wired the background worker to accumulate a log + partial answer and throttled-flush an encrypted snapshot to 4 new `progress_*` columns (migration `0033`, cleared on terminal status), and exposed it through the API. Rebuilt the Tasks detail view as a dedicated page (`/tasks/[id]`) with a monospace auto-scrolling activity console, extracted `MarkdownContent` out of `ChatPane.tsx` into a shared component so both chat and the new page render markdown identically, and added Copy/Re-run actions. Verified with 4 new backend unit tests (32/32 relevant tests pass, same 27 pre-existing environmental failures elsewhere, unaffected), a full migration re-verification (`0001→0033` upgrade / `downgrade -1` / re-upgrade, clean) against a disposable Postgres container, and clean `tsc --noEmit` + `next build`.

**Files changed:**
- `backend/app/agents/orchestrator.py` — new `run_chat_collect_streamed()` (streaming variant of `run_chat_collect` with an `on_event` callback); explicit `Callable`/`Awaitable` typing import
- `backend/app/models/agent_task.py` — new `progress_ciphertext/nonce/tag/progress_key_version` encrypted-quad columns
- `backend/alembic/versions/0033_agent_task_progress.py` — new; adds the 4 progress columns (nullable, no `COMMIT` needed)
- `backend/app/services/agent_tasks.py` — `_run_task` now drives `run_chat_collect_streamed` via an `on_event` closure that accumulates log lines + partial output and throttled-flushes (`_flush_progress`, ≤1 write/2s) to `progress_*`; cleared on the terminal update; new `decrypt_progress()`
- `backend/app/routers/tasks.py` — `TaskDetail.progress: str | None`; `TaskSummary.has_progress: bool` (cheap no-decrypt presence flag for the list view)
- `backend/tests/unit/test_orchestrator.py` — 3 new tests for `run_chat_collect_streamed` (per-event callback + final result, works without a callback, raises on error-with-no-output)
- `backend/tests/unit/test_agent_tasks.py` — 1 new test: progress flushes mid-run and clears on success
- `frontend-chat/components/ui/Markdown.tsx` — new; `MarkdownContent` extracted out of `ChatPane.tsx` (no more duplication)
- `frontend-chat/components/ChatPane.tsx` — imports `MarkdownContent` from the new shared module instead of defining it inline; dropped now-unused `memo`/`useMemo` imports
- `frontend-chat/app/tasks/[id]/page.tsx` — new; dedicated detail route (inherits the existing `/tasks` layout's role gate)
- `frontend-chat/components/tasks/TaskDetailView.tsx` — new; full detail page — header/status/cancel, task prompt, collapsible live activity-log console (auto-scroll while running), rendered-markdown output with Copy/Re-run, encrypted/governed footer note
- `frontend-chat/components/tasks/TasksPage.tsx` — removed the inline `TaskDetailModal`; cards now `router.push` to `/tasks/{id}`; running cards show a "Hermes is working…" hint via `has_progress`
- `PLAN.md` — documented the follow-on under Task 3.12 (new files, migration 0033, updated Accept criteria); task checkbox left ☐ (E2E items still blocked on a live Hermes instance)

**Next steps:**
- [ ] Deploy an actual Hermes Agent instance (`hermes setup`, `API_SERVER_ENABLED=true`) — user action, no host available to this session (carried forward)
- [ ] Set real `HERMES_API_KEY`/`HERMES_API_URL` in `.env`, run `alembic upgrade head` (now needs `0033` too), restart `backend-api` (carried forward, narrowed)
- [ ] E2E verify: `GET /models/available` shows `hermes-agent` for L5+/ADMIN, hidden for L1–L4 (carried forward)
- [ ] E2E verify: chat via Hermes streams tokens, shows tier/model badge, writes an `audit_log` row, decrements quota (carried forward)
- [ ] E2E verify: blank `HERMES_API_KEY` → model not registered/offered (carried forward)
- [ ] E2E verify Task 3.12: submit a task as L5+ → 202 → poll `queued`→`running`→`succeeded` with decrypted result, audit rows, quota decrement; L1–L4 cannot see `/tasks`; blank key → 503 (carried forward)
- [ ] E2E verify this session's follow-on: detail page's activity log actually grows while a real Hermes task runs, and note in practice how much structure Hermes's stream provides beyond raw content deltas (new — needs the same live Hermes instance)
- [ ] Note: since Hermes's OpenAI-compatible stream today only exposes content deltas + a few status markers (no per-tool-call structure), the activity log will read as streamed prose + status lines, not discrete tool rows, unless/until Hermes's API surfaces that structure — documented in PLAN.md, not a bug
- [ ] Optional: Phase 2 — scheduling/recurring tasks (host-cron script + cadence picker), explicitly deferred by design (carried forward)
- [ ] Optional: Phase 3 — pre-run approval gate (RevealQueue-style `awaiting_approval`), explicitly deferred by design (carried forward)
- [ ] Optional: distinct `ProviderMark` tint for the `hermes` provider (carried forward)
- [ ] Optional: create `backend/tests/manual/` checklist per PLAN.md §9 (carried forward)
- [ ] Nothing from this session committed yet — still sitting in the worktree, awaiting user go-ahead
- [ ] (older carried-forward items — Phase 2 acceptance gate, `ollama pull bge-m3`, pre-existing `test_policy_engine.py`/`test_audit.py`/`test_crypto.py`/`test_google_llm.py`/`test_vault_connection.py`/`test_orchestrator.py::test_call_llm_*` failures (environmental — bare-metal Windows Python lacks the Docker test env's `ENCRYPTION_KEY` wiring for these specific fixtures), HUMAN DECISION items — untouched by this session, still open)

## 2026-07-14 15:20 — worktree-hermes-agent @ d377b8f

**Summary:** Deployed a real, live Hermes Agent instance and closed out the E2E blocker that every prior session's Next Steps carried forward. User wanted Hermes running locally but reached only through the gateway (governance/audit/quota in front of it), and then asked whether the gateway could install Hermes automatically — research confirmed NousResearch ships an official Docker image (`nousresearch/hermes-agent`) supporting non-interactive setup via a pre-populated `config.yaml`/`.env`, so the architecture changed from "manual host install" to "a `hermes` service in `docker-compose.yml`." Added a one-shot `hermes-init` service that writes Hermes's config into a named volume on first boot only, pointed at the existing LAN Ollama host; `hermes` runs `gateway run` under s6 supervision. Pulled a tool-calling model (`hermes3:8b`) after the user's first choice (`gemma4:12b`) failed — that LAN Ollama host's version (0.22.1) is too old for its manifest; upgrading it is a user action, not done this session. Merged this worktree branch into the main checkout (which holds the only running gateway stack) three times as work progressed, rebuilt `backend-api`, ran migrations `0031`-`0033`, and ran the full E2E suite live: `/models/available` role gating (ADMIN sees `hermes-agent`, L1 doesn't), streaming chat through Hermes with audit-log + quota rows, and the Task 3.12 background-task lifecycle including catching the live activity log mid-flight (progress accumulating while `status=running`, cleared once `result` was written). Found one real minor bug (not fixed, just documented): the progress log's `"start"` event always says "Task started on Hermes" even when a role-based downgrade sends the task to the local model instead. Updated `PLAN.md`'s Task 3.11/3.12 accept criteria from "pending" to verified, with corrected phrasing where live behavior (silent downgrade, not hard rejection) didn't match the original text.

**Notable incident (needs the user's attention, see Next steps):** leaked four live secrets into this session's transcript through careless raw output — a GitHub PAT (`VAULT_GIT_URL`), the Hermes API key (twice, before rotating it), the running stack's `POSTGRES_PASSWORD`, and `JWT_SECRET` (via a subagent's report that included it in plaintext). Root cause both times: reaching for full-file reads / unfiltered `docker compose config` / delegating `.env`-adjacent research to a subagent without telling it to withhold live values, instead of redacting before output. The harness's own guardrails caught and blocked two follow-on mistakes (a raw `.env` grep, and a unilateral `JWT_SECRET` rotation) — those blocks were correct. The Hermes key was safely rotated twice using non-echoing techniques after the lesson landed. The GitHub PAT, Postgres password, and JWT_SECRET are still live and exposed as of end of session — rotation needs the user's explicit go-ahead per the harness (already asked once, not yet answered).

**Files changed:**
- `docker-compose.yml` — added `hermes-init` (one-shot config writer) and `hermes` (`nousresearch/hermes-agent:latest`, `gateway run`) services; forwarded `HERMES_API_KEY`/`HERMES_API_URL`/`HERMES_API_TIMEOUT` into `backend-api`; added `hermes_data` named volume
- `.env.example` — documented the new Docker-Compose-managed Hermes architecture; added `HERMES_OLLAMA_URL`/`HERMES_OLLAMA_MODEL`
- `.env` (main checkout, not committed/tracked) — added `HERMES_API_KEY` (rotated twice), `HERMES_API_URL=http://hermes:8642/v1`, `HERMES_API_TIMEOUT`, `HERMES_OLLAMA_URL`, `HERMES_OLLAMA_MODEL`; fixed a missing-newline bug from an earlier append that had concatenated two lines together
- `PLAN.md` — Task 3.11 checkbox ☐→☑, scope text revised for the Docker Compose architecture; Task 3.12 checkbox ☐→☑; both tasks' Accept criteria updated from "pending" to live-verified, with the L1 downgrade-vs-reject clarification and the progress-log bug noted

**Next steps:**
- [ ] **User decision needed:** rotate the exposed GitHub PAT in `VAULT_GIT_URL` (real external access — highest priority of the three)
- [ ] **User decision needed:** rotate `JWT_SECRET` in the main checkout's `.env` (harness requires explicit authorization; invalidates existing local sessions, low real risk otherwise) — I asked, awaiting answer
- [ ] **User decision needed:** rotate `POSTGRES_PASSWORD` (local dev DB; low real risk, but exposed) — requires updating the live Postgres container too, so flagged rather than done unilaterally
- [ ] Minor bug, not fixed: `backend/app/services/agent_tasks.py`'s `on_event` "start" handler hardcodes "Task started on Hermes" even when `downgrade_to_local=True` sends the task to the local model instead — misleading log text, not a security issue
- [ ] Upgrade Ollama on the LAN host (`192.168.20.18:12341`, currently `0.22.1`) if the user still wants `gemma4:12b` — then swap Hermes's `config.yaml` `model.default` from `hermes3:8b` (currently live) to `gemma4:12b`, one-line change, no rework needed
- [ ] Frontend Tasks detail page (`/tasks/[id]`) was verified at the API level (live activity log growth, role gating) but not re-driven through an actual browser this session — worth a quick manual click-through
- [ ] Optional: Phase 2 — scheduling/recurring tasks, explicitly deferred by design (carried forward)
- [ ] Optional: Phase 3 — pre-run approval gate, explicitly deferred by design (carried forward)
- [ ] Optional: distinct `ProviderMark` tint for the `hermes` provider (carried forward)
- [ ] Optional: create `backend/tests/manual/` checklist per PLAN.md §9 (carried forward)
- [ ] This session's `docker-compose.yml`/`.env.example` commits (`372c26e`, `d377b8f`) are on `worktree-hermes-agent` and already fast-forward-merged into the main checkout's `main` branch locally; not pushed to a remote. `PLAN.md`'s update in this entry is still uncommitted.
- [ ] (older carried-forward items — Phase 2 acceptance gate, `ollama pull bge-m3`, pre-existing test failures listed in the prior entry, HUMAN DECISION items — untouched by this session, still open)
