# Client Workspace as a LINE MINI App (LIFF)

## Short answer

**Yes.** A LINE MINI App *is* a web app rendered in LINE's in-app browser (LIFF), so this
Next.js app qualifies structurally as-is. This is not a rewrite — it is one new identity
path, one new entry route, and mobile polish.

Three things make it unusually cheap here:

1. **The seam was designed in.** `backend/app/models/client_invite.py:12-16` calls itself
   "the LINE-integration seam", and `client_invites.line_user_id` /
   `workspaces.line_user_id` already exist (`String(64)`, nullable) — **written by nothing,
   read by nothing** today. PLAN.md:1099 (Task 5.2) records `/try/<token>` as a "LINE-ready
   seam; LINE integration itself is a follow-on."
2. **The UI is already responsive to phone widths.** `responsive.md` documents a verified
   pass at 390px; `app/globals.css:507+` collapses `.client-grid` to one column at ≤768px
   with the nav rail and work panel as off-canvas drawers.
3. **The BFF keeps everything same-origin.** The browser only ever calls `/api/*` on the
   Next server (`lib/clientBff.ts`), which re-attaches the `access_token` cookie server-side
   toward FastAPI. Inside LIFF the cookie is therefore **first-party**, sidestepping the
   usual in-app-webview third-party-cookie problem, and `CORS_ORIGINS` needs no change.

No new dependencies on the backend: `httpx` and `python-jose[cryptography]` are already in
`backend/pyproject.toml`.

## Context

The client workspace (`/w`, `/w/plans`, `/p/<token>`) is a client-facing funnel: an AI
persona (น้อง brandbiz) runs a deterministic intake, pulls live market research, matches the case
library, and drafts a costed plan handed to a human expert (PLAN.md Phase 5, D21–D23).

Distribution today is a hand-minted single-use `/try/<token>` link. Putting the funnel
inside LINE removes the link-passing step and — with LINE Login — makes a prospect's
engagement **resumable**, which the current model cannot do at all.

### The one real problem: identity

Everything else is plumbing.

| | Today | Needed |
|---|---|---|
| Seat creation | `redeem_invite` mints a `User` with `google_email = client-{uuid4}@{slug}.client.invalid` | find-or-create keyed on the LINE user id |
| Re-entry | **none** — invite is single-use (410 on second POST), JWT TTL 8h, no refresh | silent re-auth from `liff.getIDToken()` |
| Identity source | the token in the URL | LINE `sub`, verified server-side |

`users.google_email` is `NOT NULL UNIQUE` (`backend/app/models/user.py:24`), so a LINE seat
needs a stable unique value there either way.

## Decisions taken (confirmed with the user)

- **LINE Login as identity** — `liff.getIDToken()` → new `POST /public/line-login`.
- **Unverified MINI App first** — publishable in Thailand, no LY Corporation review.
- **Client workspace only** — `/w`, `/w/plans`, `/w/plans/[id]`, `/p/<token>`. Admin
  (`/clients`, `/leads`) and the internal staff app stay on normal web.

---

## Phase A — LINE Developers Console + public HTTPS (no code)

Do this first; nothing below can be tested without it.

1. Provider → **LINE MINI App channel** (not a plain LIFF app — LINE is folding LIFF into
   the MINI App brand, and new apps should be created as MINI Apps). Region: **Thailand**.
2. Two channels: **Dev** and **Prod**. Note the **Channel ID**, **Channel secret**, and
   **LIFF ID** for each.
3. Endpoint URL → `https://<public-host>/line` (the new entry route from Phase C).
   Size `Full`. Scopes: **`openid` + `profile`**.
   - **Do not plan on `email`.** That scope needs a separate application in the console
     (screenshot of your collection notice, ~1–2 business days) and is unnecessary —
     identity comes from `sub`.
4. Use the console's **basic authentication** to lock the app while unreleased.
5. **Local dev:** LIFF requires public HTTPS; `localhost:3100` will not work. Point the Dev
   channel's endpoint at an HTTPS tunnel to port 3100 (e.g. `cloudflared` / `ngrok`) and
   re-point it when the URL rotates. Everything except `liff.init()` can still be developed
   against localhost with the LIFF bootstrap disabled by env flag (Phase C item 6).

**Judgment call for you:** whether the Prod endpoint is a new host (e.g.
`https://w.brandbiz.ai`) or a path on the existing frontend host. A dedicated host is
cleaner because the unverified MINI App header displays the domain to the user.

