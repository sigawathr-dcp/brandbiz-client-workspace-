'use client'

import { Ic } from '../ui/Icon'

// Client Workspaces redesign (PLAN.md Task 5.10) — "insight earned" card
// rendered above an AI turn's text when the answer that produced this turn
// carried an insight (see app/services/client_intake.py's IntakeStep.insight
// and POST /client/intake/answer's response).
export default function InsightCallout({ text }: { text: string }) {
  return (
    <div
      style={{
        marginBottom: 12,
        display: 'flex',
        gap: 11,
        alignItems: 'flex-start',
        background: 'var(--surface)',
        border: '1px solid var(--line-2)',
        borderLeft: '3px solid var(--accent)',
        borderRadius: 10,
        padding: '11px 13px',
        boxShadow: 'var(--shadow-1)',
        animation: 'popIn .3s ease',
      }}
    >
      <span style={{ flex: 'none', marginTop: 2, color: 'var(--accent)' }}>
        <Ic.spark size={15} />
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 10.5,
            fontWeight: 600,
            letterSpacing: '.07em',
            textTransform: 'uppercase',
            color: 'var(--accent)',
            marginBottom: 3,
          }}
        >
          Insight earned
        </div>
        <div style={{ fontSize: 13.5, lineHeight: 1.6, color: 'var(--ink-2)' }}>{text}</div>
      </div>
    </div>
  )
}
