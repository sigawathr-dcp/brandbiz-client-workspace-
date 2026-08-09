# Production Readiness Gap Report

Generated: 2026-06-29

---

## Critical — blocks production

| # | Gap | Detail |
|---|-----|--------|
| 1 | **Uncommitted changes** | 12 modified backend files + 11 Alembic migrations (0011–0021) + all agent/studio/music/video/library/agent frontend work are **untracked/uncommitted**. Server redeploy from a clean clone would lose all of it. |
| 2 | **SSE `sources` event not rendered** ✅ Fixed | `image` events were already handled (`ChatPane.tsx:529`). `sources` events were silently dropped — the dispatch chain had no branch for them, so RAG citations never reached the user. Fixed: `SourcesPanel` component added; `Message` interface extended with `sources?: Source[]`; citations now display as a collapsible "Sources (N)" panel under each RAG answer. Requires gap #3 (`bge-m3` pull) to produce visible citations. |
| 3 | **BGE-M3 not pulled on Ollama host** | `ollama pull bge-m3` never run on `192.168.20.18`. RAG search (`retrieve()`) silently returns empty results for every query. |
| 4 | **n8n LINE alert broken** | `N8N_ALERT_WEBHOOK_URL` not set in `.env`; n8n Webhook node HTTP method and LINE node field mapping not wired in the UI. The "server is down" → LINE alert flow is dead. |
| 5 | **4 test_policy_engine.py failures** ✅ Fixed | 16/16 pass. The four quota-path tests (`TestHappyPath`, `TestDepartmentAddOn`, both `TestQuotaExceeded`) previously exhausted their `AsyncMock(side_effect=[...])` lists because `_get_or_create_current_quota()` issues 3 `execute()` calls (SELECT QuotaDefault → INSERT ON CONFLICT DO NOTHING → SELECT Quota). The `_quota_sequence()` helper was added to supply exactly those 3 return values; all failures are resolved. |
| 6 | **Phase 2 acceptance gate not passed** | All 100 employees must be onboarded, one billing cycle verified against provider invoices (<5% variance), at least one real reveal flow end-to-end, and audit log showing zero Tier 3+ external calls. |

---

## Important — production quality

| # | Gap | Detail |
|---|-----|--------|
| 7 | **No per-user video quota** | L5/L6/ADMIN + MKT users can submit unlimited paid Veo 3.1 Lite jobs. No cost ceiling. |
| 8 | **Task 3.7 not started** | Single `llamacpp-primary` instance = single point of failure for local LLM. Under 15 concurrent users, one crash kills everyone. |
| 9 | **ENCRYPTION_KEY in env var** | Phase 4 Decision D13 — still using env var. Key compromise = all message history readable. Plan called for Vault/KMS migration. |
| 10 | **No backups** | No nightly `pg_dump`. Data loss on disk failure = permanent. |
| 11 | **No rate limiting** | Any authenticated user can hammer the API. No per-user request-per-minute cap. |
| 12 | **No observability** | Langfuse not wired (Phase 4). Prometheus/Grafana not set up. No visibility into GPU temp, queue depth, LLM latency, error rates in production. |
| 13 | **Manual verification pending** | AI Agent UI end-to-end, True Studio Image and Video tabs, and Library tab all carried forward as "manual verify" — never confirmed working in production. |
| 14 | **Open questions unresolved** (PLAN.md §12) | Who are Tier 4 actors? Can ADMIN self-approve reveals? What is audit log retention limit per Legal? What is the default model on "auto"? |

---

## Blocked on infrastructure / external

| # | Gap | Detail |
|---|-----|--------|
| 15 | **GPU box not tested** | llamacpp-primary VRAM budget and p95 < 5s latency (Phase 1 gate) never verified — dev machine has no GPU. |
| 16 | **Phase 1 acceptance gate** | 10 employees × 1 week soak with GPU never ran. This is a prerequisite to Phase 2 going wide. |
| 17 | **Pen test** | Phase 4 item — required before opening beyond pilot per PLAN.md §4. |

---

## Found during server-spec.md review (2026-08-06)

Surfaced while fact-checking `docs/deck/server-spec.md`'s license-tier sizing table. None of these
are fixed by more CPU/RAM — they cap capacity regardless of hardware tier. See `server-spec.md` §6.1
for the customer-facing summary; this section has the specifics.

### Critical

