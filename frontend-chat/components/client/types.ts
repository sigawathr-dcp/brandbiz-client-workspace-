// Client Workspaces (Phase 5, D21/D22) — shared types for components/client/**.

export interface Chip {
  index: number
  label: string
  // The value the server stores when this chip is picked. Sent only on
  // IntakeField.options (GET /client/bootstrap -> intake_fields), where the
  // Profile tab's edit mode uses it to mark the current answer — `label` is
  // Thai and the stored value English, so they never compare equal.
  value?: string
}

export interface CurrentStep {
  field: string
  question: string
  options: Chip[]
  // True when the client may pick SEVERAL chips (the six scoring questions)
  // — IntakeChips then toggles selections and answers on an explicit
  // confirm, instead of answering on first tap.
  multi_select: boolean
}

export interface IntakeAnswerResponse {
  step: number
  total_steps: number
  completed: boolean
  completion_message: string | null
  current_step: CurrentStep | null
  insight: string | null
  // Canonical fields after this answer — see ClientWorkspace.tsx::answerIntake
  // for why the frontend replaces its whole `fields` state from this instead
  // of guessing at what the server stored.
  fields: Record<string, string>
}

export interface IntakeField {
  key: string
  label: string
  // Same chips the intake step offered — lets the Profile tab's edit mode
  // (Task 5.11) render familiar chips instead of a bare free-text box.
  options: Chip[]
  // Mirrors CurrentStep.multi_select — the edit mode's chips toggle instead
  // of replacing each other on a multi-select field.
  multi_select: boolean
}

export interface BootstrapData {
  workspace: { id: string; name: string; slug: string }
  agent: {
    id: string
    name: string
    avatar_color: string | null
    skill_count: number
    file_count: number
    web_search: boolean
  } | null
  conversation_id: string | null
  // DB redesign — the id of the engagement this bootstrap describes
  // (app/models/engagement.py::Engagement) and which of its plans is
  // "active" (what a revision targets, what the switcher checkmarks) —
  // server state now, replacing the old bb:activePlan:* localStorage key.
  engagement_id: string
  active_plan_id: string | null
  step: number
  total_steps: number
  completed: boolean
  fields: Record<string, string>
  // Ordered display manifest for the Profile tab — the backend intake
  // script is the single source of truth for field keys, labels, and
  // order (app/services/client_intake.py::field_manifest).
  intake_fields: IntakeField[]
  current_step: CurrentStep | null
  plan_count: number
  // True when an internal staff member is previewing the demo workspace
  // rather than a real redeemed client seat — see
  // app/deps.py::require_client_context on the backend.
  is_preview: boolean
  // D23 — true when client-workspace seats may use the full internal app
  // right now (settings.client_internal_access_enabled). See
  // app/deps.py::require_internal on the backend.
  internal_app_enabled: boolean
  // Replays a prior market scan / case match / saved plan so the "Your
  // journey" chapters (and the Research/Cases work-panel tabs) stay
  // unlocked across a page reload — see app/routers/client.py::BootstrapOut
  // for why 'pending' never appears here (mapped to 'error' instead).
  research_status: 'idle' | 'pending' | 'done' | 'error'
  research: ResearchResult | null
  cases_status: 'idle' | 'pending' | 'done' | 'error'
  cases: CasesResult | null
  // The engagement's saved plan, replayed as the in-thread plan card. Before
  // this existed bootstrap carried plan titles only (`plans` below), so a
  // reload dropped the plan card out of the chat even though /w/plans still
  // listed the plan — see app/routers/client.py::_plan_replay. null when the
  // engagement has no saved plan (an unsaved draft is not replayable —
  // POST /client/plan/draft persists no artifact).
  plan: PlanReplay | null
  // Task 5.12 — a seat can hold several plans (POST /client/plans always
  // creates a new one; there's no unique constraint tying a workspace/user
  // to a single row), so bootstrap replays the full list, newest first,
  // instead of only the most recently saved one.
  plans: PlanSummary[]
  // The real chat bubbles to re-render, oldest first — the interview Q&A
  // ('interview') followed by any free-form turns ('chat'). Replaces the
  // synthetic thread this component used to rebuild on every mount, which
  // meant a refresh / tab close / phone screen-lock discarded everything
  // the client had read. See app/routers/client.py::_transcript.
  transcript: TranscriptTurn[]
}

export interface TranscriptTurn {
  who: 'ai' | 'user'
  stage: 'interview' | 'chat'
  text: string
}

export interface PlanSummary {
  id: string
  title: string
  version: number
}

export interface Finding {
  text: string
}

export interface Citation {
  index: number
  source: string
}

export interface ResearchResult {
  id: string
  findings: Finding[]
  citations: Citation[]
}

export interface CaseMatchItem {
  file_id: string
  filename: string
  score: number
  rationale: string | null
  // Parsed from the case-study markdown by app/services/case_card.py —
  // all best-effort, null when the document drifts from the template.
  title?: string | null
  client?: string | null
  category?: string | null
  source_url?: string | null
  summary?: string | null
  image_url?: string | null
  // Scoring dimensions this case matched the client's intake on outright,
  // already localised to Thai by the backend (app/routers/client.py::
  // _DIMENSION_TH). Empty for matches stored before the weighted scorer
  // existed, and whenever the tag model is switched off — the card then
  // shows the score alone rather than claiming a match it cannot evidence.
  matched_on?: string[] | null
}

