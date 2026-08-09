# Gap analysis — Brandbiz ecosystem doc vs. CH-AI Gateway codebase

## Context

`brandbiz_ecosystem_and_workflow.md` (untracked, added 2026-07-27) describes a **client-facing**
Brandbiz workspace: a 5-step demo funnel (login → chat with "น้องภูมิ" → gather company info →
pull external market data via IAG → match against Brandbiz case studies → present a plan with
budget estimate → CTA handoff to a human expert). Its action items are narrow: record a demo video
and add a CTA button for an upcoming event.

This repo is a different product. `PLAN.md:3` defines it as an **internal AI chat platform for
~100 employees**, and lists as explicit non-goals **"Customer-facing chatbot"** (`PLAN.md:40`) and
**"Multi-tenancy (single company only)"** (`PLAN.md:1241`). The Brandbiz document is both of those.

This is a gap analysis, not a build plan. It maps each step onto what exists, names what is missing,
and sizes the effort — split into what a **demo** needs versus what a **product** needs, because
those two numbers are wildly different.

---

## Verdict up front

| | Demo (event video) | Product (real client workspace) |
|---|---|---|
| Backend code required | **Essentially none** | Substantial — tenancy, roles, retention |
| Blocking decisions | None | D-level: reverses `PLAN.md:40` and `PLAN.md:1241` |
| Rough size | 1–2 days of seeding + config | Multi-phase; a Phase 5 in its own right |

Steps 1–4 of the funnel can be staged **today** using existing primitives (Agents, Skills, org-scoped
RAG, Perplexity, Studio) with essentially no new backend code. Step 5 and everything about client
isolation is genuinely new.

---

## Step-by-step mapping

### Step 1 — Login & chat with น้องภูมิ

**Exists:**
- Login page `frontend-chat/app/login`, NextAuth Google OAuth + username/password
  (`backend/app/routers/auth.py:96`), JWT cookie.
- Chat UI `frontend-chat/app/chat/[id]` with SSE streaming.
- **The persona is a data row, not code.** `backend/app/models/agent.py` gives an Agent a `name`,
  `instructions` (system prompt), `model`, `capabilities` (`web_search`, `image_gen`, …),
  `creativity_level`, `avatar_color`, `category`. "น้องภูมิ" = one Agent created via
  `frontend-chat/app/agent/create`.

**Missing:**
- **No self-service signup.** Users are admin-provisioned (`frontend-chat/app/(admin)/users`).
  A prospect cannot create an account.
- **No tenant concept.** `backend/app/models/user.py` has `google_email`, `role`, `is_active` — no
  `org_id`. Same for `conversations`, `files`, `agents`, `skills`.
- Branding is CH-AI Gateway, not Brandbiz.

**Effort:** demo — seed one client user + one Agent (**zero code**). Product — **large**; tenancy is
a schema-wide change.

---

### Step 2 — Intake questions + IAG external data

**Exists:**
- **The intake interview is a Skill.** `backend/app/models/skill.py` — `instructions` (a SKILL.md
  body) injected into the system prompt when selected, and pinnable to an Agent
  (`agent_skills`). Injection seam: `backend/app/services/chat_policy.py:167-173`. A scripted
  "ask these 8 questions about the business, one at a time" skill is authorable in the UI at
  `frontend-chat/app/skills/create` — **zero code**.
- **IAG ≈ Perplexity.** `backend/app/llm/perplexity.py` is a live `sonar` client returning
  `citations` in chunk metadata. When the model is `auto`, `classify_intent` routes research-shaped
  messages to it (`chat_policy.py:234-241`), gated by the Agent's `web_search` capability
  (`chat_policy.py:152`).

**Missing:**
- Web search is a **model choice, not a tool** — the agent gets one LLM per turn. No multi-step
  research loop (search → fetch → synthesize), no iterative competitor sweep.
- **No structured company profile.** Answers stay as conversation text; nothing is extracted into
  queryable fields, so nothing downstream can reason over "the client's industry" as data.
- Perplexity citations are captured but not persisted as a research artifact.

**Effort:** demo — **small** (author the intake Skill, enable `web_search`). Product — **medium**
for a real research pipeline + structured profile extraction.

---

### Step 3 — Process against Brandbiz case studies

**Exists — this is the best-covered step.**
- Full RAG pipeline: upload (`frontend-chat/app/chat/knowledge`, `backend/app/routers/files.py`) →
  chunk/embed/dbwriter workers → pgvector HNSW.
- `backend/app/tools/rag_search.py:66` retrieves top-k chunks; retrieval runs on **every** chat turn
  before classification (`chat_policy.py:198-203`), and citations surface as an SSE `sources` event.
- Attaching knowledge files to an Agent (`agent_files`) narrows retrieval to just those files
  (`chat_policy.py:197-201`) — exactly the "score this brand against our case library" shape.

So: upload the case studies, attach them to the ภูมิ Agent, done. **Zero code.**

**Missing — and this is the sharpest technical gap:**
- Scope is binary: `personal` (owner only) or `org` (**any authenticated user**)
  — `rag_search.py:48-63`. With external clients on the platform, org-scoped case studies become
  readable by *every client*, including competitors. There is no third scope and no tenant filter.

**Effort:** demo — **zero**. Product — **medium**; needs a real scope/tenant boundary in
`_scope_filter` and the `files` table.

---

