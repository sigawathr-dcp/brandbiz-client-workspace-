# Production Readiness — Test Cases

Generated: 2026-06-29  
Source: `production_improvement.md`

Each section corresponds to a numbered gap. Each test case has: **ID**, **Title**, **Preconditions**, **Steps**, **Expected Result**, **Pass/Fail**.

---

## Critical — Blocks Production

---

### Gap 1 — Uncommitted Changes

#### TC-01-01 — Git working tree is clean after commit

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Manual / CI |

**Preconditions**  
- Developer has staged and committed all files listed in the gap report (migrations 0011–0021, backend models/routers/services, frontend pages).

**Steps**  
1. Run `git status` in the repository root.  
2. Run `git stash list`.  
3. Clone the repository to a clean temp directory and compare file trees with the main working directory.

**Expected Result**  
- `git status` shows `nothing to commit, working tree clean`.  
- `git stash list` is empty (no stashed work hiding changes).  
- Clean clone contains all migration files `0011` through `0021` and all new frontend/backend files.

**Pass Criteria** All three checks pass with zero missing files.

---

#### TC-01-02 — Fresh clone boots without migration errors

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Manual |

**Preconditions**  
- All files committed (TC-01-01 passes).  
- Docker and `docker compose` available.

**Steps**  
1. `git clone <repo-url> /tmp/clean-clone && cd /tmp/clean-clone`  
2. Copy `.env.example` to `.env` and fill required secrets.  
3. `docker compose up -d db && sleep 5`  
4. `docker compose run --rm backend alembic upgrade head`  
5. Check the alembic version table: `SELECT version_num FROM alembic_version;`

**Expected Result**  
- Alembic completes with `Done` and no errors.  
- Version table contains the head revision from migration `0021`.

---

### Gap 2 — SSE `sources` Event Rendering (Fixed)

#### TC-02-01 — Sources panel renders on RAG answer

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Manual / Browser |

**Preconditions**  
- `bge-m3` model pulled on Ollama host (`192.168.20.18`) — Gap 3 resolved.  
- At least one document ingested into the knowledge base.  
- Frontend running against the backend.

**Steps**  
1. Log in as any non-guest user.  
2. Open the Chat pane and send a query whose answer is covered by an ingested document (e.g., "What is the company's leave policy?").  
3. Observe the streaming response in the chat bubble.  
4. After the answer completes, look below the message.

**Expected Result**  
- A collapsible **"Sources (N)"** panel appears below the assistant message where N ≥ 1.  
- Expanding the panel shows titles and/or URLs of the source documents.  
- No `sources` event errors appear in the browser console.

---

#### TC-02-02 — `image` SSE event still renders (regression check)

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Manual / Browser |

**Steps**  
1. Request an image generation (e.g., "Generate an image of a mountain lake").  
2. Observe the chat pane during and after generation.

**Expected Result**  
- The generated image appears inline in the chat bubble.  
- No regression — image display behaviour is unchanged from before the sources fix.

---

#### TC-02-03 — No SSE events silently dropped (unit)

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Automated / Unit |

**Steps**  
1. In `frontend-chat/components/ChatPane.tsx`, locate the SSE dispatch switch/if-chain.  
2. Assert that branches exist for: `text`, `image`, `sources`, `error`, `done`.  
3. Run `npm test -- --testPathPattern=ChatPane` (or equivalent).

**Expected Result**  
- All SSE event types have an explicit handler branch — no fall-through to an unhandled default.  
- Unit tests pass (0 failures).

---

### Gap 3 — BGE-M3 Not Pulled on Ollama Host

#### TC-03-01 — BGE-M3 model available on Ollama host

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Manual / Infrastructure |

**Preconditions**  
- SSH access to `192.168.20.18`.

**Steps**  
1. SSH into `192.168.20.18`.  
2. Run `ollama list`.

**Expected Result**  
- Output includes a row for `bge-m3` (or `bge-m3:latest`) with a non-zero size.

