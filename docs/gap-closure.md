# Gap Closure — AskMe feature parity

Task list for closing the 35 unbuilt features identified in [`report.md`](../report.md)
(AskMe AI Gateway vs. CH-AI Gateway feature audit, 4 Aug 2026 — 29 present / 1 partial / 35 gaps
out of 65).

| | |
|---|---|
| **Source audit** | [`report.md`](../report.md) |
| **Merged target spec** | [`report_merge.md`](../report_merge.md) |
| **Branch** | `dsme` |
| **Coverage** | 35 audit gaps + the 1 partial row (G-C2) |
| **Numbering** | `G-<area><n>` — stable references, independent of PLAN.md task numbers |
| **Convention** | `☐` / `☑` checkboxes as in PLAN.md §6, so the `/progress` workflow works unchanged |

This document does **not** supersede `PLAN.md`. PLAN.md remains the source of truth for
architecture, decisions (§2), critical patterns (§7) and out-of-scope rules (§11). Every task below
must still be cross-checked against §7 and §8 before implementation.

---

## Blocked on decision — do not start

Four tasks (6 audit rows) collide with decisions already made in PLAN.md. Each needs the user to
explicitly amend or reverse a decision before any work begins.

| Task | Collides with | Needed |
|---|---|---|
| **G-H4** SAML | §11 "Federated identity beyond Google Workspace"; D11 fixes auth at Google OAuth + JWT | Amend D11 + §11 |
| **G-J1** Logo / brand name / primary color | §11 "tenant-configurable branding" | Amend §11 |
| **G-J2** Custom domain | §11 per-tenant deployments | Amend §11 |
| **G-F8** Commercial packaging tiers (3 rows) | §11 per-tenant deployments + tenant self-service admin | New decision (D24) |

**G-F6 / G-F7** (billing management and setup) are *not* blocked but need a scope call: billing for
one internal organisation is inside today's boundary; *tenant-configurable* billing is named in §11.
Confirm which one is meant before starting.

---

## A. Chat pipeline & model layer — 5 items

Files: `backend/app/routers/chat.py`, `backend/app/services/chat_policy.py`,
`backend/app/agents/orchestrator.py`, `backend/app/llm/*`,
`frontend-chat/components/ChatPane.tsx`, `frontend-chat/components/ModelPicker.tsx`

- ☑ **G-A1 Response modes — Instant / Thinking / Pro**
  Add `mode` to `ChatRequest` (`routers/chat.py:18`), thread through `prepare_chat` →
  `run_chat_stream`. The seam already exists — both calls already carry `temperature` and
  `system_prompt`. Provider mapping lives **only** inside `app/llm/<provider>.py` (§7.2: never
  branch on provider outside that directory). UI: a mode selector next to `ModelPicker`.

- ☑ **G-A2 Reasoning level — Low / Medium / High / Max**
  Same seam as G-A1, separate knob. Maps to Anthropic thinking budget, OpenAI reasoning effort,
  local `max_tokens`. Distinct from the existing per-Agent `creativity_level`, which stays as-is.
  *Implement together with G-A1 as one commit — it is the same plumbing change twice.*

- ☐ **G-A3 Arena Mode — two models side by side**
  Backend primitives are complete; the work is a second concurrent SSE channel from one prompt plus
  per-branch accounting. Watch: §7.5 decrements quota *after* the response — arena decrements twice,
  and both branches must be audited and classified separately. `report.md` §7 says a plan already
  exists; it does not — the phrase appears only inside the report itself. Treat as unplanned.

- ☐ **G-A4 Prompt Assistant**
  Pre-send prompt rewriter. Reuse the `app/services/skill_selector.py` pattern (a small local-model
  call behind a service function) rather than introducing a new provider path.

- ☐ **G-A5 Model catalog breadth — Grok / Llama / DeepSeek …**
  One new `app/llm/<provider>.py` per vendor + `model_catalog` rows via a seed migration (next free
  number `0044_*`). `model_provider` is a Postgres ENUM (`app/models/model_catalog.py`) — adding a
  vendor requires an `ALTER TYPE`, not just an insert. The role/department permission surface at
  `routers/admin.py:335-483` is fully data-driven off `role_model_permissions` /
  `department_model_permissions` — a new vendor needs seed rows (a grant migration), not a code
  change there. Ongoing, vendor by vendor.

## B. Conversation organization — 1 item