### Step 4 — Plan output + cost valuation

**Exists:**
- Markdown chat output; conversation persistence; `frontend-chat/app/library` for artifacts.
- Infographic option: Studio image generation (`backend/app/tools/image_gen.py`,
  `frontend-chat/app/studio`) is real (Gemini image). Video and music are **mocked** (Task 3.9).

**Missing:**
- **No deliverable-document concept.** The 4-part structure (core idea → analogous case → adapted
  plan → budget) would be a chat message, not an artifact you can name, revise, version, or hand to
  an expert. No PDF/slide export anywhere in the repo.
- **No pricing data.** Nothing in the codebase knows Brandbiz's rates, so "Cost Valuation" is
  hallucinated unless a rate card is ingested as a knowledge file *and* a Skill constrains the
  output format. Treat this as a correctness risk, not a feature gap — a made-up budget in front of
  a client is worse than no budget.
- **Image gen would be blocked for a client user.** `chat_policy.py:297-332` authorizes images only
  for L5+ or the Marketing department. A client provisioned at L1 gets a 403.

**Effort:** demo — **small** (a Skill that fixes the output template + a rate-card file; screenshot
the markdown). Product — **medium**; the plan-as-artifact is genuinely new.

---

### Step 5 — CTA handoff to a human expert

**Exists:**
- The n8n webhook path is the only outbound-to-humans mechanism: `backend/app/services/n8n_client.py`
  + `alert.py`, routed when a keyword matches (`chat_policy.py:338-342`). It fires a webhook and
  emits an acknowledgement in-chat.

**Missing — effectively all of it:**
- No CTA button/UI on any output surface, no lead-capture form, no CRM or notification target, no
  expert-side inbox, no way to hand a conversation to a named human.
- Hermes `AgentTask` is an agent runner, not a human handoff — it does not help here.

**Effort:** demo — **small** (a button that POSTs to n8n; n8n does the routing). Product —
**medium**, mostly integration rather than platform work.

---

## Cross-cutting gaps (the ones that actually decide this)

1. **Non-goal collision.** `PLAN.md:40` (no customer-facing chatbot) and `PLAN.md:1241` (no
   multi-tenancy) both block the product version. `CLAUDE.md` treats D1–D20 and Section 11 as final,
   so this needs an explicit decision before any product work — flagged here, not proposed.
2. **No tenant boundary in the schema.** Isolation between client companies does not exist at any
   layer. Org-scoped RAG actively leaks across users.
3. **The role model inverts.** L1–L6 encode *employee seniority* to restrict access to expensive
   external models. A client at L1 gets local Qwen only — no Perplexity, no image gen — which is the
   opposite of what the funnel needs. The existing lever is D19 (department permissions are additive,
   `PLAN.md:69`); a "client" department could unlock Perplexity + image without touching role logic.
4. **Retention kills the deliverable.** D14 (`PLAN.md:64`) drops `messages.content_*` after 30 days.
   A plan the client engaged you for would evaporate. Plans must live outside message content —
   which also satisfies §7.1 (never write plaintext message content to the DB).
5. **Quota economics differ.** D18's per-role monthly token budget is an internal cost ceiling; a
   client-acquisition funnel needs per-prospect or per-engagement accounting instead.
6. **Audit/reveal becomes client-visible governance.** 4-eyes reveal over *client* conversations is
   defensible internally, but is now a disclosure owed to the client.

---

## Effort summary

| Step | Reusable today | Demo | Product |
|---|---|---|---|
| 1 Login + persona | Auth, chat UI, Agent model | none | large (tenancy, signup) |
| 2 Intake + IAG | Skills, Perplexity, intent routing | small | medium |
| 3 Case studies | Full RAG + agent knowledge files | none | medium (scope boundary) |
| 4 Plan + budget | Chat markdown, Studio, Library | small | medium (artifact + export) |
| 5 Expert CTA | n8n webhook only | small | medium |
| Cross-cutting | — | none | **the real cost** |

---

## Recommendation

Treat these as two separate tracks, and do not let the demo imply the product exists.

- **Demo track (matches the document's own action items).** Seed a client user, build the ภูมิ Agent,
  author 2–3 Skills (intake interview, plan-output template, budget format), upload case studies +
  rate card as knowledge files attached to that Agent, enable `web_search`. Record it. The only real
  code is the CTA button. Watch the L1 image-gen block if the infographic is in the video.
- **Product track.** Blocked on a decision about `PLAN.md:40` / `PLAN.md:1241`. If it proceeds, it
  is a Phase 5, and the first three items are tenancy in the schema, a client-safe RAG scope, and
  plan-as-artifact stored outside `messages.content_*`.

---

## How to verify this analysis

Nothing to run — this is a documentation deliverable. Correctness check:

1. Confirm the claimed seams still hold: `chat_policy.py:167` (skill injection), `:198` (RAG per
   turn), `:234` (intent → Perplexity), `:297` (image authz), `:338` (n8n route).
2. Confirm `rag_search.py:48-63` still has only `personal` / `org` scopes.
3. Confirm `PLAN.md:40` and `PLAN.md:1241` are unchanged, since the whole framing rests on them.
4. Sanity-check the demo claim cheaply: create an Agent with a pinned Skill and an attached knowledge
   file in the running app, and verify the system prompt and citations arrive — this validates
   "Steps 2–4 need no code" without writing any.
