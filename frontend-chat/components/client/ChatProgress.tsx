'use client'

import type { Journey } from './journey'

// Client Workspaces redesign (PLAN.md Task 5.10) — the chat header's
// right-hand progress block: "{answered}/{total}" + a status hint, above a
// row of pips (one per intake question). Purely a view over journey.ts.
export default function ChatProgress({ journey }: { journey: Journey }) {
  return (
    <div className="client-chat-progress" style={{ flex: 'none', width: 250 }}>
      <div className="client-chat-hint" style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 4 }}>
        <span style={{ fontSize: 11, fontWeight: 600, fontFamily: 'var(--font-mono)', color: 'var(--ink-2)' }}>
          {journey.answered}/{journey.totalSteps}
        </span>
        <span style={{ fontSize: 11, color: 'var(--ink-3)', flex: 1, textAlign: 'right' }}>{journey.headerHint}</span>
      </div>
      <div style={{ display: 'flex', gap: 3 }}>
        {journey.pips.map((p, i) => (
          <div
            key={i}
            style={{
              flex: 1,
              height: 5,
              borderRadius: 3,
              transition: 'background .3s ease',
              background: p === 'done' ? 'var(--t1)' : p === 'current' ? 'var(--accent)' : 'var(--line)',
            }}
          />
        ))}
      </div>
    </div>
  )
}
