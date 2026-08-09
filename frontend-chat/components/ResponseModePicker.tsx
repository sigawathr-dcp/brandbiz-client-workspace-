'use client'

// G-A1: Instant / Thinking / Pro response-mode selector. Visual style copied
// from the segmented tab control in components/library/LibraryPage.tsx —
// the closest existing precedent for a 3-way toggle in this codebase.

export type ResponseMode = 'instant' | 'thinking' | 'pro'

const MODES: { key: ResponseMode; label: string; blurb: string }[] = [
  { key: 'instant', label: 'Instant', blurb: 'Fastest answer, no extended reasoning' },
  { key: 'thinking', label: 'Thinking', blurb: 'Takes a bit longer, reasons before answering' },
  { key: 'pro', label: 'Pro', blurb: 'Deepest reasoning available for this model' },
]

interface ResponseModePickerProps {
  value: ResponseMode
  onChange: (mode: ResponseMode) => void
}

export default function ResponseModePicker({ value, onChange }: ResponseModePickerProps) {
  return (
    <div
      role="tablist"
      aria-label="Response mode"
      style={{
        display: 'flex',
        border: '1px solid var(--line-2)',
        borderRadius: 'var(--r-md)',
        overflow: 'hidden',
        flexShrink: 0,
      }}
    >
      {MODES.map(m => {
        const active = m.key === value
        return (
          <button
            key={m.key}
            type="button"
            role="tab"
            aria-selected={active}
            title={m.blurb}
            onClick={() => onChange(m.key)}
            style={{
              padding: '7px 11px',
              border: 'none',
              background: active ? 'var(--accent-weak)' : 'var(--surface)',
              color: active ? 'var(--accent)' : 'var(--ink-3)',
              fontWeight: active ? 600 : 500,
              fontSize: 12.5,
              cursor: 'pointer',
              transition: 'all 0.1s',
            }}
          >
            {m.label}
          </button>
        )
      })}
    </div>
  )
}
