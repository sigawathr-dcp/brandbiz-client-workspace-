'use client'

import { useEffect, useState } from 'react'
import LeadModal from './LeadModal'
import PlanRating from './PlanRating'
import PlanSideRail from './PlanSideRail'
import { money, moneyCol } from './budgetTable'
import type { PlanVersionBody, SavedPlan } from './types'

// Client Workspaces (Phase 5, D21/D22) — the plan document view: 720px
// "paper", the same 4-part shape as PlanDraftCard but as a standalone,
// nameable artifact. Print stylesheet (Phase 6 export) targets this exact
// markup — see app/(client)/w/plans/[id]/print/page.tsx.
export default function PlanDocument({ planId }: { planId: string }) {
  const [plan, setPlan] = useState<SavedPlan | null>(null)
  const [error, setError] = useState(false)
  const [leadOpen, setLeadOpen] = useState(false)
  // Task 5.12 — which version the paper currently renders. null = "the
  // plan's current version" (no extra fetch needed — `plan` already has
  // it); a number means the client clicked an older row in the Versions
  // rail and `versionBody` below holds that version's own snapshot.
  const [viewingVersion, setViewingVersion] = useState<number | null>(null)
  const [versionBody, setVersionBody] = useState<PlanVersionBody | null>(null)
  const [versionError, setVersionError] = useState(false)

  useEffect(() => {
    fetch(`/api/client/plans/${planId}`, { credentials: 'include' })
      .then((r) => {
        if (!r.ok) throw new Error()
        return r.json()
      })
      .then(setPlan)
      .catch(() => setError(true))
  }, [planId])

  const isViewingOld = plan !== null && viewingVersion !== null && viewingVersion !== plan.version

  useEffect(() => {
    if (!isViewingOld || viewingVersion === null) {
      setVersionBody(null)
      return
    }
    let cancelled = false
    setVersionError(false)
    fetch(`/api/client/plans/${planId}/versions/${viewingVersion}`, { credentials: 'include' })
      .then((r) => {
        if (!r.ok) throw new Error()
        return r.json()
      })
      .then((data: PlanVersionBody) => {
        if (!cancelled) setVersionBody(data)
      })
      .catch(() => {
        if (!cancelled) setVersionError(true)
      })
    return () => {
      cancelled = true
    }
  }, [planId, viewingVersion, isViewingOld])

  if (error) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
        <div style={{ fontSize: 14, color: 'var(--ink-2)' }}>This plan could not be found.</div>
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

  // Task 5.12 — when viewing an older version, render its own snapshot
  // (title/core_idea/analogous_case/adapted_plan/budget) instead of the
  // plan's current body. Falls back to the current plan while that
  // version's fetch is still in flight or failed, rather than a blank paper.
  const showingVersion = isViewingOld && versionBody ? versionBody : plan
  const budget = showingVersion.budget
  const agentName = plan.agent_name ?? 'น้องภูมิ'

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)' }}>
      <div className="no-print client-plandoc-topbar" style={{ borderBottom: '1px solid var(--line)', background: 'var(--surface)', display: 'flex', alignItems: 'center', gap: 12 }}>
        <a href="/w/plans" style={{ fontSize: 13, color: 'var(--ink-2)', textDecoration: 'none' }}>
          ← My plans
        </a>
        <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink)' }}>{showingVersion.title}</div>
        <span style={{ fontSize: 11, fontWeight: 500, color: 'var(--ink-2)', background: 'var(--surface-2)', border: '1px solid var(--line)', borderRadius: 99, padding: '2px 8px', fontFamily: 'var(--font-mono)' }}>
          v{isViewingOld ? viewingVersion : plan.version} · {plan.status}
        </span>
        <div style={{ flex: 1 }} />
        {!isViewingOld && (
        <>
        <button
          onClick={async () => {
            const res = await fetch(`/api/client/plans/${planId}/share`, { method: 'POST', credentials: 'include' })
            if (!res.ok) return
            const data = await res.json()
            const url = `${window.location.origin}${data.share_path}`
            try {
              await navigator.clipboard.writeText(url)
              window.alert(`Share link copied:\n${url}`)
            } catch {
              window.prompt('Share link (copy manually):', url)
            }
          }}
          style={{ fontSize: 13, color: 'var(--ink-2)', border: '1px solid var(--line-2)', borderRadius: 7, padding: '6px 11px', background: 'var(--surface)', cursor: 'pointer' }}
        >
          Share
        </button>
        <a
          href={`/w/plans/${planId}/print`}
          style={{ fontSize: 13, color: 'var(--ink-2)', border: '1px solid var(--line-2)', borderRadius: 7, padding: '6px 11px', textDecoration: 'none' }}
        >
          Export PDF
        </a>
        </>
        )}
      </div>

      {isViewingOld && (
        <div
          className="no-print"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '9px 22px',
            background: 'var(--warn-weak, #fef3c7)',
            color: 'var(--warn, #b45309)',
            fontSize: 13,
          }}
        >
          <span>
            {versionError
              ? "Couldn't load this version — showing the current plan instead."
              : `Viewing v${viewingVersion}${versionBody ? ` · saved ${new Date(versionBody.created_at).toLocaleString()}` : ''}`}
          </span>
          <button
            onClick={() => setViewingVersion(null)}
            style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
          >
            Back to latest (v{plan.version}) →
          </button>
        </div>
      )}

      <div className="client-paper-wrap" style={{ display: 'flex', justifyContent: 'center' }}>
        <div className="client-plandoc-grid" style={{ width: 1062, maxWidth: '100%', display: 'grid', gap: 22, alignItems: 'start' }}>
        <div className="client-paper" style={{ width: '100%', maxWidth: 720, background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 14, boxShadow: 'var(--shadow-1)', boxSizing: 'border-box' }}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '.09em', textTransform: 'uppercase', color: 'var(--ink-3)', marginBottom: 12 }}>
            Brandbiz · draft plan
          </div>
          <div style={{ fontSize: 31, lineHeight: 1.2, fontWeight: 600, letterSpacing: '-.02em', marginBottom: 10, color: 'var(--ink)' }}>
            {showingVersion.title}
          </div>
          <div style={{ fontSize: 14, color: 'var(--ink-3)', marginBottom: 26, paddingBottom: 22, borderBottom: '1px solid var(--line)' }}>
            {isViewingOld && versionBody
              ? `Saved ${new Date(versionBody.created_at).toLocaleDateString()}`
              : `Drafted by ${agentName} · ${new Date(plan.created_at).toLocaleDateString()} · ${plan.status === 'draft' ? 'awaiting expert review' : plan.status}`}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            <div>
              <div style={{ fontSize: 11.5, fontWeight: 600, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: 7 }}>
                Core idea
              </div>
              <div style={{ fontSize: 15, lineHeight: 1.68, color: 'var(--ink-2)' }}>{showingVersion.core_idea}</div>
            </div>
            <div>
              <div style={{ fontSize: 11.5, fontWeight: 600, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: 7 }}>
                Analogous case
              </div>
              <div style={{ fontSize: 15, lineHeight: 1.68, color: 'var(--ink-2)' }}>{showingVersion.analogous_case}</div>
            </div>
            <div>
              <div style={{ fontSize: 11.5, fontWeight: 600, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: 7 }}>
                Adapted plan
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 11 }}>
                {showingVersion.adapted_plan.map((item, i) => (
                  <div key={i} className="client-plan-phase">
                    <div className="client-plan-phase-period">{item.period}</div>
                    <div style={{ fontSize: 14.5, lineHeight: 1.6, color: 'var(--ink-2)' }}>{item.text}</div>
                  </div>
                ))}
              </div>
            </div>

            {budget && (
              <div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10 }}>
                  <div style={{ fontSize: 11.5, fontWeight: 600, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--accent)' }}>Budget</div>
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                  <tbody>
                    {budget.lines.map((l) => (
                      <tr key={l.code}>
                        <td style={{ padding: '9px 0', borderTop: '1px solid var(--line)', color: 'var(--ink-2)' }}>{l.label}</td>
                        <td style={{ ...moneyCol, padding: '9px 0 9px 14px', borderTop: '1px solid var(--line)', textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 13 }}>
                          {money(l.amount)}
                        </td>
                      </tr>
                    ))}
                    <tr>
                      <td style={{ padding: '9px 0', borderTop: '1px solid var(--line)', color: 'var(--ink-3)' }}>Contingency</td>
                      <td style={{ ...moneyCol, padding: '9px 0 9px 14px', borderTop: '1px solid var(--line)', textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--ink-3)' }}>
                        {money(budget.contingency)}
                      </td>
                    </tr>
                    <tr>
                      <td style={{ padding: '12px 0 0', borderTop: '2px solid var(--ink)', fontWeight: 600, fontSize: 15 }}>Estimate</td>
                      <td style={{ ...moneyCol, padding: '12px 0 0 14px', borderTop: '2px solid var(--ink)', textAlign: 'right', fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 15 }}>
                        {budget.currency} {money(budget.total)}
                      </td>
                    </tr>
                  </tbody>
                </table>
                {budget.needs_expert.length > 0 && (
                  <div style={{ marginTop: 10, fontSize: 12, color: 'var(--ink-3)' }}>
                    {budget.needs_expert.length} item(s) left for an expert to price.
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Rating/CTA/share/export all act on the plan's CURRENT body, and
              none of them take a version parameter — an old snapshot is
              read-only, not something to rate or hand off from. */}
          {!isViewingOld && (
            <>
              <div className="client-plandoc-cta" style={{ marginTop: 32, borderTop: '1px solid var(--line)', paddingTop: 24 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4, color: 'var(--ink)' }}>Want a real quote?</div>
                  <div style={{ fontSize: 13.5, lineHeight: 1.55, color: 'var(--ink-3)' }}>
                    A Brandbiz strategist reviews this plan with you and confirms the numbers. No cost, no commitment.
                  </div>
                </div>
                <button
                  onClick={() => setLeadOpen(true)}
                  className="no-print"
                  style={{ flex: 'none', height: 44, padding: '0 20px', borderRadius: 9, border: 'none', background: 'var(--accent)', color: '#fff', fontSize: 14.5, fontWeight: 500, cursor: 'pointer', boxShadow: 'var(--shadow-2)' }}
                >
                  Talk to an expert
                </button>
              </div>

              <div
                className="no-print"
                style={{
                  marginTop: 26,
                  border: '1px solid var(--line)',
                  borderRadius: 12,
                  background: 'var(--surface-2)',
                  padding: '20px 22px',
                }}
              >
                <PlanRating planId={planId} initial={plan.rating} agentName={agentName} />
              </div>
            </>
          )}
        </div>

        <PlanSideRail
          plan={plan}
          viewingVersion={isViewingOld ? viewingVersion! : plan.version}
          viewingProvenance={isViewingOld ? (versionBody?.provenance ?? null) : plan.provenance}
          onSelectVersion={setViewingVersion}
        />
        </div>
      </div>

      {leadOpen && <LeadModal planId={planId} onClose={() => setLeadOpen(false)} />}
    </div>
  )
}
