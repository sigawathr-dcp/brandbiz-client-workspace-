'use client'

import { Ic } from '../ui/Icon'

// Client Workspaces redesign (PLAN.md Task 5.10) — the full-width "chapter
// complete" card emitted into the thread alongside a who:'sys' Turn. See
// journey.ts for the four chapters this marks progress through.
export default function MilestoneTurn({ title, sub }: { title: string; sub: string }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        width: '100%',
        background: 'var(--surface)',
        border: '1px solid var(--t1)',
        borderRadius: 12,
        padding: '12px 15px',
        boxShadow: 'var(--shadow-1)',
        animation: 'popIn .34s ease',
      }}
    >
      <div
        style={{
          width: 28,
          height: 28,
          flex: 'none',
          borderRadius: '50%',
          background: 'var(--t1-bg)',
          display: 'grid',
          placeItems: 'center',
          color: 'var(--t1)',
        }}
      >
        <Ic.check size={15} strokeWidth={2} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink)' }}>{title}</div>
        <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 1 }}>{sub}</div>
      </div>
    </div>
  )
}
