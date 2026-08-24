 Client Workspace — Database Redesign

 Context

 The client workspace is a 4-step funnel: Interview → Market scan → Case match → Plan & budget, plus a chat thread running alongside it. The schema was built one step at a time (migrations 0041, 0042, 0043, 0044, 0047–0049), so each step got its own table with no shared parent. The result:

 There is no row anywhere that represents "one client's run through the 4 steps." The four step tables are glued together by repeating the same three columns — (workspace_id, user_id, conversation_id) — on each one. That triple is a de-facto foreign key to a table that does not exist.

 Concrete costs of that, all present in the code today:

 ┌─────┬───────────────────────────┬────────────────────────────────────────────────────────────────────────────────────────────────────┐
 │  #  │          Problem          │                                              Evidence                                              │
 ├─────┼───────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │     │ No server-side journey    │                                                                                                    │
 │ 1   │ state at all. The 4       │ frontend-chat/components/client/journey.ts::deriveJourney() reconstructs all 4 chapters from 9     │
 │     │ chapters exist only in    │ loose inputs. GET /client/bootstrap exists mainly to feed that reconstruction.                     │
 │     │ the browser.              │                                                                                                    │
 ├─────┼───────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │     │ Step 3 has no run record, │ backend/app/routers/client.py:353-367 — a zero-match run leaves no rows, so it SELECTs audit_log   │
 │ 2   │  so the audit log is      │ WHERE action='case_matched' to tell "never ran" from "ran, found nothing". Violates §7.3 (audit is │
 │     │ queried as application    │  append-only compliance, not app state), and that query is not scoped to conversation_id — a stale │
 │     │ state.                    │  audit row makes the current conversation report cases_done with an empty list.                    │
 ├─────┼───────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │     │ Three different status    │ DB pending/done/failed (VALID_RESEARCH_STATUSES) → API/journey idle/pending/done/error → step 3    │
 │ 3   │ vocabularies for the same │ has none. research_runs.status='pending' is unreachable (no worker), so client.py:298 hardcodes    │
 │     │  concept.                 │ {"pending": "error"}.                                                                              │
 ├─────┼───────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │ 4   │ A seat gets exactly one   │ uq_client_profiles_workspace_user. A returning client cannot start a second brief.                 │
 │     │ interview, forever.       │                                                                                                    │
 ├─────┼───────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │     │ All 8 interview answers   │ client_profiles.fields_ciphertext = json.dumps({field: value}) AES-GCM'd. No per-answer            │
 │ 5   │ are one opaque encrypted  │ timestamps, no edit history (the intake_edited audit row records only {"field": name} — never      │
 │     │ blob.                     │ old/new), every read decrypts all 8, and zero queryability.                                        │
 ├─────┼───────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │     │ Interview position is a   │ client_profiles.step indexes INTAKE_SCRIPT. Reordering or inserting a question silently            │
 │ 6   │ bare integer index into a │ reinterprets every stored row. No script version column exists.                                    │
 │     │  Python list.             │                                                                                                    │
 ├─────┼───────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │     │ The research query is a   │ research_runs.query (plain Text) = "…Business context: " + build_context_query(fields). The        │
 │ 7   │ plaintext copy of the     │ answers are encrypted in client_profiles and then written next door in the clear.                  │
 │     │ encrypted answers.        │                                                                                                    │
 ├─────┼───────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │     │ Findings/citations are    │ client.py:695 — [{"text": s} for s in full_text.split("\n")]. The model docstrings promise         │
 │ 8   │ fake structure.           │ citation_indexes and title; neither is ever written. Citations join to findings by an integer      │
 │     │                           │ index inside a JSONB blob.                                                                         │
 ├─────┼───────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │     │ Case cards are re-parsed  │ case_matches stores only filename/score; services/case_card.py::parse_case_card() re-regexes the   │
 │ 9   │ from markdown on every    │ file's chunks on each read. No case-study catalog table.                                           │
 │     │ request.                  │                                                                                                    │
 ├─────┼───────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │ 10  │ Case-match history is     │ client.py:762-768 deletes and re-inserts. The eval harness can never reconstruct what a real       │
 │     │ destroyed on every run.   │ client actually saw.                                                                               │
 ├─────┼───────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │     │ plans is both container   │ plans carries title/body_*/budget/provenance/version; plan_versions duplicates them. 0049 added    │
 │ 11  │ and current version — the │ title/provenance to plan_versions late and nullable, so every reader needs fallback logic and the  │
 │     │  head/history split done  │ rail renders "Provenance wasn't recorded for this version". No UNIQUE (plan_id, version) —         │
 │     │ twice.                    │ plan.py:345-359 compensates with ORDER BY created_at DESC LIMIT 1.                                 │
 ├─────┼───────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │     │ Budget is untyped JSONB   │ plans.budget {"lines":[…], "subtotal":"0.00"}. plans.provenance's docstring (rate_card/cases) does │
 │ 12  │ with money as strings and │  not match what plan.py:184 writes (rate_card_codes/case_files/research_sources). Frontend         │
 │     │  no FK to the rate card.  │ consumes it as Record<string, unknown> and parses defensively.                                     │
 ├─────┼───────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │ 13  │ The drafted plan is never │ POST /client/plan/draft returns an ephemeral dict. A reload loses an expensive LLM call.           │
 │     │  persisted.               │                                                                                                    │
 ├─────┼───────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │     │ "Which plan is active" is │ bb:activePlan:${workspaceId}. PUT /client/plans/{id} targets whatever that key says — a second     │
 │ 14  │  browser localStorage.    │ device revises a different plan, and the strategist on the leads inbox cannot know which plan the  │
 │     │                           │ client considers current.                                                                          │
 ├─────┼───────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │     │ The interview never       │ _get_or_create_profile creates a Conversation so a later chat turn has a consistent id, but intake │
 │ 15  │ becomes conversation      │  writes no Message rows. load_history_messages reads from messages, so the agent in free-form chat │
 │     │ history.                  │  has no record of the 8 answers.                                                                   │
 ├─────┼───────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │ 16  │ conversations has no      │ Seat isolation goes through users only; every workspace-scoped conversation query needs a join.    │
 │     │ workspace_id.             │                                                                                                    │
 └─────┴───────────────────────────┴────────────────────────────────────────────────────────────────────────────────────────────────────┘

 Decisions taken (confirmed with the user): full redesign including payload normalization; data must be preserved via staged migrations; a seat may run the 4 steps more than once.

 Not in scope: per-tenant schemas/databases, tenant self-service admin (PLAN.md §11). The plan_ratings.comment plaintext exception stays as documented. plans.status stays a liability badge (draft · awaiting expert review) and is never touched by a revision.

 ---
 Figure 1 — Current schema: four islands

 mermaid
 graph TB
     subgraph GLUE["glued only by a repeated triple: (workspace_id, user_id, conversation_id)"]
         direction LR
         P["1. client_profiles<br/>step 0..8 = index into a PYTHON LIST<br/>all 8 answers in ONE encrypted blob"]
         R["2. research_runs<br/>status pending/done/failed<br/>query is a PLAINTEXT copy of the answers<br/>findings + citations as JSONB"]
         C["3. case_matches<br/>NO status column<br/>deleted and re-inserted every run<br/>card re-parsed from markdown per read"]
         L["4. plans<br/>title + body + budget + provenance<br/>duplicated into plan_versions<br/>no UNIQUE plan_id version"]
     end
     A["audit_log"] -.->|"client.py:353 SELECTs this to tell<br/>'never ran' from 'ran, found nothing'"| C
     J["journey.ts in the BROWSER"] -.->|"reconstructs all 4 chapters<br/>from 9 loose bootstrap fields"| GLUE

 The four step tables never reference each other. Everything that ties them together lives in journey.ts in the browser.

 ---
 Figure 2 — Proposed schema

 mermaid
 erDiagram
     workspaces ||--o{ users : "seats"
     workspaces ||--o{ engagements : ""
     users      ||--o{ engagements : ""

     engagements ||--o{ engagement_steps : "exactly 4"
     engagements ||--|| conversations    : "1:1 chat thread"
     engagements ||--o{ plans            : ""
     engagements ||--o{ leads            : ""

     conversations ||--o{ messages : ""
     engagement_steps ||--o{ messages : "which chapter a turn belongs to"

     engagement_steps ||--o{ intake_answers  : "step 1"
     engagement_steps ||--o{ research_runs   : "step 2"
     engagement_steps ||--o{ case_match_runs : "step 3"
     engagement_steps ||--o{ plan_drafts     : "step 4"

     intake_scripts   ||--o{ intake_questions : "versioned"
     intake_questions ||--o{ intake_options   : ""
     intake_questions ||--o{ intake_answers   : ""
     intake_options   |o--o{ intake_answers   : "chip pick = FK, queryable"

     research_runs ||--o{ research_findings  : ""
     research_runs ||--o{ research_citations : ""
     research_findings }o--o{ research_citations : "real join, not an int index"

     case_match_runs ||--o{ case_matches : "run row exists even at 0 matches"
     case_studies    ||--o{ case_matches : ""
     files           ||--o| case_studies : "parsed ONCE"

     plans ||--o{ plan_versions : ""
     plans }o--o| plan_versions : "current_version_id"
     plan_versions ||--o{ plan_budget_lines : ""
     plan_versions ||--o{ plan_sources      : "provenance as ROWS"
     rate_card_items |o--o{ plan_budget_lines : ""
     plans ||--o| plan_ratings : ""
     plans ||--o{ leads : ""

     engagements {
         uuid id PK
         uuid workspace_id FK
         uuid user_id FK
         uuid conversation_id FK
         uuid active_plan_id FK "replaces localStorage"
         uuid intake_script_id FK
         str  status "active / completed / abandoned"
         int  seq "1,2,3... per seat"
     }
     engagement_steps {
         uuid id PK
         uuid engagement_id FK
         int  step_no "1..4"
         str  step_key "interview / market / cases / plan"
         str  status "idle / running / done / failed / skipped"
         int  progress_current "1..8 for interview"
         int  progress_total
         int  attempt_count
         ts   started_at
         ts   completed_at
         str  error_code
     }
     intake_answers {
         uuid engagement_step_id FK
         uuid question_id FK
         uuid option_id FK "NULL for free text"
         bytea value_ct "free text only"
         str  source "chip / free_text / edit"
         ts   answered_at
         ts   superseded_at "append-only edits"
     }
     plan_budget_lines {
         uuid plan_version_id FK
         uuid rate_card_item_id FK "nullable = needs_expert"
         str  code
         numeric qty
         numeric unit_price "NUMERIC(12,2), not a string"
         numeric amount
         bool needs_expert
     }
     plan_sources {
         uuid plan_version_id FK
         str  kind "rate_card / case_study / research_citation"
         uuid ref_id
         str  label_snapshot "frozen at draft time"
     }

 Figure 3 — One uniform step lifecycle, replacing three vocabularies

 mermaid
 stateDiagram-v2
     [*] --> idle
     idle --> running : POST /client/{step}
     running --> done : success
     running --> failed : error (attempt_count++)
     failed --> running : retry
     done --> running : re-run after profile edit
     done --> [*]

     note right of idle
       Same 5 states for all 4 steps.
       Step 3 gets a run row even at
       0 matches -> the audit_log
       probe (client.py:353) is deleted.
     end note

 step_key reuses the frontend's existing CHAPTER_ORDER ids (interview, market, cases, plan) verbatim, so journey.ts keeps its vocabulary and simply reads the journey instead of deriving it.

 ---
 Target schema — table by table

 Backbone

 engagements — one run through the 4 steps.
 id, workspace_id FK CASCADE, user_id FK CASCADE, seq INT (1,2,3… per seat), conversation_id FK SET NULL, intake_script_id FK RESTRICT, active_plan_id FK SET NULL, status VARCHAR(16) (active|completed|abandoned), created_at, updated_at, completed_at.
 - UNIQUE (workspace_id, user_id, seq)
 - Partial unique: UNIQUE (workspace_id, user_id) WHERE status = 'active' — one active engagement per seat, unlimited archived. Replaces uq_client_profiles_workspace_user (problem 4).
 - active_plan_id replaces the bb:activePlan:* localStorage key (problem 14).

 engagement_steps — uniform per-step state.
 id, engagement_id FK CASCADE, step_no SMALLINT (1–4), step_key VARCHAR(16), status VARCHAR(16), progress_current SMALLINT, progress_total SMALLINT, attempt_count INT DEFAULT 0, started_at, completed_at, error_code VARCHAR(64), error_detail TEXT.
 - UNIQUE (engagement_id, step_no); CHECK (step_no BETWEEN 1 AND 4)
 - Follow house convention (Gotcha #5): VARCHAR + module-level frozenset, not a PG enum. New constant VALID_STEP_STATUSES = frozenset({"idle","running","done","failed","skipped"}) in app/models/engagement.py.
 - 4 rows inserted at engagement creation, all idle. Solves problems 1, 2, 3.
 - For step 1, progress_current/progress_total carry what client_profiles.step / total_steps() do today.

 Step 1 — Interview

 intake_scripts — id, version INT, locale VARCHAR(8), name, published_at, active BOOL. UNIQUE (version, locale).
 intake_questions — id, script_id FK CASCADE, ordinal SMALLINT, field_key VARCHAR(64), prompt TEXT, insight TEXT. UNIQUE (script_id, ordinal), UNIQUE (script_id, field_key).
 intake_options — id, question_id FK CASCADE, ordinal SMALLINT, label TEXT (Thai chip), value VARCHAR(255) (English). UNIQUE (question_id, ordinal).

 Seeded from INTAKE_SCRIPT in backend/app/services/client_intake.py as version 1. client_intake.py keeps resolve_answer() and the helper API but reads the catalog from the DB — the Python literal becomes seed data, not runtime truth. Fixes problem 6: engagements.intake_script_id pins which script a stored answer was given against.

 intake_answers — append-only.
 id, engagement_step_id FK CASCADE, question_id FK RESTRICT, field_key VARCHAR(64) (denormalized for the common read), option_id FK NULL, value_ciphertext BYTEA NULL, value_nonce, value_tag, key_version, source VARCHAR(16) (chip|free_text|edit), answered_at, superseded_at NULL.
 - CHECK (option_id IS NOT NULL OR value_ciphertext IS NOT NULL)
 - Partial unique: UNIQUE (engagement_step_id, field_key) WHERE superseded_at IS NULL — exactly one live answer per field.
 - The key move: a chip pick stores option_id (a queryable FK, no ciphertext); only free text is encrypted. §7.1 is honoured and "how many attendees picked Food & beverage" becomes a GROUP BY. Fixes problem 5.
 - PATCH /client/intake/fields stamps superseded_at and inserts a new row — real edit history, which the intake_edited audit row cannot provide.

 Step 2 — Market scan

 research_runs — id, engagement_step_id FK CASCADE, query_ciphertext/_nonce/_tag/key_version (encrypted — fixes problem 7), model_used, status, tokens_input, tokens_output, cost_usd NUMERIC(10,6), created_at, completed_at, error_detail.
 Drops workspace_id/user_id/conversation_id (reachable via the step → engagement).

 research_findings — id, research_run_id FK CASCADE, ordinal SMALLINT, text TEXT. UNIQUE (run_id, ordinal).
 research_citations — id, research_run_id FK CASCADE, ordinal SMALLINT, url TEXT, title TEXT NULL, source_domain VARCHAR(255) NULL. UNIQUE (run_id, ordinal).
 research_finding_citations — composite PK (finding_id, citation_id). Replaces the never-written citation_indexes (problem 8) with a real join.

 Step 3 — Case matching

 case_studies — the catalog, parsed once.
 id, workspace_id FK CASCADE, file_id FK CASCADE UNIQUE, title, client_name, category, source_url, image_url, summary TEXT, content_sha256 CHAR(64), parser_version SMALLINT, parsed_at.
 Populated by services/case_card.py::parse_case_card() at ingestion time; re-parsed only when content_sha256 changes. Fixes problem 9.

 case_match_runs — id, engagement_step_id FK CASCADE, query_ciphertext/_nonce/_tag/key_version, top_k SMALLINT, status, match_count SMALLINT, created_at, completed_at.
 A run row exists even at zero matches → client.py:353-367's audit_log probe is deleted (problem 2).

 case_matches — id, case_match_run_id FK CASCADE, case_study_id FK RESTRICT, rank SMALLINT, score DOUBLE PRECISION, rationale TEXT. UNIQUE (run_id, case_study_id).
 Append-only per run instead of delete-and-replace — the eval harness can reconstruct what a real client saw (problem 10). plan.py's stale-match bug is solved structurally: read the latest run's matches, not "all matches ordered by score".

 Step 4 — Plan & budget

 plans — head only. id, engagement_id FK CASCADE, workspace_id, user_id, current_version_id FK SET NULL, status VARCHAR(16) (draft|expert_review|final), share_token_hash UNIQUE, created_at, updated_at.
 title/body_*/budget/provenance/version all move to plan_versions (problem 11).

 plan_versions — all content. id, plan_id FK CASCADE, version_no INT, title VARCHAR(500) NOT NULL, body_ciphertext/_nonce/_tag/key_version NOT NULL, subtotal_amount NUMERIC(12,2), contingency_rate NUMERIC(5,4), contingency_amount NUMERIC(12,2), total_amount NUMERIC(12,2), currency CHAR(3), created_by FK, created_at, note.
 - UNIQUE (plan_id, version_no) — removes the ORDER BY created_at DESC LIMIT 1 workaround.
 - title NOT NULL — no more nullable-snapshot fallback logic.

 plan_budget_lines — id, plan_version_id FK CASCADE, ordinal SMALLINT, rate_card_item_id FK SET NULL, code VARCHAR(64), label VARCHAR(255), section VARCHAR(16), unit VARCHAR(64), qty NUMERIC(10,2), unit_price NUMERIC(12,2), amount NUMERIC(12,2), currency CHAR(3), needs_expert BOOL.
 Money as NUMERIC, not strings. rate_card_item_id gives the FK the JSONB never had; label/unit_price are frozen snapshots so a rate-card change never rewrites a signed plan. needs_expert = TRUE ⟺ rate_card_item_id IS NULL — the anti-hallucination guard becomes a DB invariant instead of a JSON key (problem 12).

 plan_sources — provenance as rows. id, plan_version_id FK CASCADE, ordinal, kind VARCHAR(24) (rate_card|case_study|research_citation), ref_id UUID, label_snapshot TEXT, score_snapshot DOUBLE PRECISION NULL.
 Replaces plans.provenance, whose docstring and writer already disagree.

 plan_drafts — id, engagement_step_id FK CASCADE, body_ciphertext/_nonce/_tag/key_version, budget_json JSONB, created_at, discarded_at NULL.
 Persists POST /client/plan/draft so a reload does not throw away an LLM call (problem 13). Discarded on save.

 plan_ratings, leads, rate_card_items — unchanged except leads gains engagement_id FK.

 Chat history

 conversations — add workspace_id FK (denormalized; removes the join through users, problem 16), engagement_id FK NULL, kind VARCHAR(24) (internal|client_workspace). Add onupdate to updated_at (currently missing).
 messages — add engagement_step_id FK NULL. Lets the transcript replay per chapter instead of being rebuilt synthetically on reload.
 Intake turns become real Message rows (encrypted, engagement_step_id → step 1), so chat_policy.py::load_history_messages finally sees the interview (problem 15). Safe under D14: the canonical answers live in intake_answers; only the chat copy is purged at 30 days.

 ---
 Migration plan — expand → backfill → contract

 Current head is 0049_plan_version_snapshot. Every migration below is hand-written raw SQL via op.execute(...), matching house style. Nothing is dropped until stage 6.

 ⚠️ Migrations 0044, 0045, 0047, 0048, 0049 have never been run against a real DB (standing item in PROGRESS.md). Run alembic upgrade head and confirm it is clean before starting 0050.

 Stage: 1 — backbone
 Migration: 0050_engagements
 Content: Create engagements + engagement_steps. Add nullable engagement_id to research_runs, case_matches, plans, leads, conversations; add
 engagement_step_id to messages. Add workspace_id/kind to conversations.
 ────────────────────────────────────────
 Stage: 1 — backfill
 Migration: 0051_engagements_backfill
 Content: One engagements row per client_profiles row (seq=1, status from completed_at). Four engagement_steps per engagement, statuses
 derived: interview from client_profiles.step/completed_at; market from the latest research_runs.status; cases from row existence plus the
 historical audit_log probe run one last time; plan from plans existence. Backfill engagement_id on all child tables via the (workspace_id,
  user_id, conversation_id) triple.
 ────────────────────────────────────────
 Stage: 2 — interview
 Migration: 0052_intake_catalog
 Content: Create + seed intake_scripts/intake_questions/intake_options from INTAKE_SCRIPT as version 1, locale th.
 ────────────────────────────────────────
 Stage: 2
 Migration: 0053_intake_answers
 Content: Create intake_answers. Python data migration — decrypts client_profiles.fields_*, matches each value against intake_options.value
 (chip → option_id) or re-encrypts as free text. Requires ENCRYPTION_KEY in the migration environment; document this in the migration
 docstring and in .env.example.
 ────────────────────────────────────────
 Stage: 3 — research
 Migration: 0054_research_normalized
 Content: Create research_findings/research_citations/research_finding_citations; backfill from the JSONB. Add encrypted query_* columns and
 backfill from plaintext query.
 ────────────────────────────────────────
 Stage: 4 — cases
 Migration: 0055_case_studies
 Content: Create case_studies; backfill by parsing each distinct case_matches.file_id through parse_case_card(). Create case_match_runs;
 synthesize one run per distinct (engagement, created_at::date) group; repoint case_matches at it.
 ────────────────────────────────────────
 Stage: 5 — plans
 Migration: 0056_plan_head_split
 Content: Create plan_budget_lines, plan_sources, plan_drafts. Backfill a plan_versions row for any plans head with no matching version.
 Explode every version's budget JSONB into plan_budget_lines (needs_expert entries → rate_card_item_id IS NULL) and provenance into
 plan_sources. Set plans.current_version_id. Add UNIQUE (plan_id, version_no).
 ────────────────────────────────────────
 Stage: 6 — contract
 Migration: 0057_drop_legacy
 Content: Drop client_profiles; drop plans.title/version/body_*/budget/provenance; drop
 research_runs.findings/citations/query/workspace_id/user_id/conversation_id; drop
 case_matches.workspace_id/user_id/conversation_id/filename; set new FKs NOT NULL.

 Run stages 1–5 and deploy; the application dual-reads (new tables preferred, legacy as fallback) across that window. Stage 6 only after the new read paths are verified in the running app. Every stage has a working downgrade() except 0057.

 ---
 Application changes

 New/changed models — backend/app/models/:
 - New engagement.py (Engagement, EngagementStep, VALID_ENGAGEMENT_STATUSES, VALID_STEP_STATUSES, STEP_KEYS).
 - New intake.py (IntakeScript, IntakeQuestion, IntakeOption, IntakeAnswer) — client_intake.py's ClientProfile is deleted at stage 6.
 - client_intake.py → ResearchRun slims down; new ResearchFinding, ResearchCitation, ResearchFindingCitation, CaseStudy, CaseMatchRun, CaseMatch.
 - plan.py → Plan slims to head; PlanVersion gains totals; new PlanBudgetLine, PlanSource, PlanDraft.
 - Register all new tables in models/__init__.py __all__. Also fix the two pre-existing drifts found during exploration: 'messages_purged' is missing from _audit_action_pg in models/audit.py (added to the PG type by 0047), and HermesHostJob is imported but absent from __all__.

 New service — backend/app/services/engagement.py, the single owner of step state. One responsibility per file (CLAUDE.md). Public surface:
 get_or_create_active(session, user, workspace_id), start_new(session, user, workspace_id), mark_step(session, step_id, status, *, error_code=None), journey(session, engagement_id) -> JourneyOut. Every step transition goes through mark_step — nothing else writes engagement_steps.status.

 Router — backend/app/routers/client.py:
 - GET /client/bootstrap returns a typed journey: JourneyOut (4 step objects with step_key, status, progress, error_code) instead of the four loose step/research_status/cases_status/plan_count fields. BootstrapOut's four untyped dict members become real Pydantic models.
 - Delete _bootstrap_research_and_cases's audit_log probe entirely.
 - POST /client/research, POST /client/cases, POST /client/plan/draft each call mark_step(..., 'running') before and 'done'/'failed' after.
 - New POST /client/engagements to start a second brief.
 - POST /client/plans / PUT /client/plans/{id} set engagements.active_plan_id.
 - services/plan.py::draft_plan reads research/cases via engagement_step_id, fixing the scoping divergence at plan.py:119-133 (it filters by (workspace_id, user_id) only, while every other reader also scopes by conversation_id — a seat with two conversations can get a plan drafted from the wrong research run).

 Frontend — frontend-chat/components/client/:
 - journey.ts::deriveJourney becomes a thin adapter over the server's journey payload. Keep CHAPTER_ORDER/CHAPTER_NAMES exactly as they are — step_key is deliberately identical.
 - types.ts: Budget.lines[].qty|unit_price|amount stay strings over the wire (NUMERIC → JSON string is correct); provenance: Record<string, unknown> becomes a typed PlanSource[], so provenance.ts's defensive parsing can be deleted.
 - Remove activePlanStorageKey / localStorage; read active_plan_id from bootstrap.
 - WorkPanel.tsx:172-178's duplicated idx < profile.step editability rule reads journey.interview.progress_current instead of re-deriving from !!fields[key].

 Tests — extend the uncommitted suites (test_client_router_save_plan.py, test_plan_versions.py, …) plus new backend/tests/unit/test_engagement_steps.py (the 5-state machine, one active engagement per seat) and backend/tests/integration/test_engagement_migration.py (seed pre-0050 shaped data, run 0050–0057, assert the journey is identical).

 ---
 Verification

 1. Migrations round-trip. alembic upgrade head then alembic downgrade 0049 then upgrade head again on a scratch DB — clean both ways for 0050–0056.
 2. Backfill fidelity. Before 0050, snapshot GET /client/bootstrap for every existing seat. After 0057, re-fetch and diff: the derived journey, all 8 answers, findings, citations, case matches, and every plan version body must be byte-identical.
 3. Unit tests. cd backend && pytest tests/unit -q — the existing 145-test tenancy suite must stay green; no regressions in the full suite.
 4. The audit-log hack is gone. grep -n "case_matched" backend/app/routers/client.py returns only the audit_svc.log(...) write, no select(AuditLog).
 5. Zero-match case run. Point a seat at a workspace with no case library, run the funnel: the Cases chapter must read "Cases matched · 0 results" from a case_match_runs row — and must still say so after a reload, and must not be affected by another conversation's history.
 6. Second engagement. POST /client/engagements on a completed seat → a fresh 4-step journey, with the first engagement intact and read-only.
 7. Encryption invariant (§7.1). SELECT query FROM research_runs no longer exists; psql inspection of intake_answers shows option_id FKs and ciphertext, never plaintext answers.
 8. End-to-end in the app. Follow the run skill / docker compose up on ports 3100/8100 and click the full funnel at /w. Note the standing gap in PROGRESS.md: frontend-chat has no source mount, so it needs a container rebuild before browser verification.

 ---
 Open item for the user

 plan_drafts (persisting the ephemeral draft, problem 13) is the one item that is genuinely new product behaviour rather than a schema cleanup — everything else preserves current behaviour. It is included because it is cheap once engagement_steps exists, but it can be dropped from 0056 without affecting any other part of this plan.