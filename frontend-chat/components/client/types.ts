// Client Workspaces (Phase 5, D21/D22) — shared types for components/client/**.

export interface Chip {
  index: number
  label: string
}

export interface CurrentStep {
  field: string
  question: string
  options: Chip[]
}

export interface IntakeAnswerResponse {
  step: number
  total_steps: number
  completed: boolean
  completion_message: string | null
  current_step: CurrentStep | null
  insight: string | null
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
  conversation_id: string
  step: number
  total_steps: number
  completed: boolean
  fields: Record<string, string>
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
  // Only populated by GET /client/plans/{id} — see app/routers/client.py::_plan_out.
  versions: PlanVersionSummary[]
  rating: PlanRatingData | null
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
  planSaved?: boolean
  savedPlanId?: string
  // set iff kind === 'milestone' — see MilestoneTurn.tsx
  milestone?: { title: string; sub: string }
  // set on the AI turn that follows an intake answer — see InsightCallout.tsx
  insight?: string
}
