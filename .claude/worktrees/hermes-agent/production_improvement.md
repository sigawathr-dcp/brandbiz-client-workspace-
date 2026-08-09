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

## Shortest path to "shippable for pilot" (Phase 1+2 gate)

1. Commit all untracked files (migrations 0011–0021, all new models/routers/services/frontend pages)
2. Fix the 4 `test_policy_engine.py` failures
3. Handle `image` and `sources` SSE events in `ChatPane.tsx`
4. `ollama pull bge-m3` on the Ollama host (`192.168.20.18`)
5. Set `N8N_ALERT_WEBHOOK_URL`, wire n8n UI (Webhook POST method + LINE node field mapping)
6. Add a video generation quota cap
7. Onboard pilot users and run Phase 2 acceptance gate
