'use client'

import { useEffect } from 'react'
import type { Chip } from './types'

// Client Workspaces (Phase 5, D21/D22) — the numbered option card above the
// composer during intake, ported from the approved design. 1-N keyboard
// shortcuts speed through the script at a booth; "Skip" falls through to
// the free-text composer for the same step.
export default function IntakeChips({
  title,
  chips,
  onPick,
  onSkip,
  disabled,
}: {
  title: string
  chips: Chip[]
  onPick: (chip: Chip) => void
  onSkip: () => void
  disabled?: boolean
}) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (disabled) return
      const target = e.target as HTMLElement | null
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) return
      const n = parseInt(e.key, 10)
      if (n >= 1 && n <= chips.length) {
        e.preventDefault()
        onPick(chips[n - 1])
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [chips, disabled, onPick])

  return (
    <div
      style={{
        marginBottom: 10,
        background: 'var(--surface)',
        border: '1px solid var(--line-2)',
        borderRadius: 14,
        boxShadow: 'var(--shadow-2)',
        overflow: 'hidden',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '13px 16px 11px' }}>
        <div style={{ flex: 1, fontSize: 14, fontWeight: 600, letterSpacing: '-.01em', color: 'var(--ink)' }}>
          {title}
        </div>
      </div>
      {chips.map((chip, i) => (
        <button
          key={chip.index}
          disabled={disabled}
          onClick={() => onPick(chip)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 13,
            width: '100%',
            textAlign: 'left',
            background: 'transparent',
            border: 'none',
            borderTop: '1px solid var(--line)',
            padding: '11px 16px',
            fontSize: 14,
            color: 'var(--ink)',
            cursor: disabled ? 'default' : 'pointer',
            fontFamily: 'var(--font-sans)',
          }}
        >
          <span
            style={{
              width: 22,
              height: 22,
              flex: 'none',
              borderRadius: 6,
              background: 'var(--surface-2)',
              color: 'var(--ink-3)',
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              display: 'grid',
              placeItems: 'center',
            }}
          >
            {i + 1}
          </span>
          <span style={{ flex: 1, lineHeight: 1.45 }}>{chip.label}</span>
        </button>
      ))}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 13,
          borderTop: '1px solid var(--line)',
          background: 'var(--surface-2)',
          padding: '10px 16px',
        }}
      >
        <span style={{ flex: 1, fontSize: 13.5, color: 'var(--ink-4)' }}>พิมพ์คำตอบเองด้านล่าง</span>
        <button
          disabled={disabled}
          onClick={onSkip}
          style={{
            height: 26,
            padding: '0 11px',
            borderRadius: 7,
            border: '1px solid var(--line-2)',
            background: 'var(--surface)',
            color: 'var(--ink-2)',
            fontSize: 12,
            fontWeight: 500,
            cursor: disabled ? 'default' : 'pointer',
          }}
        >
          Skip
        </button>
      </div>
    </div>
  )
}