---

#### TC-03-02 — RAG retrieve() returns non-empty results

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Automated / Integration |

**Preconditions**  
- TC-03-01 passes.  
- At least one document has been embedded and stored in the vector DB.

**Steps**  
1. Call `backend/app/services/rag_service.py::retrieve(query="<known-doc-content-snippet>", top_k=3)` via the integration test suite or a direct pytest test.  
2. Assert `len(results) >= 1`.  
3. Assert each result has a non-empty `content` field and a `score > 0`.

**Expected Result**  
- `retrieve()` returns ≥ 1 result with meaningful content.  
- No `ConnectionError` or embedding-model-not-found errors in the log.

---

#### TC-03-03 — End-to-end RAG chat answer cites sources

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Manual / E2E |

**Steps**  
1. Ingest a test document with unique, searchable text (e.g., "The annual gala is held on December 12th").  
2. Ask the chatbot: "When is the annual gala?"  
3. Verify the answer and check the Sources panel (TC-02-01).

**Expected Result**  
- The answer references December 12th.  
- The Sources panel shows the ingested test document.

---

### Gap 4 — n8n LINE Alert Broken

#### TC-04-01 — `N8N_ALERT_WEBHOOK_URL` is set in `.env`

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Configuration Check |

**Steps**  
1. On the production server, run: `grep N8N_ALERT_WEBHOOK_URL .env`  
2. Confirm the value is a non-empty URL pointing to the n8n Webhook node.

**Expected Result**  
- Variable is present and non-empty.  
- URL responds with `200 OK` on a test `POST` (using `curl -X POST <url> -d '{}'`).

---

#### TC-04-02 — n8n Webhook node configured for HTTP POST

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Manual / n8n UI |

**Steps**  
1. Open the n8n UI and navigate to the "Server Down → LINE Alert" workflow.  
2. Click the Webhook trigger node.  
3. Check the **HTTP Method** field.

**Expected Result**  
- HTTP Method is set to `POST`.  
- The Webhook Path matches the URL configured in `N8N_ALERT_WEBHOOK_URL`.

---

#### TC-04-03 — LINE node field mapping is correct

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Manual / n8n UI |

**Steps**  
1. In the n8n workflow, open the LINE Send Message node.  
2. Verify the **To** field maps to the LINE User/Group ID.  
3. Verify the **Message** field references the alert body from the Webhook payload (e.g., `{{$json.body.message}}`).

**Expected Result**  
- Fields are populated with correct JSON path expressions, not static/placeholder values.

---

#### TC-04-04 — Full alert flow fires a LINE message

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Manual / Integration |

**Preconditions**  
- TC-04-01 through TC-04-03 pass.  
- A LINE test channel/user is available.

**Steps**  
1. Simulate a server-down event by running:  
   ```bash
   curl -X POST "$N8N_ALERT_WEBHOOK_URL" \
     -H "Content-Type: application/json" \
     -d '{"message": "TEST: Gateway service is down", "severity": "critical"}'
   ```
2. Wait up to 30 seconds.  
3. Check the LINE test channel.

**Expected Result**  
- A LINE message arrives containing "TEST: Gateway service is down" within 30 seconds.  
- n8n execution log shows status `success` for all nodes.

---

### Gap 5 — 4 `test_policy_engine.py` Failures

#### TC-05-01 — All PolicyEngine unit tests pass

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Automated / Unit |

**Steps**  
1. `cd backend`  
2. `pytest tests/unit/test_policy_engine.py -v 2>&1 | tee pytest_policy.txt`

**Expected Result**  
- Exit code `0`.  
- Output shows `X passed, 0 failed, 0 errors`.  
- No `StopIteration` or `MagicMock exhausted` errors (the mock-exhaustion failures cited in the gap).

---

#### TC-05-02 — PolicyEngine blocks Tier 3+ external calls

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Automated / Unit |