---

## Phase B — Backend: LINE identity

### B1. Migration `0059_line_identity.py`

Copy the shape of `0058_engagement_started_action.py`.

- Add `users.line_user_id` — `String(64)`, nullable, **unique index**.
  - *Chosen over* overloading `google_email` with a deterministic
    `line-{sub}@...client.invalid` value. That alternative needs no migration, but it hides
    the identity inside a column named for a different provider and makes "find the seat for
    this LINE user" an unindexed string-prefix problem. One nullable column with a real
    unique index is the correct shape and the repo is disciplined about migrations
    (0058 already exists).
  - `google_email` still gets a synthetic value, reusing the existing
    `.client.invalid` convention: `line-{sub_sha256[:24]}@{workspace.slug}.client.invalid`.
    Deterministic, so a retry cannot mint a duplicate seat.
- `op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'line_login'")` and add
  `"line_login"` to the label list in `backend/app/models/audit.py:48-63`.
  `tests/integration/test_audit_enum_sync.py` enforces that these stay in sync.

### B2. New service `backend/app/services/line_identity.py`

One responsibility per file, per CLAUDE.md. Two functions:

- `async def verify_id_token(id_token: str) -> LineProfile`
  POST to `https://api.line.me/oauth2/v2.1/verify` with `id_token` + `client_id`
  (= `LINE_CHANNEL_ID`), using the `httpx.AsyncClient` + `httpx.Timeout` idiom already in
  `backend/app/services/n8n_client.py:24-68`. Validate `aud == channel_id`,
  `iss == https://access.line.me`, `exp` in the future. Raise `HTTPException(401)` on any
  failure. **Never trust a client-decoded token.**
  - Local HS256 verification with the channel secret via `python-jose` is a valid
    alternative (no network hop, no LINE rate limit). Start with the endpoint — it is the
    documented path and less to get wrong — and switch if latency shows up.
- `async def find_or_create_line_seat(session, *, profile, workspace) -> tuple[User, bool]`
  Mirror `workspace_svc.redeem_invite` (`backend/app/services/workspace.py:292-355`) for the
  create branch: `role="L1"`, `workspace_id`, `is_active=True`,
  `consent_acknowledged_at=now`, join via `_ensure_client_department`, audit. On the
  **found** branch: refresh `display_name` from the LINE profile and return early — no new
  engagement, so `uq_engagements_one_active_per_seat` is untouched and `GET /client/bootstrap`
  replays the existing engagement, transcript and plan.

### B3. Workspace selection

There is no invite carrying a `workspace_id`, so this needs an explicit rule. Add
`get_workspace_by_slug(session, slug)` to `workspace.py` (no such helper exists) and resolve
in this order:

1. `settings.line_workspace_slug` if set → that workspace;
2. else `get_preview_workspace()` (the seeded demo workspace).

Reject archived workspaces with 404, as `redeem_invite` does.

**Blast-radius note:** every LINE user lands in **one shared workspace**, exactly as booth
attendees do today. D23 accepted that for a controlled event; a LINE MINI App is a
materially wider door. The pooled `workspaces.token_budget_limit` is the cost cap and it is
per-workspace, so set it deliberately before publishing.

### B4. New endpoint in `backend/app/routers/client_public.py`

`POST /public/line-login {id_token}` — modelled directly on `redeem` (lines 41-61), which is
already the template for "unauthenticated call that mints a session cookie":

```
_line_login_limit = rate_limit("public_line_login", limit=20, window_seconds=60)
```

Body → `verify_id_token` → resolve workspace → `find_or_create_line_seat` →
`_create_jwt(seat)` + `_set_jwt_cookie(response, token)` → return `_user_response(seat)` plus
the workspace block, same shape as `redeem`. The router already sits behind
`Depends(require_client_surface)` at `include_router` level, so the `CLIENT_SURFACE_ENABLED`
kill switch covers it for free. Add a second flag `LINE_MINIAPP_ENABLED` (default off) so
the LINE door can be closed independently.

Audit `line_login` with `{"new_seat": bool}`.

### B5. Config

`backend/app/config.py` (append near the client-workspace block, ~line 95) and
`.env.example`: `line_channel_id: str = ""`, `line_channel_secret: str = ""`,
`line_liff_id: str = ""`, `line_miniapp_enabled: bool = False`,
`line_workspace_slug: str = ""`. Blank channel ID must hard-disable the endpoint (same
pattern as `n8n_webhook_url`).

