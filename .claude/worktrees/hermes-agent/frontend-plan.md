# Restyle frontends to the Claude-designed prototype

## Context

The user designed the full UX of the **Decomplica AI Gateway** as a self-contained
React/CDN prototype (`Brandbiz Openrouter.zip`: `theme.css`, `components.jsx`,
`shell.jsx`, `app.jsx`, `admin-console.jsx`, `rag-upload.jsx`). The two existing
Next.js apps (`frontend-chat`, `frontend-admin`) are functionally complete for
Phases 1–2 but visually "scaffold-grade" — ad-hoc inline styles, hardcoded dark
hex, no shared design system.

**Goal (confirmed with user):** port the prototype's visual language and flows into
the existing Next.js apps. **No new backend features.** For the admin app,
**adopt the prototype's shape** — a focused 2-tab "Admin console" (Token quotas +
External model access), with the existing rich pages (Users / Permissions / Audit /
Reveal / Dashboard) kept as secondary, restyled.

The Knowledge Base / RAG surface in the prototype is **out of scope** (Phase 3 not
started; user chose "restyle existing only").

### Hard constraints
- The prototype is React-via-CDN + Babel, **not** Next.js. We re-implement its
  components as TSX; we do **not** drop the `.jsx` files in.
- Per `CLAUDE.md`: don't touch backend policy/audit/crypto paths; this is
  frontend-only. No changes to `app/llm/*`, `PolicyEngine`, or audit.
- The two frontends are **separate apps with no shared package**. The design system
  (tokens + shared components) is **duplicated** into each app's `components/ui/`
  and `globals.css`. (A shared workspace package is possible later but not in scope.)

### Known gap to surface, not silently work around
The design's **Token-quota tab** edits per-role budgets and per-user overrides, but
the backend exposes **no quota-config endpoint** (only read-only `GET /admin/metrics*`
and the per-role budget is server-config, not CRUD). So the Quotas tab ships
**display-only** (roll-up cards + per-role usage from metrics, sliders disabled/read-only).
Making it editable is a backend task (new `/admin/quotas` GET/PUT) — explicitly
deferred. The **Model-access matrix tab is fully wireable** to existing
`GET/PUT /admin/permissions/role` + `/admin/permissions/department`.

---

## Phase A — Shared design system (both apps)

Port the prototype's foundation into each app identically.

1. **Tokens + globals** — replace each `app/globals.css` with the prototype's
   `theme.css`: light-default CSS custom properties, `[data-theme="dark"]` overrides,
   tier scale `--t1..--t4`, radii/shadows, scrollbar + keyframes
   (`fadeUp/fadeIn/blink/popIn/barStripe/spin`). Source: `theme.css` (verbatim tokens).
2. **Fonts** — IBM Plex Sans / IBM Plex Sans Thai / IBM Plex Mono via
   `next/font/google` in each `app/layout.tsx`, exposed as `--font-sans` / `--font-mono`.
3. **Theme handling** — light default + dark toggle persisted in `localStorage`
   (`dca_dark`), applied via `data-theme` on `<html>`. Small client `ThemeToggle`.
   Note: existing apps are hardcoded dark; switching to light-default is intended.
4. **`components/ui/` shared kit** (TSX ports, props-driven — no data fetching):
   - `Icon.tsx` — the stroke icon set from `components.jsx` (`Ic` map + `<Icon>`).
   - `TierBadge.tsx` — badge / subtle / sm variants, tier T1–T4 (replaces existing).
   - `ProviderMark.tsx` — text-mark provider glyph.
   - Tier/role/model constants module `lib/domain.ts` (port `TIERS`, `ROLES`,
     `MODEL_BY_CODE` shapes) so badges/pickers render without backend round-trips.

Representative files: `frontend-chat/app/globals.css`, `frontend-chat/app/layout.tsx`,
`frontend-chat/components/ui/*`, and the mirror set under `frontend-admin/`.

---

## Phase B — Chat app restyle (`frontend-chat`)

Re-skin to match `app.jsx` while preserving the existing SSE/data wiring in
`ChatPane.tsx` (the `start`/`notice`/`content`/`done`/`error` stream stays as-is).

- **Shell** (`app/chat/layout.tsx` + `ConversationList.tsx`): 278px sidebar with
  logo block, nav (Chat / Knowledge base / Admin console links), "New chat" button,
  conversation groups by recency with a lock glyph on sensitive threads, footer with
  `QuotaMeter` + user identity card.