**Steps**  
1. Instantiate `PolicyEngine` with a Tier 3+ request context.  
2. Call `PolicyEngine.decide()` and assert the decision is `DENY` or raises `PolicyViolation`.

**Expected Result**  
- The call is blocked.  
- An `audit_log` entry is written with `action=DENY`.

---

#### TC-05-03 — PolicyEngine allows Tier 1 internal call

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Automated / Unit |

**Steps**  
1. Instantiate `PolicyEngine` with a Tier 1 (internal/local LLM) request context.  
2. Call `PolicyEngine.decide()`.

**Expected Result**  
- Returns `ALLOW`.  
- No audit log `DENY` entry is written.

---

#### TC-05-04 — Full pytest suite passes

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Automated / CI |

**Steps**  
1. `cd backend && pytest -v`

**Expected Result**  
- Exit code `0`, zero failures across all test files.

---

### Gap 6 — Phase 2 Acceptance Gate Not Passed

#### TC-06-01 — All 100 employees onboarded

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Manual / Admin |

**Steps**  
1. Log in as ADMIN.  
2. Navigate to **Admin → Users**.  
3. Count active users.

**Expected Result**  
- Active user count ≥ 100.  
- No user is in `PENDING` or `LOCKED` status unless intentional.

---

#### TC-06-02 — Billing variance ≤ 5% vs provider invoices

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Manual / Finance |

**Steps**  
1. Export the internal `usage_log` / cost aggregation for one full billing cycle.  
2. Obtain the provider invoice for the same period (Google, Anthropic, or other).  
3. Calculate: `|internal_total - invoice_total| / invoice_total * 100`.

**Expected Result**  
- Variance < 5%.

---

#### TC-06-03 — Reveal flow works end-to-end

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Manual / E2E |

**Steps**  
1. As an L5+ user, trigger a "reveal" request for a masked piece of data.  
2. An authorised approver (Tier 4 actor, pending Gap 14 resolution) approves the request.  
3. Verify the data is decrypted and returned to the requester.  
4. Check the audit log for a `REVEAL` event.

**Expected Result**  
- Reveal succeeds.  
- Audit log shows: `action=REVEAL`, `user_id`, `target_data_id`, `approver_id`, timestamp.

---

#### TC-06-04 — Audit log shows zero Tier 3+ external calls for pilot period

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Automated / DB Query |

**Steps**  
1. Run:  
   ```sql
   SELECT COUNT(*) FROM audit_log
   WHERE tier >= 3 AND action = 'ALLOW'
   AND created_at > '<pilot_start_date>';
   ```

**Expected Result**  
- Count = 0 (or the count matches exactly the approved external calls with documented justification).

---

## Important — Production Quality

---

### Gap 7 — No Per-User Video Quota

#### TC-07-01 — Video quota cap is enforced

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Automated / Integration |

**Preconditions**  
- Per-user daily/monthly video job quota is configured (e.g., `VIDEO_QUOTA_PER_USER_DAILY=5`).

**Steps**  
1. Submit `QUOTA_LIMIT + 1` Veo 3.1 Lite video generation requests as the same L5 user within the quota window.  
2. Observe the response on the `QUOTA_LIMIT + 1`-th request.

**Expected Result**  
- Requests 1 through `QUOTA_LIMIT` return `202 Accepted`.  
- Request `QUOTA_LIMIT + 1` returns `429 Too Many Requests` with a clear quota-exceeded message.  
- No additional Veo API calls are made after the quota is hit.

---

#### TC-07-02 — Quota resets at window boundary

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Type** | Automated / Unit |

**Steps**  
1. Advance the system clock or use a mock to simulate the quota window expiring.  
2. Submit a new video request as the same user.

**Expected Result**  
- Request succeeds (`202 Accepted`) — quota counter has reset.

---

#### TC-07-03 — ADMIN users are also subject to quota (or have a higher ceiling)

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Type** | Manual |

**Steps**  
1. Log in as ADMIN.  
2. Submit `ADMIN_QUOTA_LIMIT + 1` video jobs.