### B6. Session lifetime — do **not** build refresh tokens

JWT TTL stays 8h. The LIFF client re-authenticates silently: on `liff.init()`, call
`/api/me` (which already 401s when the cookie is missing, `app/api/me/route.ts:7`); on 401,
re-run `POST /api/public/line-login` with a fresh `liff.getIDToken()`. Inside LINE the user
is already logged in, so this is invisible. Far less machinery than a refresh-token scheme,
and it removes the "8h and you're locked out" failure entirely.

**Expiry mid-session is a dead end today and must be fixed.** When the token expires while
the app is open, `app/(client)/layout.tsx` redirects to `/api/session-expired`, which clears
the cookie and sends the user to `/login`. Inside a LIFF webview `/login` is unreachable by
design — there is no self-serve entry, and `POST /auth/login` 403s anyway whenever
`GOOGLE_OAUTH_CLIENT_ID` is set (which it is). The user is simply stuck.

Fix: have `app/api/session-expired/route.ts` redirect to `/line` instead of `/login` when
the request came from a LINE session. Cheapest reliable marker is a non-httpOnly
`line_session=1` cookie set alongside the JWT in C1; `/line` then re-runs the silent
handshake and the user never sees an interruption.

### B7. Consent

LIFF development guidelines require user consent before linking LINE identity to a session.
`redeem_invite` pre-sets `consent_acknowledged_at` on the reasoning that the invite link
*is* the notice. That reasoning does not carry over — nobody hand-delivered the LINE entry.

**Recommendation:** keep `consent_acknowledged_at` auto-set (so `require_consent` still
composes), but render a short consent screen in the LIFF entry route *before* the first
`line-login` call, with a link to the privacy policy. LINE's own channel-consent screen
covers the LINE-side data grant; this covers linking it to a Brandbiz workspace.

---

## Phase C — Frontend: LIFF integration

### C1. New entry route `frontend-chat/app/line/page.tsx`

This is the hard part, because `liff.init()` is client-only while the auth gate is in
`middleware.ts` + a **server** layout (`app/(client)/layout.tsx`, which server-fetches
`/auth/me` and redirects to `/login`).

Deliberately put the entry **outside** the `(client)` route group so it never hits that
server-side guard. A server component reads `process.env.LINE_LIFF_ID` and passes it as a
prop to a `'use client'` `LiffBootstrap` component that:

1. `liff.init({ liffId })`
2. consent gate (B7) on first visit
3. `POST /api/public/line-login` with `liff.getIDToken()`
4. `router.replace(target)` — where `target` comes from `liff.state` (default `/w`)

Order matters: the cookie is set in step 3, *before* any navigation into `/w`, so the
server layout's guard passes on first render and there is no bounce to `/login`.

### C2. `@line/liff` npm package, not the CDN script

The CDN tag is simpler but the npm package type-checks and survives the
`output: 'standalone'` build. Import it dynamically inside the client component so it never
lands in the server bundle.

### C3. `frontend-chat/app/api/public/line-login/route.ts`

Copy `app/api/public/redeem/route.ts` verbatim in shape — forward the JSON body, forward
the backend's `Set-Cookie`. 23 lines.

### C4. `middleware.ts` + session-expiry recovery

Add `/line` to the existing pass-through beside `/try/` and `/p/` (`middleware.ts:12`) —
one line. Then apply the `/api/session-expired` change from B6 so an expired LINE session
recovers instead of dead-ending at `/login`.

### C5. Deep links via `liff.state`

Appending a path to the LIFF URL (`https://miniapp.line.me/{liffId}/w/plans/abc`) arrives
as a `liff.state` query param on the endpoint URL. Read it in `LiffBootstrap`, validate it
against an allow-list of client-workspace paths (`/w`, `/w/plans`, `/w/plans/<id>`) —
**do not** blindly `router.replace` attacker-controlled input — then navigate.

Next's App Router uses the History API, which is what LIFF requires; LIFF explicitly has
"limited compatibility with routing using fragments", so avoid hash routing. Nothing in the
current app uses it.

### C6. `liff.isInClient()` + env gating

