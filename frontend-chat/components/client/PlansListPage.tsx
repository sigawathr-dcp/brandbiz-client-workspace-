'use client'

import { useEffect, useState } from 'react'
import type { SavedPlan } from './types'

// Client Workspaces (Phase 5, D21/D22) — "My plans" list. Each plan is a
// durable artifact (Plan row + PlanVersion snapshot) that survives the
// 30-day messages.content_* retention wipe (D14) — see app/models/plan.py.
export default function PlansListPage() {
  const [plans, setPlans] = useState<SavedPlan[] | null>(null)

  useEffect(() => {
    fetch('/api/client/plans', { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : []))
      .then(setPlans)
      .catch(() => setPlans([]))
  }, [])

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)' }}>
      <div className="client-plans-topbar" style={{ borderBottom: '1px solid var(--line)', background: 'var(--surface)', display: 'flex', alignItems: 'center', gap: 12 }}>
        <a href="/w" style={{ fontSize: 13, color: 'var(--ink-2)', textDecoration: 'none' }}>
          ← Back to chat
        </a>
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>My plans</div>
      </div>
      <div className="client-plans-content" style={{ maxWidth: 720, margin: '0 auto' }}>
        {plans === null && <div style={{ fontSize: 13, color: 'var(--ink-3)' }}>Loading…</div>}
        {plans !== null && plans.length === 0 && (
          <div style={{ fontSize: 13, color: 'var(--ink-3)' }}>
            No plans saved yet — chat with your Brandbiz strategist and choose &quot;Save as a plan&quot; once one is drafted.
          </div>
        )}
        {plans !== null && plans.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {plans.map((p) => (
              <a
                key={p.id}
                href={`/w/plans/${p.id}`}
                style={{
                  display: 'block',
                  border: '1px solid var(--line)',
                  borderRadius: 12,
                  background: 'var(--surface)',
                  padding: '14px 16px',
                  textDecoration: 'none',
                  boxShadow: 'var(--shadow-1)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <div style={{ fontSize: 14.5, fontWeight: 600, color: 'var(--ink)' }}>{p.title}</div>
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 500,
                      color: 'var(--ink-2)',
                      background: 'var(--surface-2)',
                      border: '1px solid var(--line)',
                      borderRadius: 99,
                      padding: '2px 8px',
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    v{p.version} · {p.status}
                  </span>
                </div>
                <div style={{ fontSize: 13, color: 'var(--ink-3)', lineHeight: 1.5 }}>{p.core_idea}</div>
                {p.budget && (
                  <div style={{ marginTop: 8, fontSize: 12, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>
                    {p.budget.currency} {p.budget.total}
                  </div>
                )}
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