**Expected Result**  
- Either ADMIN has a documented, separate (higher) quota that is enforced, OR ADMIN is subject to the same quota as L5/L6 — whichever policy is chosen, it is enforced and not unlimited.

---

### Gap 8 — Task 3.7 Not Started (Single Point of Failure)

#### TC-08-01 — llamacpp-primary failover does not kill active sessions

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Manual / Infrastructure |

**Preconditions**  
- At least two llamacpp instances are running (primary + standby/replica).

**Steps**  
1. Start 5 concurrent chat sessions using the LLM.  
2. While sessions are active, kill the `llamacpp-primary` process/container.  
3. Observe whether in-flight requests complete or are retried transparently.

**Expected Result**  
- In-flight requests either complete (if the gateway buffers) or return a user-friendly retry message within 10 seconds.  
- Within 30 seconds, the standby instance takes over and new requests succeed.  
- No session data is lost.

---

#### TC-08-02 — Health check detects llamacpp crash within 10 seconds

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Automated / Infrastructure |

**Steps**  
1. Kill the `llamacpp-primary` process.  
2. Poll the gateway health endpoint (`GET /health`) every 2 seconds.

**Expected Result**  
- Within 10 seconds of the crash, `/health` reflects degraded/partial status.  
- Alert fires (LINE/n8n, Gap 4) notifying the ops team.

---

### Gap 9 — ENCRYPTION_KEY in Env Var

#### TC-09-01 — ENCRYPTION_KEY is not in `.env` after Vault migration

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Configuration Check |

**Preconditions**  
- Phase 4 Decision D13 migration to Vault/KMS has been completed.

**Steps**  
1. `grep ENCRYPTION_KEY .env .env.example`  
2. Check the running container's env: `docker exec <backend-container> env | grep ENCRYPTION_KEY`

**Expected Result**  
- `ENCRYPTION_KEY` is absent from `.env` and the container environment.  
- The application fetches the key from Vault/KMS at startup (verify in startup logs).

---

#### TC-09-02 — Key rotation does not break message decryption

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Automated / Integration |

**Steps**  
1. Store a test encrypted message using the current key.  
2. Rotate the key in Vault/KMS.  
3. Attempt to decrypt the previously stored message.

**Expected Result**  
- Old messages remain decryptable (key versioning / re-encryption job completed successfully).

---

### Gap 10 — No Backups

#### TC-10-01 — Nightly pg_dump runs and produces a non-empty file

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Manual / Infrastructure |

**Preconditions**  
- Nightly backup cron job configured.

**Steps**  
1. Trigger the backup job manually (or wait for the next scheduled run).  
2. Check the backup destination (S3, NAS, etc.) for a file named with today's date.  
3. Verify the file size is > 0 KB.  
4. Run: `pg_restore --list <backup-file>` (or `zcat <file> | head -20` for plain SQL dumps).

**Expected Result**  
- Backup file exists with today's date.  
- File is non-empty and contains valid SQL/custom-format dump headers.

---

#### TC-10-02 — Backup restore works on a clean DB

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Manual / DR Drill |

**Steps**  
1. Spin up an empty PostgreSQL instance.  
2. Restore from last night's backup: `pg_restore -d testdb <backup-file>`.  
3. Run a spot-check query: `SELECT COUNT(*) FROM users;`

**Expected Result**  
- Restore completes with no errors.  
- Row count matches the production database (within acceptable delta for data written since backup).

---

### Gap 11 — No Rate Limiting

#### TC-11-01 — Per-user API rate limit is enforced

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Automated / Integration |

**Preconditions**  
- Rate limit configured (e.g., `RATE_LIMIT_RPM=60` — 60 requests per minute per user).

**Steps**  
1. As a single authenticated user, send `RATE_LIMIT + 1` requests to `POST /api/chat` within 60 seconds.  
2. Record the HTTP status code of each response.