Since Oct 2025 MINI Apps are also reachable from an external browser. If `!isInClient()`,
still run the login (LINE Login works in a normal browser too) but skip any
LINE-client-only API. Gate the whole bootstrap on `LINE_LIFF_ID` being set, so the normal
web app and existing `/try/<token>` flow are completely unaffected when it is blank.

### C7. Do not use `NEXT_PUBLIC_LIFF_ID`

`NEXT_PUBLIC_*` is inlined at **build** time, so setting it in `docker-compose.yml`'s
`environment:` block would silently not reach the browser bundle — it would need a build
arg. Pass the LIFF ID from the server component as a prop instead (C1). This matches how
`BACKEND_URL` is already kept server-only.

---

## Phase D — Mobile / LIFF UI polish

All of this belongs in named classes in `frontend-chat/app/globals.css`, per the repo's
documented convention at `globals.css:349-354` (inline styles beat class media queries, so
anything that flips at a breakpoint lives in CSS).

1. **iOS auto-zoom on the composer** — the chat input is `fontSize: 13`
   (`ClientWorkspace.tsx:1153`) and `html { font-size: 14px }` (`globals.css:121`). iOS Safari
   /WKWebView zooms the viewport whenever a focused input is under 16px. Bump the composer
   input to ≥16px on coarse pointers. **Most user-visible fix in this list.**
2. **Safe areas** — add `viewport-fit: 'cover'` to the `viewport` export in
   `app/layout.tsx`, then `padding-bottom: calc(14px + env(safe-area-inset-bottom))` on
   `.client-composer-wrap` in the ≤768px block (`globals.css:521`). Without this the
   composer sits under the home indicator and LINE's bottom chrome.
3. **`100dvh` fallback** — `ClientWorkspace.tsx:719` and `globals.css:280` use `100dvh`.
   Add a `100svh` (or `100vh`) declaration immediately before it for older LINE webviews.
4. **Drawers on a phone-only surface** — the ≤768px layout already makes the nav rail and
   work panel full-screen drawers, which is the right pattern. Verify the toggle buttons
   (`ClientWorkspace.tsx:810`, `:833`) clear LINE's own header, and that touch targets are
   ≥44px.

---

## Phase E — Cookies, streaming, deployment

- **Cookies:** set `COOKIE_SECURE=true` (→ `samesite="none"`, `backend/app/routers/auth.py:64`)
  and serve over HTTPS. Because of the BFF the cookie is **first-party** to the LIFF endpoint
  origin, so this should just work. `deps.py::_extract_token` already accepts
  `Authorization: Bearer` first — that is the fallback if a LINE webview turns out to drop
  the cookie, but it would mean changing the Next proxy routes to forward a header instead,
  so treat it as contingency, not plan-of-record.
- **SSE:** `/client/chat` is POST + `ReadableStream` (`lib/sse.ts`), not `EventSource`, so it
  works in a webview. `X-Accel-Buffering: no` is already set. Risk is intermediate proxy
  buffering — verify on a real device. Fallback already exists in shape:
  `POST /automations/agent` is the non-streaming variant.
- **CORS:** no change needed — the browser never talks to FastAPI directly.
- **compose:** add `LINE_*` vars to the `backend-api` environment block and `LINE_LIFF_ID` to
  `frontend-chat` (`docker-compose.yml:163-178`).

---

## Verification

1. **Unit** (`backend/tests/unit/test_line_identity.py`, new): `verify_id_token` accepts a
   good payload and rejects wrong `aud` / wrong `iss` / expired / LINE returning 400 —
   patch the outbound call with `AsyncMock`, the way `test_alert.py:91-110` does for n8n.
   `find_or_create_line_seat` creates once and
   **returns the same seat on the second call** — the resumability guarantee.
2. **Integration** (extend `tests/integration/test_engagement_funnel.py`): `line-login` →
   cookie set → `GET /client/bootstrap` 200; call `line-login` again → same `user.id`, same
   `engagement_id`, transcript replayed. Extend `test_client_isolation.py` to confirm a LINE
   seat cannot read another workspace.
3. **Enum sync**: `tests/integration/test_audit_enum_sync.py` must still pass after the
   `line_login` addition.
4. **Real device** — the only way to actually confirm this. `docker compose build frontend-chat`
   (per project memory, `frontend-chat` has **no hot reload**; a rebuild is required), point
   the Dev channel endpoint at the HTTPS tunnel, open the LIFF URL on a phone with LINE
   installed, and check: entry lands on `/w` without a `/login` bounce; chat streams
   token-by-token; composer does not zoom on focus and is not hidden by the home indicator;
   close LINE, reopen the app, land back in the same engagement.
