'use client'

import { useEffect, useState } from 'react'

interface SharedPlan {
  id: string
  title: string
  status: string
  version: number
  core_idea: string
  analogous_case: string
  adapted_plan: { period: string; text: string }[]
  budget: {
    lines: { code: string; label: string; amount: string }[]
    contingency: string
    total: string
    currency: string
    needs_expert: { code: string; qty: string }[]
  } | null
  created_at: string
}

// Client Workspaces (Phase 6, D21/D22) — the unauthenticated share-link
// view (GET /public/plans/{token}). Read-only, no chat, no profile — just
// the plan, exactly as the plan called for. Reachable with no cookie at
// all (see middleware.ts's /p/ exemption); the token itself is the
// credential.
export default function SharedPlanView({ token }: { token: string }) {
  const [plan, setPlan] = useState<SharedPlan | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    fetch(`/api/public/plans/${token}`)
      .then((r) => {
        if (!r.ok) throw new Error()
        return r.json()
      })
      .then(setPlan)
      .catch(() => setError(true))
  }, [token])

  if (error) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
        <div style={{ fontSize: 14, color: 'var(--ink-2)' }}>This plan link is not valid.</div>
      </div>
    )
  }
  if (!plan) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
        <div style={{ fontSize: 13, color: 'var(--ink-3)' }}>Loading…</div>
      </div>
    )
  }

  const { budget } = plan

  return (
    <div className="client-paper-wrap" style={{ minHeight: '100vh', background: 'var(--bg)' }}>
      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <div className="client-paper" style={{ width: 720, maxWidth: '92vw', background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 14, boxShadow: 'var(--shadow-1)', boxSizing: 'border-box' }}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '.09em', textTransform: 'uppercase', color: 'var(--ink-3)', marginBottom: 12 }}>
            Brandbiz · shared plan
          </div>
          <div style={{ fontSize: 28, lineHeight: 1.2, fontWeight: 600, letterSpacing: '-.02em', marginBottom: 10, color: 'var(--ink)' }}>
            {plan.title}
          </div>
          <div style={{ fontSize: 14, color: 'var(--ink-3)', marginBottom: 26, paddingBottom: 22, borderBottom: '1px solid var(--line)' }}>
            {plan.status === 'draft' ? 'Draft · awaiting expert review' : plan.status} · shared {new Date(plan.created_at).toLocaleDateString()}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            <div>
              <div style={{ fontSize: 11.5, fontWeight: 600, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: 7 }}>Core idea</div>
              <div style={{ fontSize: 15, lineHeight: 1.68, color: 'var(--ink-2)' }}>{plan.core_idea}</div>
            </div>
            <div>
              <div style={{ fontSize: 11.5, fontWeight: 600, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: 7 }}>Analogous case</div>
              <div style={{ fontSize: 15, lineHeight: 1.68, color: 'var(--ink-2)' }}>{plan.analogous_case}</div>
            </div>
            <div>
              <div style={{ fontSize: 11.5, fontWeight: 600, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: 7 }}>Adapted plan</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 11 }}>
                {plan.adapted_plan.map((item, i) => (
                  <div key={i} style={{ display: 'flex', gap: 12 }}>
                    <div style={{ width: 54, flex: 'none', fontSize: 12, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)', paddingTop: 2 }}>{item.period}</div>
                    <div style={{ fontSize: 14.5, lineHeight: 1.6, color: 'var(--ink-2)' }}>{item.text}</div>
                  </div>
                ))}
              </div>
            </div>
            {budget && (
              <div>
                <div style={{ fontSize: 11.5, fontWeight: 600, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: 10 }}>Budget</div>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                  <tbody>
                    {budget.lines.map((l) => (
                      <tr key={l.code}>
                        <td style={{ padding: '9px 0', borderTop: '1px solid var(--line)', color: 'var(--ink-2)' }}>{l.label}</td>
                        <td style={{ padding: '9px 0 9px 14px', borderTop: '1px solid var(--line)', textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 13 }}>{l.amount}</td>
                      </tr>
                    ))}
                    <tr>
                      <td style={{ padding: '12px 0 0', borderTop: '2px solid var(--ink)', fontWeight: 600, fontSize: 15 }}>Estimate</td>
                      <td style={{ padding: '12px 0 0 14px', borderTop: '2px solid var(--ink)', textAlign: 'right', fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 15 }}>
                        {budget.currency} {budget.total}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
