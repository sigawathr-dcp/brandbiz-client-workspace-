'use client'

import type { DraftPlan, PlanDiff } from './types'
import { moneyCol, percentDelta, percentShares } from './budgetTable'

// Client Workspaces (Phase 5, D21/D22) — the 4-part draft plan card, inline
// in the transcript. Every budget row's amount is computed server-side from
// rate_card_items (app/services/rate_card.py::price()) — the model only
// ever emitted an item code and a quantity, never a number. A code with no
// rate-card match shows in "needs_expert", not as an invented line.
export default function PlanDraftCard({
  status,
  plan,
  error,
  setupError,
  showDetail,
  saved,
  savedPlanId,
  onSave,
  saving,
  saveError,
  agentName,
  activePlan,
  revision,
}: {
  status: 'pending' | 'done' | 'error'
  plan?: DraftPlan
  error?: string
  // True iff the draft failed with HTTP 503 (workspace setup incomplete)
  // rather than a transient provider error — changes the copy below.
  setupError?: boolean
  showDetail?: boolean
  saved?: boolean
  savedPlanId?: string
  onSave: (mode: 'revise' | 'new') => void
  saving?: boolean
  // Set when a previous save attempt on THIS card failed — surfaced
  // instead of silently console.error'd (see ClientWorkspace.tsx::handleSavePlan).
  saveError?: string
  agentName: string
  // Set when this card is a chat-driven revision (POST /client/plan/revise)
  // rather than a fresh draft. Such a card is ALREADY committed as the next
  // version — the confirmation chip was the confirmation — so it renders the
  // version it became, what the client asked for, and what actually changed.
  // Pass `saved` alongside it; the footer's saved branch is what shows the
  // "View saved plan" link.
  revision?: { version: number; note: string; diff: PlanDiff }
  // Set when this seat already has a plan open (Task 5.12 — a seat can
  // hold several plans, so the client chooses each time rather than the
  // card silently deciding for them). When set, two actions are offered:
  // revise it into the next version, or save this draft as an independent
  // new plan. See ClientWorkspace.tsx::handleSavePlan.
  activePlan?: { title: string; nextVersion: number }
}) {
  if (status === 'pending') {
    return (
      <div style={{ marginTop: 14, fontSize: 12.5, color: 'var(--ink-3)' }}>
        Drafting your plan from the case library and rate card…
      </div>
    )
  }
  if (status === 'error' || !plan) {
    return (
      <div style={{ marginTop: 14, fontSize: 12.5, color: 'var(--ink-3)' }}>
        {setupError ? (
          // HTTP 503 — this workspace is missing its agent or its rate card.
          // No amount of retrying fixes that, and the old copy ("try again in
          // a moment") sent clients round the loop instead of to a human.
          <>
            {agentName} can&apos;t draft a plan for this workspace yet — it&apos;s still
            being set up. Please contact Brandbiz; retrying won&apos;t help.
          </>
        ) : (
          <>{agentName} couldn&apos;t draft a plan just now — try again in a moment.</>
        )}
        {showDetail && error && (
          <div style={{ marginTop: 4, fontSize: 11.5, fontFamily: 'monospace' }}>Reason: {error}</div>
        )}
      </div>
    )
  }

  const { budget } = plan
  // The budget table shows each row's share of the estimate, not its price —
  // lines + contingency, in that order, so the column sums to 100%.
  const shares = percentShares([...budget.lines.map((l) => l.amount), budget.contingency], budget.total)

  return (
    <div style={{ marginTop: 14, border: '1px solid var(--line-2)', borderRadius: 12, background: 'var(--surface)', overflow: 'hidden' }}>
      <div style={{ padding: '15px 16px 0' }}>
        <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--ink-3)', marginBottom: 7 }}>
          {revision ? `Revised · version ${revision.version}` : 'Draft plan · 4 parts'}
        </div>
        {revision && (
          <div
            style={{
              marginBottom: 11,
              padding: '9px 11px',
              borderRadius: 8,
              border: '1px solid var(--line-2)',
              background: 'var(--surface-2)',
            }}
          >
            <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginBottom: 4 }}>You asked for</div>
            <div style={{ fontSize: 13, lineHeight: 1.55, color: 'var(--ink-2)' }}>{revision.note}</div>
            <PlanChangeSummary diff={revision.diff} />
          </div>
        )}
        <div style={{ fontSize: 17, fontWeight: 600, letterSpacing: '-.01em', marginBottom: 12, color: 'var(--ink)' }}>{plan.title}</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 13, paddingBottom: 14 }}>
          <div>
            <div style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--accent)', marginBottom: 3 }}>1 · Core idea</div>
            <div style={{ fontSize: 13.5, lineHeight: 1.6, color: 'var(--ink-2)' }}>{plan.core_idea}</div>
          </div>
          <div>
            <div style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--accent)', marginBottom: 3 }}>2 · Analogous case</div>
            <div style={{ fontSize: 13.5, lineHeight: 1.6, color: 'var(--ink-2)' }}>{plan.analogous_case}</div>
          </div>
          <div>
            <div style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--accent)', marginBottom: 3 }}>3 · Adapted plan</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 11 }}>
              {plan.adapted_plan.map((item, i) => (
                <div key={i} className="client-plan-phase is-stacked">
                  <div className="client-plan-phase-period">{item.period}</div>
                  <div style={{ fontSize: 13.5, lineHeight: 1.55, color: 'var(--ink-2)' }}>{item.text}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div style={{ borderTop: '1px solid var(--line)', background: 'var(--surface-2)', padding: '14px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <div style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--accent)' }}>4 · Budget</div>
        </div>
        {budget.lines.length > 0 && (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', fontSize: 10.5, fontWeight: 600, color: 'var(--ink-3)', padding: '0 0 7px' }}>Line item</th>
                <th style={{ ...moneyCol, textAlign: 'right', fontSize: 10.5, fontWeight: 600, color: 'var(--ink-3)', padding: '0 0 7px 12px' }}>
                  Share
                </th>
              </tr>
            </thead>
            <tbody>
              {budget.lines.map((l, i) => (
                <tr key={l.code}>
                  <td style={{ padding: '7px 0', borderTop: '1px solid var(--line-2)', color: 'var(--ink-2)' }}>{l.label}</td>
                  <td style={{ ...moneyCol, padding: '7px 0 7px 12px', borderTop: '1px solid var(--line-2)', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                    {shares[i]}
                  </td>
                </tr>
              ))}
              <tr>
                <td style={{ padding: '7px 0', borderTop: '1px solid var(--line)', color: 'var(--ink-3)' }}>Contingency</td>
                <td style={{ ...moneyCol, padding: '7px 0 7px 12px', borderTop: '1px solid var(--line)', textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--ink-3)' }}>
                  {shares[budget.lines.length]}
                </td>
              </tr>
              <tr>
                <td style={{ padding: '9px 0 0', borderTop: '2px solid var(--ink)', fontWeight: 600 }}>Estimate</td>
                <td style={{ ...moneyCol, padding: '9px 0 0 12px', borderTop: '2px solid var(--ink)', textAlign: 'right', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                  100%
                </td>
              </tr>
            </tbody>
          </table>
        )}
        {budget.needs_expert.length > 0 && (
          <div style={{ marginTop: 10, fontSize: 11.5, color: 'var(--ink-3)' }}>
            {budget.needs_expert.length} line{budget.needs_expert.length > 1 ? 's' : ''} left for an expert to price — no rate-card row.
          </div>
        )}
        <div
          style={{
            marginTop: 12,
            display: 'flex',
            gap: 8,
            alignItems: 'flex-start',
            background: 'var(--surface)',
            border: '1px solid var(--line)',
            borderRadius: 8,
            padding: '9px 11px',
          }}
        >
          <div style={{ fontSize: 11.5, lineHeight: 1.55, color: 'var(--ink-2)' }}>
            Every line traces to a rate-card row. {agentName} can&apos;t price work that has no row —
            those are left for an expert. Final quote is confirmed by a human.
          </div>
        </div>
      </div>

      <div style={{ borderTop: '1px solid var(--line)', padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 8, background: 'var(--surface)' }}>
        {saved ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <a
              href={savedPlanId ? `/w/plans/${savedPlanId}` : '/w/plans'}
              style={{
                height: 36,
                padding: '0 15px',
                borderRadius: 8,
                border: '1px solid var(--line-2)',
                background: 'var(--surface)',
                color: 'var(--ink-2)',
                fontSize: 13.5,
                fontWeight: 500,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                whiteSpace: 'nowrap',
                flexShrink: 0,
                textDecoration: 'none',
              }}
            >
              View saved plan
            </a>
            <span style={{ flex: '1 1 140px', minWidth: 0, fontSize: 12, color: 'var(--ink-3)' }}>
              Keeps it past the 30-day message wipe, versioned.
            </span>
          </div>
        ) : (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <button
                onClick={() => onSave(activePlan ? 'revise' : 'new')}
                disabled={saving}
                style={{
                  height: 36,
                  padding: '0 15px',
                  borderRadius: 8,
                  border: 'none',
                  background: 'var(--accent)',
                  color: '#fff',
                  fontSize: 13.5,
                  fontWeight: 500,
                  cursor: saving ? 'default' : 'pointer',
                  opacity: saving ? 0.7 : 1,
                  maxWidth: '100%',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {saving
                  ? 'Saving…'
                  : activePlan
                    ? `Save as v${activePlan.nextVersion} of "${activePlan.title}"`
                    : 'Save as a plan'}
              </button>
              {activePlan && (
                <button
                  onClick={() => onSave('new')}
                  disabled={saving}
                  style={{
                    height: 36,
                    padding: '0 15px',
                    borderRadius: 8,
                    border: '1px solid var(--line-2)',
                    background: 'var(--surface)',
                    color: 'var(--ink-2)',
                    fontSize: 13.5,
                    fontWeight: 500,
                    cursor: saving ? 'default' : 'pointer',
                    opacity: saving ? 0.7 : 1,
                    whiteSpace: 'nowrap',
                    flexShrink: 0,
                  }}
                >
                  Save as a new plan
                </button>
              )}
              {!activePlan && (
                <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>Keeps it past the 30-day message wipe, versioned.</span>
              )}
            </div>
            {activePlan && (
              <div style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                Revising replaces what&apos;s on the plan document; a new plan sits beside it.
              </div>
            )}
            {saveError && (
              <div style={{ fontSize: 11.5, color: 'var(--danger, #b91c1c)' }}>{saveError}</div>
            )}
          </>
        )}
      </div>
    </div>
  )
}


const _FIELD_LABELS: Record<string, string> = {
  title: 'title',
  core_idea: 'core idea',
  analogous_case: 'analogous case',
  adapted_plan: 'the phases',
}

// What actually moved between the previous version and this one.
//
// This exists because a chat edit is a RE-DRAFT under an instruction, not a
// patch: asked to cut phase 4, the model can also reword the core idea. The
// diff is computed server-side (app/services/plan.py::diff_versions) and shown
// here so drift is visible rather than silent — and money is listed separately
// from prose, because a reworded sentence is cosmetic and a changed budget
// line is not.
function PlanChangeSummary({ diff }: { diff: PlanDiff }) {
  const { added, removed, qty_changed: qtyChanged, total_before: before, total_after: after } = diff.budget
  const budgetMoved = added.length > 0 || removed.length > 0 || qtyChanged.length > 0
  const narrative = diff.fields.map((f) => _FIELD_LABELS[f] ?? f)

  if (!budgetMoved && narrative.length === 0) {
    return (
      <div style={{ marginTop: 8, fontSize: 11.5, color: 'var(--ink-3)' }}>
        Nothing changed — this version is identical to the last one.
      </div>
    )
  }

  return (
    <div style={{ marginTop: 9, display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>What changed</div>
      {narrative.length > 0 && (
        <div style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>Rewritten: {narrative.join(', ')}</div>
      )}
      {added.map((l) => (
        <div key={`a-${l.code}`} style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>
          + {l.label ?? l.code}
          {l.amount ? '' : ' · needs an expert quote'}
        </div>
      ))}
      {removed.map((l) => (
        <div key={`r-${l.code}`} style={{ fontSize: 12.5, color: 'var(--ink-3)', textDecoration: 'line-through' }}>
          {l.label ?? l.code}
        </div>
      ))}
      {qtyChanged.map((l) => (
        <div key={`q-${l.code}`} style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>
          {l.label ?? l.code} · qty {l.from} → {l.to}
        </div>
      ))}
      {budgetMoved && before !== after && (
        <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink)' }}>
          Estimate {percentDelta(before, after) ?? 'changed'}
        </div>
      )}
    </div>
  )
}