**Expected Result**  
- Requests 1–`RATE_LIMIT` return `200 OK` (or `202 Accepted`).  
- Request `RATE_LIMIT + 1` returns `429 Too Many Requests`.  
- `Retry-After` header is present on the `429` response.

---

#### TC-11-02 — Rate limit is per-user, not global

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Type** | Automated / Integration |

**Steps**  
1. User A exhausts their rate limit (TC-11-01).  
2. Send a request as User B.

**Expected Result**  
- User B's request succeeds (`200 OK`).  
- User A's bucket does not affect User B.

---

### Gap 12 — No Observability

#### TC-12-01 — Langfuse receives traces for LLM calls

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Manual / Integration |

**Preconditions**  
- Langfuse wired in (Phase 4 task completed).  
- `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` set in `.env`.

**Steps**  
1. Send a chat request through the gateway.  
2. Open the Langfuse UI and navigate to **Traces**.

**Expected Result**  
- A new trace appears within 30 seconds of the request.  
- Trace includes: model name, prompt tokens, completion tokens, latency, and user ID.

---

#### TC-12-02 — Prometheus metrics endpoint is reachable

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Automated / Infrastructure |

**Steps**  
1. `curl http://localhost:9090/metrics` (or the configured Prometheus port).

**Expected Result**  
- Response is `200 OK` with `Content-Type: text/plain`.  
- Output includes at minimum: `http_requests_total`, `llm_latency_seconds`, `gpu_temperature_celsius` (or equivalent custom metrics).

---

#### TC-12-03 — Grafana dashboard shows GPU temp and LLM latency

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Type** | Manual / Infrastructure |

**Steps**  
1. Open Grafana and navigate to the AI Gateway dashboard.  
2. Generate load (5 concurrent chat requests).  
3. Observe the panels for GPU temperature, queue depth, and p95 LLM latency.

**Expected Result**  
- All three panels populate with real-time data.  
- p95 latency panel shows values < 5 s during normal load (Phase 1 SLA).

---

### Gap 13 — Manual Verification Pending

#### TC-13-01 — AI Agent UI works end-to-end

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Manual / E2E |

**Steps**  
1. Navigate to the **Agent** tab in the frontend.  
2. Create a new agent with a simple task (e.g., "Search the web for today's weather in Bangkok").  
3. Start the agent and observe the execution log.

**Expected Result**  
- Agent executes without error.  
- Execution log shows tool calls, intermediate results, and a final answer.  
- No unhandled exceptions appear in the browser console.

---

#### TC-13-02 — True Studio Image tab generates an image

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Manual / E2E |

**Steps**  
1. Navigate to **Studio → Image**.  
2. Enter a prompt: "A photorealistic Thai silk pattern".  
3. Click Generate and wait up to 60 seconds.

**Expected Result**  
- An image renders in the UI.  
- No error toast or blank image placeholder.

---

#### TC-13-03 — True Studio Video tab submits and displays a video job

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Manual / E2E |

**Steps**  
1. Navigate to **Studio → Video**.  
2. Enter a prompt and click Generate.  
3. Observe the job status (polling or SSE).  
4. Wait for the job to complete (up to 10 minutes for Veo).

**Expected Result**  
- Job status transitions: `PENDING → RUNNING → DONE`.  
- Video player appears and the video is playable.

---

#### TC-13-04 — Library tab loads and displays media assets

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Manual / E2E |

**Preconditions**  
- At least one image and one video have been generated (TC-13-02 and TC-13-03 passed).

**Steps**  
1. Navigate to **Library**.  
2. Observe the asset grid.

**Expected Result**  
- Previously generated image and video appear as thumbnail cards.  
- Clicking a card opens a preview/detail view without errors.

---

### Gap 14 — Open Questions Unresolved

#### TC-14-01 — Tier 4 actors are defined and enforced

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Type** | Manual / Policy |

