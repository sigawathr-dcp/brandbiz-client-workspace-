// Tier definitions — matches the reference prototype + backend constants
export const TIERS = {
  T1: {
    key: 'T1' as const,
    label: 'General',
    th: 'ทั่วไป',
    level: 1,
    description: 'Non-sensitive. Any permitted model.',
    color: 'var(--t1)',
    bg: 'var(--t1-bg)',
  },
  T2: {
    key: 'T2' as const,
    label: 'Internal',
    th: 'ภายใน',
    level: 2,
    description: 'Internal-only. Contact details, internal notes.',
    color: 'var(--t2)',
    bg: 'var(--t2-bg)',
  },
  T3: {
    key: 'T3' as const,
    label: 'Confidential',
    th: 'ลับ',
    level: 3,
    description: 'Customer PII. Stays on the local model.',
    color: 'var(--t3)',
    bg: 'var(--t3-bg)',
  },
  T4: {
    key: 'T4' as const,
    label: 'Restricted',
    th: 'ลับที่สุด',
    level: 4,
    description: 'M&A, source code, board matters. L5+ only, local only.',
    color: 'var(--t4)',
    bg: 'var(--t4-bg)',
  },
} as const

export type TierKey = keyof typeof TIERS

export const ROLES = ['L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'ADMIN'] as const
export type Role = (typeof ROLES)[number]

export const ROLE_LABELS: Record<Role, string> = {
  L1:    'L1 · Associate',
  L2:    'L2 · Analyst',
  L3:    'L3 · Senior',
  L4:    'L4 · Lead',
  L5:    'L5 · Manager',
  L6:    'L6 · Director',
  ADMIN: 'Administrator',
}

export const ROLE_LEVELS: Record<Exclude<Role, 'ADMIN'>, number> = {
  L1: 1, L2: 2, L3: 3, L4: 4, L5: 5, L6: 6,
}

export interface ModelInfo {
  label:    string
  provider: string
  isLocal:  boolean
  free?:    boolean
  blurb?:   string
}

export const MODEL_BY_CODE: Record<string, ModelInfo> = {
  'auto':                   { label: 'Auto (local)',       provider: 'local',      isLocal: true,  free: true,  blurb: 'Routes to local model — always on, no external calls.' },
  'qwen2.5-14b-local':      { label: 'Qwen 2.5 14B',       provider: 'local',      isLocal: true,  free: true,  blurb: 'Runs on our GPU. Free, private, always available.' },
  'claude-haiku-4-5':       { label: 'Claude Haiku 4.5',   provider: 'anthropic',  isLocal: false, free: false, blurb: 'Fast, lightweight Claude for quick tasks.' },
  'claude-sonnet-4':        { label: 'Claude Sonnet 4',    provider: 'anthropic',  isLocal: false, free: false, blurb: 'Balanced quality for everyday work.' },
  'claude-opus-4':          { label: 'Claude Opus 4',      provider: 'anthropic',  isLocal: false, free: false, blurb: 'Top-tier reasoning. Senior roles only.' },
  'gpt-4o-mini':            { label: 'GPT-4o mini',        provider: 'openai',     isLocal: false, free: false, blurb: 'Fast & cost-effective GPT-4o variant.' },
  'gpt-4o':                 { label: 'GPT-4o',             provider: 'openai',     isLocal: false, free: false, blurb: 'Fast general reasoning + vision.' },
  'gemini-2.5-flash':       { label: 'Gemini 2.5 Flash',   provider: 'google',     isLocal: false, free: false, blurb: 'Long context, strong multilingual.' },
  'gemini-2.5-flash-image':  { label: 'Gemini 2.5 Image',   provider: 'google',     isLocal: false, free: false, blurb: 'Image generation via Gemini.' },
  'gemini-3.1-flash-image': { label: 'Gemini 3.1 Flash Image', provider: 'google', isLocal: false, free: false, blurb: 'Image generation via Gemini 3.1 Flash.' },
  'perplexity-sonar':       { label: 'Sonar',              provider: 'perplexity', isLocal: false, free: false, blurb: 'Web-grounded answers with citations.' },
  'hermes-agent':           { label: 'Hermes Agent',       provider: 'hermes',     isLocal: false, free: false, blurb: 'Autonomous agent — researches, uses tools, and remembers. First response takes longer than a chat model.' },
}

export function modelInfo(code: string): ModelInfo {
  return MODEL_BY_CODE[code] ?? { label: code, provider: 'unknown', isLocal: false }
}

// Task 3.12 — background agent tasks. "tone" keys a semantic color (not the
// picker's provider color) the Tasks UI maps to var(--warning)/--success/etc.
export const TASK_STATUS: Record<string, { label: string; tone: 'pending' | 'active' | 'success' | 'danger' | 'muted' }> = {
  queued:            { label: 'Queued',    tone: 'pending' },
  running:           { label: 'Running',   tone: 'active' },
  succeeded:         { label: 'Done',      tone: 'success' },
  failed:            { label: 'Failed',    tone: 'danger' },
  cancelled:         { label: 'Cancelled', tone: 'muted' },
  awaiting_approval: { label: 'Awaiting approval', tone: 'pending' },
}

// Minimum role level (or ADMIN) allowed to see/use background tasks — Hermes
// access defaults to L5/L6/ADMIN (see 0030_hermes_model_catalog.py).
export function canUseTasks(role: string): boolean {
  if (role === 'ADMIN') return true
  const level = ROLE_LEVELS[role as Exclude<Role, 'ADMIN'>]
  return typeof level === 'number' && level >= 5
}