export interface CasesResult {
  matches: CaseMatchItem[]
}

export interface BudgetLine {
  code: string
  label: string
  section: string | null
  unit: string | null
  qty: string
  unit_price: string
  amount: string
}

export interface Budget {
  lines: BudgetLine[]
  needs_expert: { code: string; qty: string }[]
  subtotal: string
  contingency: string
  total: string
  currency: string
}

export interface AdaptedPlanItem {
  period: string
  text: string
}

export interface DraftPlan {
  title: string
  core_idea: string
  analogous_case: string
  adapted_plan: AdaptedPlanItem[]
  budget: Budget
  provenance: Record<string, unknown>
  conversation_id: string
}

// GET /client/bootstrap's `plan` — a DraftPlan that is already saved, so it
// also carries the plan id (what the card's "View saved plan" link needs) and
// the current version number. Reusing DraftPlan keeps the replayed card and a
// fresh draft the same shape for PlanDraftCard.
export interface PlanReplay extends DraftPlan {
  id: string
  version: number
}

// What POST /client/plan/revise changed, computed server-side
// (app/services/plan.py::diff_versions). A chat edit is a re-draft under an
// instruction, so the model CAN reword sections nobody asked about — this is
// what makes that visible on the card instead of silent.
export interface PlanDiff {
  // Narrative fields that differ from the previous version: 'title',
  // 'core_idea', 'analogous_case', 'adapted_plan'.
  fields: string[]
  budget: {
    added: { code: string; label: string | null; amount: string | null }[]
    removed: { code: string; label: string | null; amount: string | null }[]
    qty_changed: { code: string; label: string | null; from: string; to: string }[]
    total_before: string | null
    total_after: string | null
  }
}

// POST /client/plan/revise — already committed as the next version by the time
// the frontend sees it (the confirmation chip was the confirmation), so it
// carries the id and version a PlanReplay does plus what changed and why.
export interface RevisedPlan extends PlanReplay {
  revision_note: string
  diff: PlanDiff
}

export interface PlanVersionSummary {
  version: number
  created_at: string
}

export interface PlanRatingData {
  score: number
  comment: string | null
  created_at: string
}

export interface SavedPlan {
  id: string
  title: string
  status: string
  version: number
  core_idea: string
  analogous_case: string
  adapted_plan: AdaptedPlanItem[]
  budget: Budget | null
  provenance: Record<string, unknown> | null
  created_at: string
  // The workspace agent's display name at read time — null when the
  // workspace has no assigned agent (see app/routers/client.py::PlanOut).
  agent_name: string | null
  // Only populated by GET /client/plans/{id} — see app/routers/client.py::_plan_out.
  versions: PlanVersionSummary[]
  rating: PlanRatingData | null
}

// GET /client/plans/{id}/versions/{v} (Task 5.12) — a historical version's
// body, read-only. title/provenance are the version's own snapshot
// (migration 0049); for a version saved before that migration, title falls
// back server-side to the parent Plan's title and provenance is null.
export interface PlanVersionBody {
  version: number
  created_at: string
  title: string
  core_idea: string
  analogous_case: string
  adapted_plan: AdaptedPlanItem[]
  budget: Budget | null
  provenance: Record<string, unknown> | null
}

export type TurnKind = 'text' | 'research' | 'cases' | 'plan' | 'milestone'

export interface Turn {
  id: string
  who: 'ai' | 'user' | 'sys'
  kind: TurnKind
  text: string
  streaming?: boolean
  researchStatus?: 'pending' | 'done' | 'error'
  research?: ResearchResult
  researchError?: string
  casesStatus?: 'pending' | 'done' | 'error'
  cases?: CasesResult
  casesError?: string
  planStatus?: 'pending' | 'done' | 'error'
  plan?: DraftPlan
  planError?: string
  // Set when the draft failed with HTTP 503 — the workspace is missing a
  // piece of setup (no assigned agent, no rate card) rather than having hit
  // a transient provider failure. Retrying cannot clear it, so the card
  // drops "try again in a moment".
  planSetupError?: boolean
  planSaved?: boolean
  savedPlanId?: string
  // Set when a save/revise attempt on this card's plan failed — surfaced
  // on the card instead of only console.error'd (Task 5.12).
  planSaveError?: string
  // Set iff this plan card is a chat-driven revision rather than a fresh
  // draft — see PlanDraftCard's `revision` prop. Its presence is what turns
  // the card into "already saved, here is what changed".
  planRevision?: { version: number; note: string; diff: PlanDiff }
  // Set on an AI turn when the backend judged the client's message to be a
  // request to change their plan (SSE notice `plan_edit_suggested`). Renders
  // as a confirmation chip; nothing is revised until the client taps it.
  // 'offered' → chip is up, 'running' → revision in flight, 'used'/'dismissed'
  // → chip is gone.
  planEdit?: {
    planId: string
    instruction: string
    status: 'offered' | 'running' | 'used' | 'dismissed'
    error?: string
  }
  // set iff kind === 'milestone' — see MilestoneTurn.tsx
  milestone?: { title: string; sub: string }
  // set on the AI turn that follows an intake answer — see InsightCallout.tsx
  insight?: string
}
