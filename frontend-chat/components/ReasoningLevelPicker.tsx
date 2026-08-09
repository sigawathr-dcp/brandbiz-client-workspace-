'use client'

// G-A2: Low / Medium / High / Max reasoning-depth override. Only rendered
// while mode !== 'instant' (caller's responsibility — see ChatPane.tsx).
// Visual style is the lighter pill row from components/client/WorkPanel.tsx.

export type ReasoningLevel = 'low' | 'medium' | 'high' | 'max'

const LEVELS: { key: ReasoningLevel; label: string }[] = [
  { key: 'low', label: 'Low' },
  { key: 'medium', label: 'Med' },
  { key: 'high', label: 'High' },
  { key: 'max', label: 'Max' },
]

interface ReasoningLevelPickerProps {
  value: ReasoningLevel | null
  onChange: (level: ReasoningLevel | null) => void
  disabled?: boolean
}

export default function ReasoningLevelPicker({ value, onChange, disabled }: ReasoningLevelPickerProps) {
  return (
    <div
      role="tablist"
      aria-label="Reasoning level"
      style={{
        display: 'flex',
        gap: 2,
        padding: 2,
        background: 'var(--surface-2)',
        borderRadius: 8,
        flexShrink: 0,
        opacity: disabled ? 0.5 : 1,
      }}
    >
      {LEVELS.map(l => {
        const active = l.key === value
        return (
          <button
            key={l.key}
            type="button"
            role="tab"
            aria-selected={active}
            disabled={disabled}
            // Clicking the already-selected level clears the override, so
            // the mode's own default (see app.llm.tuning._MODE_DEFAULT_REASONING)
            // applies again — matches how ModelPicker's "auto" behaves.
            onClick={() => onChange(active ? null : l.key)}
            style={{
              height: 26,
              padding: '0 9px',
              borderRadius: 6,
              border: 'none',
              fontSize: 11.5,
              fontWeight: active ? 600 : 500,
              background: active ? 'var(--accent-weak)' : 'transparent',
              color: active ? 'var(--accent)' : 'var(--ink-3)',
              cursor: disabled ? 'default' : 'pointer',
              transition: 'all 0.1s',
            }}
          >
            {l.label}
          </button>
        )
      })}
    </div>
  )
}