- ☐ **G-B1 Projects / Group Chat**
  `app/models/conversation.py` has no grouping container. Add a `projects` table +
  `conversations.project_id` FK, a CRUD router, and sidebar grouping in
  `frontend-chat/components/ConversationList.tsx` / `ConversationsProvider.tsx`. Must apply
  `workspace_visibility_filter` (D22/D23) so client seats never see internal projects.

## C. Documents & export — 1 item + the 1 partial

- ☐ **G-C1 Generate Word / CSV / slides**
  New `app/services/docgen.py` + a generator in `app/tools/`. Store output through the existing
  file/Library path so the 30-day content retention (D14) does not delete deliverables. Mirror the
  structure of `app/services/studio.py`, which already handles image/video/music artifacts.

- ☐ **G-C2 General PDF export** *(the one "partial" row in the audit)*
  Print-to-PDF today covers only client plans (PLAN.md Task 5.6). Generalize to chat output and
  Library items.

## D. Org hierarchy — 1 item · foundation for G-E1 and G-F2

- ☐ **G-D1 Branches / groups**
  `app/models/department.py` is flat and single-level. Add a hierarchical org unit (parent FK) plus
  membership, admin CRUD alongside `/admin/departments` (`routers/admin.py:539`), and UI next to
  `frontend-chat/components/admin/UsersTable.tsx`.
  **Do this before G-E1 and G-F2** — both need the dimension to exist.

## E. Metrics & monitoring — 7 items

Files: `routers/admin.py:616–718` (`/metrics`, `/metrics/model-usage`, `/metrics/top-users`,
`/metrics/verify`), `frontend-chat/components/admin/MetricCards.tsx`, `ModelUsageBars.tsx`,
`TopUsersTable.tsx`

- ☐ **G-E1 Break down by branch / department / group** — dimension filter on every `/admin/metrics*`
  endpoint. **Depends on G-D1.** This also forces a decision on PLAN.md §12 open question 5
  (cost allocation — whether `department_id` lands on `messages`); raise it with the user first.
- ☐ **G-E2 Health monitoring** — `messages.latency_ms` is already recorded per message. Needs a
  per-provider aggregate endpoint, an uptime probe, and a dashboard panel.
- ☐ **G-E3 Risk monitoring** — `pii_detected` / `tier_blocked` already exist. Aggregate + panel only.
- ☐ **G-E4 Activity monitoring** — behavioral layer over `audit_log` (~70 action labels).
  Read-only aggregation: never mutate or delete audit rows (§7.3).
- ☐ **G-E5 Productivity monitoring** — job-type breakdown. Reuse `classify_intent` from the
  orchestrator instead of adding a second classifier.
- ☐ **G-E6 Storage usage report** — per-user / per-department file-size aggregate over
  `app/models/file.py` + Garage objects.
- ☐ **G-E7 Billing-cycle filter** — **depends on G-F6**; no billing-period concept exists today.

## F. FinOps, credits, billing, packaging — 10 items

Files: `app/models/quota.py`, `app/services/quota.py` (`resolve_monthly_token_limit`),
`app/routers/quota.py`, `routers/admin.py:850–985` (quota defaults),
`frontend-chat/components/QuotaMeter.tsx`

- ☐ **G-F1 Central credit unit (AICD equivalent)** — a credit abstraction + ledger over today's raw
  token quota. Keep `resolve_monthly_token_limit` as the single precedence point: three divergent
  copies of that logic were deliberately unified in PLAN.md Task 5.8 — do not fork it again.
- ☐ **G-F2 Org / branch / department / group quotas** — quota exists per user (D18) and per
  workspace (pooled). **Depends on G-D1.**
- ☐ **G-F3 Quota / credit transfer** — admin-mediated transfer between users, recorded as
  append-only ledger entries.
- ☐ **G-F4 Usage calculator** — pre-purchase estimator reading `model_catalog` cost columns.
- ☐ **G-F5 Add-on credit top-up** — depends on G-F1.
- ☐ **G-F6 Billing management — invoices / statements** — new subsystem: billing periods, line
  items, statement generation. ⚠️ Scope call required (see *Blocked on decision* above).
- ☐ **G-F7 Billing setup — templates / recipients / language** — depends on G-F6, same scope call.
- ☐ **G-F8 Commercial packaging — Shared Platform (17M / 45M / 95M), Dedicated Standard, Dedicated
  Premium** *(3 audit rows)* — **BLOCKED-ON-DECISION**, needs a new D24.

## G. Admin tooling — 3 items

- ☐ **G-G1 Model Inventory UI**
  `model_catalog.is_active` exists, but `/admin/models` (`routers/admin.py:523`) and
  `/models/available` are read-only. Add write endpoints + an admin screen. Smallest real win on
  this list.