5. **Expiry recovery** — temporarily drop `TOKEN_TTL_HOURS` (or delete the cookie from
   devtools) and confirm the app silently re-authenticates instead of landing on `/login`.

## PLAN.md bookkeeping

- **New decision D24** — LINE Login as a client-seat identity provider. Required because
  §11 lists "❌ Federated identity beyond Google Workspace" (PLAN.md:1414); note that this
  is scoped to *client seats only* and does not touch internal staff auth. Amend that §11
  line to point at D24, the way the multi-tenancy entry was amended for D21/D22.
- **New task 5.13** — "LINE MINI App (LIFF) delivery of the client workspace", closing the
  follow-on that Task 5.2 (PLAN.md:1099) left open.
- Per CLAUDE.md, run `/progress` after ticking the checkbox.

## Separate: what *verified* status would additionally require

Not needed for launch; listed so the unverified path does not paint you into a corner.

- **Certified provider is a hard gate.** In Thailand only channels under an
  already-certified provider may even apply — certification goes through **LINE for
  Business Thailand**, not the developer console. (In Japan it is granted automatically on
  first approved review; Thailand and Taiwan are not.) This is a commercial relationship,
  so start it early if you want it.
- Review takes ~1–2 weeks; rejections add rounds. Auto-publishes 31 days after approval if
  you do not release manually.
- Needs: privacy policy whose named entity matches the provider, an accurate service
  description ("AI marketing-plan consultation", not "Brandbiz"), **separate Published and
  Review channels serving the identical app**, basic-auth credentials if access is
  restricted, test scenarios for any transactional flow (the lead-submission CTA), and
  compliance with LINE's icon / loading / landscape-safe-area design and performance
  guidelines.
- What you gain: verified badge, add-to-home-screen, custom path, simplified channel
  consent, **Home tab and LINE Search discovery** (the real reason to bother), and service
  messages.

## Risks / open judgment calls

1. **Shared-workspace exposure** (B3) — one workspace for every LINE user, pooled token
   budget. Fine for a funnel, wrong if you later want per-client isolation. Decide the cap
   before publishing.
2. **`CLIENT_INTERNAL_ACCESS_ENABLED` must stay off.** D23 accepted exposing the internal
   knowledge base and staff emails to booth attendees. A public LINE door is a different
   threat model, and the flag is per-instance, not per-entry-path.
3. **Rate limits are in-process and per-IP** (`services/rate_limit.py`, no Redis). Mobile
   LINE traffic egresses over many IPs so the limits will be loose, and they reset on
   restart and do not survive multiple replicas.
4. **PLAN.md Task 5.7 hardening is still open** — prompt-injection pass against a live
   instance and secrets rotation (`JWT_SECRET`, `POSTGRES_PASSWORD`, the GitHub PAT in
   `VAULT_GIT_URL`). Those were acceptable-open for a supervised booth. They should close
   before a public LINE entry point, and `.env` is currently committed with a real
   `N8N_WEBHOOK_URL`.
5. **`POST /auth/login` returns 403 whenever `GOOGLE_OAUTH_CLIENT_ID` is set**, and the real
   `.env` sets one — so invite redemption is currently the *only* working login. Worth
   knowing before you rely on `/login` as a fallback during testing.

## Sources

- [Introducing LINE MINI App](https://developers.line.biz/en/docs/line-mini-app/discover/introduction/)
- [LINE MINI App specifications](https://developers.line.biz/en/docs/line-mini-app/discover/specifications/)
- [Implementing web apps in operation as LINE MINI Apps](https://developers.line.biz/en/docs/line-mini-app/develop/web-to-mini-app/)
- [Submitting LINE MINI App](https://developers.line.biz/en/docs/line-mini-app/submit/submission-guide/)
- [Opening a LIFF app](https://developers.line.biz/en/docs/liff/opening-liff-app/)
- [LIFF app development guidelines](https://developers.line.biz/en/docs/liff/development-guidelines/)
- [Verify a LINE ID token](https://developers.line.biz/en/docs/line-login/verify-id-token/)
- [MINI Apps usable from a web browser (Oct 2025)](https://developers.line.biz/en/news/2024/02/14/mini-app-browser/)