**Steps**  
1. Locate the policy configuration (PLAN.md or DB `roles` table) and confirm Tier 4 actors are named.  
2. Attempt a Tier 4 action (e.g., reveal approval) as a non-Tier-4 user.

**Expected Result**  
- Tier 4 roles are documented (names, employee IDs).  
- Non-Tier-4 user receives `403 Forbidden` when attempting a Tier 4 action.

---

#### TC-14-02 — ADMIN cannot self-approve reveals

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Type** | Automated / Integration |

**Steps**  
1. As ADMIN, submit a reveal request for data where ADMIN is the requester.  
2. As the same ADMIN user, attempt to approve the request.

**Expected Result**  
- The self-approval is rejected with an appropriate error (`403` or validation error).  
- Audit log records the attempted self-approval.

**Note** If the policy decision is that ADMIN *can* self-approve, document this decision explicitly and skip this test — but the decision must be explicit.

---

#### TC-14-03 — Audit log retention limit is configured

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Type** | Configuration Check |

**Steps**  
1. Check the DB or scheduled job for an audit log purge/archive policy.  
2. Confirm retention period is documented and matches Legal's requirement.

**Expected Result**  
- Retention period is set (e.g., 7 years per Legal).  
- A purge/archive job exists that respects this limit.

---

#### TC-14-04 — Default model on "auto" is documented and correct

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Type** | Automated / Unit |

**Steps**  
1. Locate the `auto` model routing logic in `backend/app/llm/`.  
2. Call the model resolver with `model="auto"` and assert the resolved model name.  
3. Confirm the resolved model is documented in PLAN.md or a config file.

**Expected Result**  
- `auto` resolves to the documented default (e.g., `llamacpp-primary` for internal, or a specific Claude/Gemini model for external Tier 2).

---

## Blocked on Infrastructure / External

---

### Gap 15 — GPU Box Not Tested

#### TC-15-01 — llamacpp-primary VRAM usage is within budget

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Manual / Infrastructure |

**Preconditions**  
- GPU box (`llamacpp-primary`) is accessible.

**Steps**  
1. Start the `llamacpp-primary` service on the GPU box.  
2. Run `nvidia-smi` or equivalent and record VRAM usage at idle.  
3. Run 5 concurrent chat requests.  
4. Record peak VRAM usage.

**Expected Result**  
- Idle VRAM usage ≤ documented model size + 1 GB overhead.  
- Peak VRAM under concurrent load does not exceed the GPU's physical VRAM (OOM = fail).

---

#### TC-15-02 — p95 LLM response latency is < 5 seconds

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Load / Performance |

**Preconditions**  
- TC-15-01 passes (no OOM).

**Steps**  
1. Use `locust` or `k6` to run 10 concurrent users sending chat requests for 5 minutes.  
2. Collect latency percentiles.

**Expected Result**  
- p50 latency < 3 s.  
- p95 latency < 5 s.  
- p99 latency < 10 s.  
- Zero `500` errors during the run.

---

### Gap 16 — Phase 1 Acceptance Gate

#### TC-16-01 — 10 pilot employees soak test for 1 week

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Manual / UAT |

**Preconditions**  
- GPU box is healthy (TC-15-01, TC-15-02 pass).  
- Pilot users onboarded with credentials.

**Steps**  
1. Onboard 10 employees as pilot users.  
2. Each employee uses the system for normal daily tasks for 5 business days.  
3. Collect daily: error rate, p95 latency, user-reported issues.

**Expected Result**  
- Average daily error rate < 1%.  
- p95 latency remains < 5 s throughout the week.  
- No P0 bugs reported by pilot users.  
- All 10 users confirm the system is usable for their work.

---

#### TC-16-02 — Phase 1 sign-off checklist complete

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Manual / Go/No-Go |

**Steps**  
1. Review the Phase 1 acceptance checklist in PLAN.md against the outcomes of TC-15-01, TC-15-02, and TC-16-01.  
2. Obtain sign-off from the project sponsor.

**Expected Result**  
- All checklist items are checked.  
- Written sign-off from project sponsor is recorded.

