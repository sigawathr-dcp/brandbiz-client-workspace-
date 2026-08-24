'use client'

import { useEffect, useState } from 'react'
import { Ic } from '../ui/Icon'
import type { Chip } from './types'

// Client Workspaces (Phase 5, D21/D22) — the numbered option card above the
// composer during intake, ported from the approved design. 1-N keyboard
// shortcuts speed through the script at a booth; the "อื่นๆ" row at the
// bottom expands into a free-text box for answers the script didn't
// anticipate. There is no Skip — the card is the only way to answer a step,
// and ClientWorkspace keeps the chat composer locked while it is on screen.
export default function IntakeChips({
  title,
  chips,
  onPick,
  onSubmitOther,
  disabled,
}: {
  title: string
  chips: Chip[]
  onPick: (chip: Chip) => void
  onSubmitOther: (text: string) => void
  disabled?: boolean
}) {
  const [otherOpen, setOtherOpen] = useState(false)
  const [otherText, setOtherText] = useState('')

  // A new step reuses this component — collapse the free-text row so the
  // next question opens on the numbered options, not a stale input.
  useEffect(() => {
    setOtherOpen(false)
    setOtherText('')
  }, [chips])

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

  function submitOther() {
    const text = otherText.trim()
    if (!text || disabled) return
    onSubmitOther(text)
    setOtherText('')
    setOtherOpen(false)
  }

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
      {otherOpen ? (
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
          <span
            style={{
              width: 22,
              height: 22,
              flex: 'none',
              borderRadius: 6,
              background: 'var(--surface)',
              color: 'var(--ink-3)',
              display: 'grid',
              placeItems: 'center',
            }}
          >
            <Ic.pencil size={12} strokeWidth={1.7} />
          </span>
          <input
            autoFocus
            value={otherText}
            disabled={disabled}
            onChange={(e) => setOtherText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                submitOther()
              } else if (e.key === 'Escape') {
                e.preventDefault()
                setOtherText('')
                setOtherOpen(false)
              }
            }}
            placeholder="พิมพ์คำตอบของคุณ…"
            style={{
              flex: 1,
              minWidth: 0,
              border: 'none',
              outline: 'none',
              background: 'transparent',
              fontSize: 14,
              fontFamily: 'var(--font-sans)',
              color: 'var(--ink)',
              height: 26,
            }}
          />
          <button
            disabled={disabled || !otherText.trim()}
            onClick={submitOther}
            aria-label="ส่งคำตอบ"
            style={{
              height: 26,
              padding: '0 11px',
              borderRadius: 7,
              border: '1px solid var(--line-2)',
              background: 'var(--surface)',
              color: 'var(--ink-2)',
              display: 'grid',
              placeItems: 'center',
              cursor: disabled || !otherText.trim() ? 'default' : 'pointer',
              opacity: disabled || !otherText.trim() ? 0.5 : 1,
            }}
          >
            <Ic.send size={12} strokeWidth={1.7} />
          </button>
        </div>
      ) : (
        <button
          disabled={disabled}
          onClick={() => setOtherOpen(true)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 13,
            width: '100%',
            textAlign: 'left',
            borderTop: '1px solid var(--line)',
            borderLeft: 'none',
            borderRight: 'none',
            borderBottom: 'none',
            background: 'var(--surface-2)',
            padding: '10px 16px',
            fontSize: 14,
            color: 'var(--ink-3)',
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
              background: 'var(--surface)',
              color: 'var(--ink-3)',
              display: 'grid',
              placeItems: 'center',
            }}
          >
            <Ic.pencil size={12} strokeWidth={1.7} />
          </span>
          <span style={{ flex: 1, lineHeight: 1.45 }}>อื่นๆ</span>
        </button>
      )}
    </div>
  )
}