- ☐ **G-G2 Classification Rules UI**
  In better shape than the audit implies. The rule store already exists
  (`data_classification_rules`, `app/models/classification.py`) and `classifier.load_rules()` /
  `reload()` already swap the in-process cache atomically. Missing: admin CRUD endpoints, a reload
  hook fired after every write, and the page body —
  `frontend-chat/app/(admin)/classification-rules/page.tsx` is a literal "not yet implemented" stub.
  ⚠️ `_VALIDATORS` in `app/services/classifier.py` is keyed by rule **name**, so renaming a rule
  through the UI silently drops its checksum validator (e.g. Thai national-ID Mod-11). Guard that.

- ☐ **G-G3 Import users (bulk provisioning)**
  CSV / Workspace-directory import feeding the existing `/admin/users` path. Must set role,
  department, and — after G-D1 — org unit.

## H. Security & governance — 4 items

- ☐ **G-H1 REDACT / BLOCK sensitive content**
  Today `PolicyEngine.decide()` classifies and *routes* (D16: Tier 3/4 silently downgrade to local);
  there is no masking of message content. Add a redact/block stage on the payload before dispatch.
  **Highest-risk task on this list** — it sits directly on the §7.2 single-path-to-an-LLM invariant
  and the §7.4 early-abort streaming contract. Write a design note + tests before any code.
- ☐ **G-H2 Advanced DLP** — egress rule set + file-content scanning, built on G-H1.
- ☐ **G-H3 MFA** — TOTP for the username/password path (`users.password_hash` exists,
  `app/services/password.py`). Google SSO seats inherit Workspace MFA — document that split rather
  than duplicating enrolment.
- ☐ **G-H4 SAML** — **BLOCKED-ON-DECISION** (§11 federated identity, D11).

## I. Localization — 1 item

- ☐ **G-I1 Thai / English switch**
  `frontend-chat/app/layout.tsx:39` hard-codes `lang="th"`; no i18n library is installed. Add the
  layer (next-intl or equivalent), extract strings, persist the preference on the user record.
  Large mechanical surface — touches every page under `frontend-chat/app/`.

## J. Branding & tenancy — 2 items, both blocked

- ☐ **G-J1 Logo / brand name / primary color** — **BLOCKED-ON-DECISION** (§11).
- ☐ **G-J2 Custom domain** — **BLOCKED-ON-DECISION** (§11).

---

## Suggested build order

Grouping above is by subsystem so related migrations and files are touched together. Within that,
this order front-loads the cheap wins and respects the dependencies:

1. **G-G1**, **G-G2** — smallest; backend already exists, unblocks admin self-service
2. **G-A1 + G-A2**, **G-A3**, **G-A4** — one chat seam, three visible features
3. **G-C1**, **G-C2** — deliverables currently expire at the 30-day retention boundary (D14)
4. **G-D1** → then **G-E1**, **G-F2** (both depend on it)
5. **G-B1**, **G-G3**, **G-F3**, **G-I1**
6. **G-E2 … G-E6** — raw data already exists; aggregate + UI only
7. **G-H1** (design note first) → **G-H2**, **G-H3**
8. **G-F1**, **G-F4**, **G-F5** → **G-F6**, **G-F7** → **G-E7**
9. **G-A5** — vendor by vendor, ongoing
10. **G-F8**, **G-H4**, **G-J1**, **G-J2** — decision first, then plan

## Coverage check

| Section | Tasks | Audit rows |
|---|---|---|
| A. Chat pipeline & model layer | G-A1 … G-A5 | 5 |
| B. Conversation organization | G-B1 | 1 |
| C. Documents & export | G-C1 | 1 (+ G-C2 = the 1 partial) |
| D. Org hierarchy | G-D1 | 1 |
| E. Metrics & monitoring | G-E1 … G-E7 | 7 |
| F. FinOps, credits, billing, packaging | G-F1 … G-F8 | 10 (G-F8 covers 3) |
| G. Admin tooling | G-G1 … G-G3 | 3 |
| H. Security & governance | G-H1 … G-H4 | 4 |
| I. Localization | G-I1 | 1 |
| J. Branding & tenancy | G-J1, G-J2 | 2 |
| **Total** | **33 tasks** | **35** |

Maps 1:1 to the "ยังไม่ทำ" rows in `report.md` §2 (8), §3.1 (7), §3.2 (4), §3.3 (8), §3.4 (3),
§5 (5) = 35. G-C2 tracks the single "บางส่วน" row and is not counted in the 35.