- **`ChatPane.tsx`**: keep markdown renderer + stream logic; restyle to the prototype's
  `MessageRow` — **decision meta row before content** (provider mark + model name +
  "kept local" pill + `TierBadge`), downgrade explainer block, body, and the
  token/cost/"logged" footer (PLAN.md §7.4, Gotcha 10). `ThinkingDots` =
  "routing through the policy engine…".
- **Composer**: rounded card; live "classified as `<TierBadge>`" chip; restyled
  `ModelPicker` (rich dropdown w/ entitlement lock + blurbs, from `components.jsx`)
  and send button; retention/approval footnote line.
- **`QuotaMeter.tsx` / `ModelPicker.tsx` / `TierBadge.tsx`**: swap visuals to the
  prototype versions but **keep their existing fetch wiring** (`/api/quota`,
  `/api/models`). Merge: presentational shell from design, data from current code.
- **`ConsentGate` / `ConsentModal`**: restyle to the prototype's `ConsentGate`
  (4 points, bilingual), keep the existing `/api/consent` POST.
- **Welcome** empty-state with suggestion cards; **`login/page.tsx`** restyled.
- **Optional, flagged**: client-side live tier chip while typing requires a
  browser `detectTier` (port from `data.jsx`, incl. Thai-ID Mod-11). This duplicates
  backend logic and can drift — include only as a cosmetic preview; the authoritative
  classification remains server-side at send. If we skip it, show the tier chip only
  after the message is sent (from the stream's decision event).

---

## Phase C — Admin app restyle + reshape (`frontend-admin`)

Adopt the prototype's `shell.jsx` + `admin-console.jsx` shape.

- **AppShell** (restyle `components/Sidebar.tsx` + `app/layout.tsx`): design sidebar
  with logo, primary nav, a "Governance" group, and operator footer.
- **New primary page "Admin console"** with two tabs (port `admin-console.jsx`):
  - **External model access** (fully wired): model × role checkbox matrix + master
    "Allow external providers" switch + the Tier 3/4-always-local info note. Source
    data `GET /admin/permissions/role` & `/admin/models`; save via
    `PUT /admin/permissions/role` (and `/admin/permissions/department` for add-ons).
    This supersedes the current `app/permissions/page.tsx` / `PermissionsMatrix.tsx`
    (reuse its API calls, restyle to the matrix UI). Sticky "unsaved changes" save bar.
  - **Token quotas & cost caps** (display-only, gap flagged): roll-up cards +
    per-role usage rows fed from `GET /admin/metrics*`; budget sliders rendered
    read-only/disabled with an inline "editing requires a quota-config endpoint" note.
    Per-user overrides shown if derivable, else static placeholder with the same note.
    Fills the empty `app/quotas/page.tsx` + `app/models/page.tsx` stubs.
- **Secondary pages kept, restyled** to the new tokens/components: `(dashboard)`,
  `users`, `audit`, `reveal`. `MetricCards`, `ModelUsageBars`, `TopUsersTable`,
  `UsersTable`, `UserEditModal`, `AuditTable`, `RevealQueue`, `ConfirmDialog` get
  the new visual language; their data/API behavior is unchanged.
- Add the three previously-orphaned stubs to nav where they now have content
  (Quotas/Models folded into "Admin console"); leave `classification-rules` as a
  restyled stub (no backend) or drop from nav.

---

## Out of scope (do not build)
- Knowledge Base / RAG upload surface (`rag-upload.jsx`).
- Any backend endpoint, including the quota-config CRUD the Quotas tab would need.
- The prototype's dev-only `tweaks-panel.jsx` (role/dept/theme playground).
- Changes to PLAN.md decisions D1–D20 or Section 11.

## Verification
1. **Build/lint both apps**: `pnpm --dir frontend-chat build` and
   `pnpm --dir frontend-admin build` — must pass with the new fonts/components.
2. **Run locally** (per PROGRESS infra notes, chat may be on port 3002): start both,
   confirm light/dark toggle persists, IBM Plex loads, no inline-style regressions.
3. **Chat flow**: sign-in → consent gate → send a normal message (external model
   path) and a Thai-ID message (`1234567890121`) → verify decision meta row, "kept
   local" pill, downgrade explainer, token/cost footer, quota meter update.
   Confirm the invalid ID `1195644567342` stays T1.
4. **Admin flow**: open "Admin console" → Model-access tab → toggle a cell, Save →
   confirm `PUT /admin/permissions/role` fires and persists on reload. Quotas tab →
   confirm read-only cards render from metrics and the gap note is visible.
5. **Regression**: Users/Audit/Reveal pages still load and their actions
   (PATCH user, CSV export, approve/deny reveal) still work post-restyle.
6. No backend diffs in `git status` — frontend-only change set.