| # | Gap | Detail |
|---|-----|--------|
| 18 | **DB connection pool unset — caps concurrency below the project's own target** | `backend/app/db.py:7` creates the async engine with no `pool_size`/`max_overflow`. SQLAlchemy defaults apply: 5 + 10 = 15 connections total. A streaming chat request holds one connection for up to `llm_read_timeout` = 120s (`config.py:42`), while `services/audit.py:36-49` opens a second, independent connection from the same pool mid-turn. Net: ~7–8 concurrent chats before the pool blocks for `pool_timeout` (30s default) and then raises — below `PLAN.md` §1's ~15-concurrent target, on any hardware tier. |
| 19 | **Studio gallery response can OOM the server** | `GET /studio/generations` (`app/routers/studio.py:103-122`) returns `GenerationResponse.output_ref` (full base64 data URL) for up to 500 rows (`Query(ge=1, le=500)`). At the doc's own 1.3–8 MB/video figure, one page load is a 65 MB–4 GB response — materialized as ORM objects, then Pydantic models, then re-buffered whole by `await res.json()` in `frontend-chat/app/api/studio/generations/route.ts`. A handful of concurrent gallery opens can OOM-kill the smallest (Standard) tier regardless of RAM headroom elsewhere. |
| 20 | **`--reload` is the deployed command, not `--workers 4`** | `backend/Dockerfile` CMD sets `--workers 4`, but `docker-compose.yml:22` overrides it with `uvicorn ... --reload` — one worker process plus a filesystem watcher, as the actual production config. Fixing this isn't a one-line change: `app/main.py:59` runs `alembic upgrade head` at process startup, which N worker processes would race, so the migration needs to be extracted to a separate startup step first. |

### Important

| # | Gap | Detail |
|---|-----|--------|
| 21 | **Postgres has zero tuning** | `docker-compose.yml`'s `postgres` service has no `command:`, no config file mount, no `POSTGRES_INITDB_ARGS`; `db/init/` holds only a README. Stock `pgvector/pgvector:pg16` defaults apply: `shared_buffers=128MB`, `work_mem=4MB`, `maintenance_work_mem=64MB`, `effective_cache_size=4GB`. `maintenance_work_mem` at 64MB holds only ~14,000 HNSW vectors (~24 MB of source corpus) before index builds fall back to the slow on-disk path — this directly undercuts the advertised RTO ≤4hr, since a `pg_dump` restore rebuilds the HNSW index from scratch. |
| 22 | **Upload path buffers the same file ~4 times, and checks size after reading it all** | `app/routers/files.py:95-96` — `data = await file.read()` reads the entire body before the size check on the next line, so an oversized POST is fully buffered before being rejected. `io.BytesIO(data)` (a second copy) is then re-read by `ingestion.save_upload` (a third). The Next.js BFF (`frontend-chat/app/api/files/route.ts`) buffers a fourth copy as `FormData` before forwarding. No global concurrency cap on uploads — N simultaneous 50MB uploads ≈ 150·N MB in Python + 50·N MB in Node, uncapped. |
| 23 | **Ingestion accumulates unbounded ORM state before committing** | `app/services/ingestion.py:233-280` builds every `FileChunk` (each carrying a 1024-float embedding list, ~32KB in CPython) in memory and commits once at the end. A 50MB text document ≈ 29,000 chunks ≈ ~900MB of pending ORM state in a single `BackgroundTasks` call, with no batching or intermediate commit. |
| 24 | **Admin audit endpoints scale linearly forever, with no purge** | `GET /admin/audit` (`app/routers/admin.py:743-745`) runs an unfiltered `SELECT count(*)` over `audit_log` on every page load — a full sequential scan, since neither `idx_audit_user` nor `idx_audit_action` helps an unfiltered count, and the table is never purged or partitioned (see main gap list re: D14, migration `0003_audit_partitions` deleted). `GET /admin/audit/export.csv` (`admin.py:784-786`) materializes up to 50,000 fully-hydrated ORM rows in memory (`max_rows` up to 50000) before the "streaming" response emits its first byte. |
| 25 | **Missing indexes on hot dashboard/pagination paths** | No index on `messages.model_used`, despite `admin.py:578-586` and `:634-640` joining `messages` to `model_catalog` on it and aggregating `SUM(cost_usd)`/`SUM(tokens_*)` over a full month — sequential scan on every dashboard load. `studio_generations` has only `ix_studio_generations_user_id` (`0011_studio_generations.py:35-38`); list queries order by `created_at DESC` with offset/limit (`studio.py:298-302`) with no `(user_id, created_at DESC)` composite, so deep pagination re-sorts the user's full history — each row dragging a multi-MB `output_ref` through the sort. |

---

## Shortest path to "shippable for pilot" (Phase 1+2 gate)

1. Commit all untracked files (migrations 0011–0021, all new models/routers/services/frontend pages)
2. Fix the 4 `test_policy_engine.py` failures
3. Handle `image` and `sources` SSE events in `ChatPane.tsx`
4. `ollama pull bge-m3` on the Ollama host (`192.168.20.18`)
5. Set `N8N_ALERT_WEBHOOK_URL`, wire n8n UI (Webhook POST method + LINE node field mapping)
6. Add a video generation quota cap
7. Onboard pilot users and run Phase 2 acceptance gate