---

### Gap 17 — Pen Test

#### TC-17-01 — Authentication bypass attempts fail

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Security / Pen Test |

**Preconditions**  
- Pen test is authorised in writing. Scope and rules of engagement are defined.

**Steps**  
1. Attempt to access `GET /api/users` without a JWT token.  
2. Attempt to access with an expired JWT.  
3. Attempt to forge a JWT with the `none` algorithm.

**Expected Result**  
- All three attempts return `401 Unauthorized`.  
- No data is leaked in the error response body.

---

#### TC-17-02 — Horizontal privilege escalation blocked

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Security / Pen Test |

**Steps**  
1. Log in as User A.  
2. Obtain User B's `user_id` from any public endpoint.  
3. Attempt `GET /api/users/{user_b_id}/messages` using User A's token.

**Expected Result**  
- Response is `403 Forbidden`.  
- User A cannot read User B's messages.

---

#### TC-17-03 — SQL injection does not affect DB queries

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Security / Pen Test |

**Steps**  
1. Submit a chat message with SQL injection payload: `'; DROP TABLE users; --`  
2. Submit the same via the search/filter API query parameter.

**Expected Result**  
- Neither request produces a DB error or modifies data.  
- Responses are either normal (input treated as literal text) or `400 Bad Request`.

---

#### TC-17-04 — XSS payloads in chat messages are not rendered

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Security / Pen Test |

**Steps**  
1. Submit a chat message: `<script>alert('xss')</script>`  
2. Open the chat in another browser tab/as another user.

**Expected Result**  
- No alert dialog fires.  
- The `<script>` tag is either escaped or stripped in the rendered output.

---

#### TC-17-05 — Pen test report shows no Critical or High findings unresolved

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Manual / Review |

**Steps**  
1. Receive the pen test report from the external/internal security team.  
2. Triage all findings by severity.  
3. Resolve all Critical and High findings.  
4. Re-test resolved findings.

**Expected Result**  
- Zero unresolved Critical or High findings at the time of go-live.  
- Medium and Low findings have documented acceptance/remediation timelines.

---

## Summary Table

| Gap | Test Case IDs | Count | Blocking? |
|-----|--------------|-------|-----------|
| 1 — Uncommitted changes | TC-01-01, TC-01-02 | 2 | Critical |
| 2 — SSE sources rendering | TC-02-01, TC-02-02, TC-02-03 | 3 | Critical |
| 3 — BGE-M3 not pulled | TC-03-01, TC-03-02, TC-03-03 | 3 | Critical |
| 4 — n8n LINE alert | TC-04-01 – TC-04-04 | 4 | Critical |
| 5 — PolicyEngine failures | TC-05-01 – TC-05-04 | 4 | Critical |
| 6 — Phase 2 acceptance gate | TC-06-01 – TC-06-04 | 4 | Critical |
| 7 — Video quota | TC-07-01 – TC-07-03 | 3 | Important |
| 8 — llamacpp SPOF | TC-08-01, TC-08-02 | 2 | Important |
| 9 — ENCRYPTION_KEY in env | TC-09-01, TC-09-02 | 2 | Important |
| 10 — No backups | TC-10-01, TC-10-02 | 2 | Important |
| 11 — No rate limiting | TC-11-01, TC-11-02 | 2 | Important |
| 12 — No observability | TC-12-01 – TC-12-03 | 3 | Important |
| 13 — Manual verify pending | TC-13-01 – TC-13-04 | 4 | Important |
| 14 — Open questions | TC-14-01 – TC-14-04 | 4 | Important |
| 15 — GPU box untested | TC-15-01, TC-15-02 | 2 | Infra-blocked |
| 16 — Phase 1 gate | TC-16-01, TC-16-02 | 2 | Infra-blocked |
| 17 — Pen test | TC-17-01 – TC-17-05 | 5 | Infra-blocked |
| **Total** | | **51** | |
