# Test Phase 1 via the Webapp (local, no GPU)

## Context

Phase 1's goal: a logged-in user chats with the local LLM, messages persist encrypted, reload shows history (PLAN.md §253, acceptance loop §333). We want to exercise that loop through the browser on this WSL dev box. Two environment facts block the stock path, and the plan works around each:

1. **No local LLM.** `llamacpp-primary` can't start (WSL, no GPU) and `models/` has only `.gitkeep`. The orchestrator persists messages *after* the LLM call (`orchestrator.py:111` runs before the commit at `:149`), so if the LLM is unreachable the user sees a streamed `error` event **and nothing is saved** — both halves of the acceptance loop fail. → Use the existing **Ollama server** (`192.168.20.18:11435`, OpenAI-compatible) as the LLM.
2. **No auth.** Google OAuth client ID/secret are blank, there's no dev-login route, and no seed user. We don't need *Google* specifically — we need a JWT signed with `JWT_SECRET` plus a matching `users` row (`deps.py:45-51`). Google is just the only token issuer built in Phase 1. → **Mint a JWT directly** and seed one user.

## Prerequisites (verify first — currently failing)

- **Ollama reachability.** Right now `192.168.20.18` is unreachable from this machine (ping 100% loss; TCP timeout on `:11435` and `:11434`). Get on the correct network/VPN, then confirm: `curl http://192.168.20.18:11435/api/tags` returns a model list. Note the exact model name (e.g. `qwen2.5:14b`) — call it `<OLLAMA_MODEL>`.
- **Containers from prior session:** postgres + redis are healthy; frontend images are built; Caddy issues `*.company.local` certs. backend-api needs restarting after env changes.

## Approach

### Part A — Point the LLM client at Ollama

The client sends a **hardcoded** upstream model name `"qwen2.5-14b-local"` (`router.py:13`), and Ollama matches models by exact name, so it would 404. Make the upstream model name env-configurable (minimal change; the request shape in `llamacpp.py:19-24` is already OpenAI-compatible and works with Ollama as-is).

Edits:
- `backend/app/config.py` (~line 34): add `llm_primary_model: str = "qwen2.5-14b-local"`.
- `backend/app/llm/router.py`: add a `primary_model` param to `LLMRouter.__init__` (default `LOCAL_MODEL_CODE`), pass it as `LlamaCppClient(base_url=primary_url, model=primary_model)`; in `get_router()` pass `primary_model=get_settings().llm_primary_model`. Keep the dict key as `LOCAL_MODEL_CODE` (the app's internal code) — only the *upstream* name becomes configurable.
- `docker-compose.yml` (common-env, ~line 47): change `LLM_PRIMARY_URL` to `${LLM_PRIMARY_URL:-http://llamacpp-primary:8080}` and add `LLM_PRIMARY_MODEL: ${LLM_PRIMARY_MODEL:-qwen2.5-14b-local}`.
- `.env`: add `LLM_PRIMARY_URL=http://192.168.20.18:11435` and `LLM_PRIMARY_MODEL=<OLLAMA_MODEL>`.

*Zero-code alternative:* instead of the config change, run `ollama cp <OLLAMA_MODEL> qwen2.5-14b-local` on the Ollama host so the hardcoded name resolves. The env approach is preferred (no mutation of the shared Ollama server).

### Part B — Auth bypass (seed user + mint JWT)

Create `backend/scripts/seed_and_token.py` (run via `docker compose exec backend-api python scripts/seed_and_token.py`). It:
1. Opens an async session, upserts a `users` row — `google_email="dev@company.local"`, `role="L1"`, `is_active=True` (other columns default; `id` auto-uuid). Schema: `models/user.py:18-38`.
2. Mints an HS256 JWT with the exact payload shape from `auth.py:48-57` — `{sub: str(user.id), email, role, iat, exp(+8h)}`, signed with `settings.jwt_secret`.
3. Prints the user id and the token.

No `COOKIE_SECURE` change needed: we set the cookie manually in the browser over HTTPS (Caddy), so the backend's cookie flags don't apply.

### Part C — Bring up the minimal stack

The Phase 1 chat loop needs only: postgres, redis, backend-api, frontend-chat, caddy (+ external Ollama). Skip llamacpp-*, garage, and the Celery workers (RAG/audit — not on the basic chat path). backend-api `depends_on` llamacpp-primary as `service_healthy` in base compose, so start services explicitly with `--no-deps`:

```
docker compose up -d --no-deps postgres redis backend-api frontend-chat caddy
docker compose run --rm backend-api alembic upgrade head   # if not already migrated
```

## Test steps (webapp E2E)

0. Trust Caddy's CA (admin PowerShell), so the browser accepts the cert:
   `docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt .\caddy-root.crt`
   `Import-Certificate -FilePath .\caddy-root.crt -CertStoreLocation Cert:\LocalMachine\Root`
1. Add hosts entries (admin PowerShell):
   `Add-Content C:\Windows\System32\drivers\etc\hosts "127.0.0.1  chat.company.local admin.company.local api.company.local"`
2. Sanity: `curl.exe https://api.company.local/health` → `{"status":"ok","db":"ok","redis":"ok"}`.
3. Run the seed/token script (Part B); copy the printed JWT.
4. Browser → `https://chat.company.local`. DevTools → Application → Cookies → add `access_token=<JWT>`, Domain `.company.local`, Path `/`. Reload → the chat shell should show the logged-in user (layout fetches `/auth/me` + `/conversations`, `chat/layout.tsx:36-39`).
5. Type a message, Send → confirm a streamed response appears token-by-token (Ollama via SSE).
6. Hard-reload (Ctrl+Shift+R) → conversation + both messages still present (persistence proven).

## Verification

- **Encryption at rest** (acceptance gate §344): `docker compose exec postgres psql -U brandbiz brandbiz -c 'SELECT id, role, length(content_ciphertext) FROM messages ORDER BY created_at DESC LIMIT 2;'` → 2 rows (user + assistant), `content_ciphertext` is non-null binary, not readable text.
- **Backend-only fallback** (if the browser/cookie path misbehaves): `curl.exe -N https://api.company.local/chat -H "Authorization: Bearer <JWT>" -H "Content-Type: application/json" -d '{"conversation_id":null,"content":"hello"}'` → SSE `start` → `content` → `done`. `_extract_token` accepts the Bearer header (`deps.py:14-18`), isolating frontend issues from backend.

## Out of scope / risks

- Real Google OAuth, the GPU llama.cpp model, garage (`rpc_bind_addr` crash), and the embed/RAG workers are **not** part of this test — they belong to their own Phase 1/2/3 tasks.
- The full acceptance gate (10 users for a week, p95 < 5s, GPU) can't be met on this dev box; this plan proves the **code path** end-to-end, not the production SLA.
- If Ollama stays unreachable, the chat loop cannot pass — reachability is a hard gate (step 0 of prerequisites).
