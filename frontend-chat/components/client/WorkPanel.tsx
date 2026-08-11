'use client'

import { Ic } from '../ui/Icon'
import CaseMatchCards from './CaseMatchCards'
import type { CasesResult, IntakeField, ResearchResult } from './types'

export type WorkTab = 'profile' | 'research' | 'cases'

// Client Workspaces (Phase 5, D21/D22) — the right-hand work panel: Profile
// fills in live as intake answers land, Research/Cases show once those
// steps have run. Ported layout from the approved design; data is real
// (GET /client/bootstrap for fields, POST /client/research + /client/cases
// for the other two tabs).
export default function WorkPanel({
  tab,
  onTab,
  fields,
  intakeFields,
  agentName,
  research,
  researchStatus,
  cases,
  casesStatus,
  navigable,
}: {
  tab: WorkTab
  onTab: (t: WorkTab) => void
  fields: Record<string, string>
  // Ordered field manifest from GET /client/bootstrap — the backend intake
  // script owns the keys, labels, and order; this component never keeps a
  // local copy that could desync.
  intakeFields: IntakeField[]
  agentName: string
  research: ResearchResult | null
  researchStatus: 'idle' | 'pending' | 'done' | 'error'
  cases: CasesResult | null
  casesStatus: 'idle' | 'pending' | 'done' | 'error'
  // From journey.ts's Journey.navigable — the single source of truth for
  // "is this chapter reachable" (also drives NavRail's chapter rows), so
  // this tab bar doesn't recompute its own lock ternary.
  navigable: { market: boolean; cases: boolean }
}) {
  const filled = intakeFields.filter((f) => fields[f.key]).length
  const pct = intakeFields.length > 0 ? Math.round((filled / intakeFields.length) * 100) : 0

  const researchLocked = !navigable.market
  const casesLocked = !navigable.cases

  const tabBtn = (t: WorkTab, label: string, locked: boolean) => (
    <button
      onClick={() => {
        if (!locked) onTab(t)
      }}
      disabled={locked}
      style={{
        flex: 1,
        height: 32,
        borderRadius: 8,
        border: 'none',
        fontSize: 12.5,
        fontWeight: 500,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 5,
        cursor: locked ? 'default' : 'pointer',
        background: !locked && tab === t ? 'var(--accent-weak)' : 'transparent',
        color: locked ? 'var(--ink-4)' : tab === t ? 'var(--accent)' : 'var(--ink-3)',
      }}
    >
      {locked && <Ic.lock size={11} strokeWidth={1.7} />}
      {label}
    </button>
  )

  return (
    <div
      style={{
        borderLeft: '1px solid var(--line)',
        background: 'var(--surface)',
        display: 'flex',
        flexDirection: 'column',
        minWidth: 0,
        height: '100%',
      }}
    >
      <div style={{ flex: 'none', display: 'flex', gap: 2, padding: '10px 12px', borderBottom: '1px solid var(--line)' }}>
        {tabBtn('profile', 'Profile', false)}
        {tabBtn('research', 'Research', researchLocked)}
        {tabBtn('cases', 'Cases', casesLocked)}
      </div>
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '16px 16px 20px' }}>
        {tab === 'profile' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 3, color: 'var(--ink)' }}>
                Company profile
              </div>
              <div style={{ fontSize: 11.5, lineHeight: 1.5, color: 'var(--ink-3)' }}>
                {filled} of {intakeFields.length} filled
              </div>
            </div>
            <div style={{ height: 4, borderRadius: 2, background: 'var(--surface-sunk)', overflow: 'hidden' }}>
              <div style={{ height: '100%', background: 'var(--accent)', width: `${pct}%`, transition: 'width .5s ease' }} />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {intakeFields.map((f) => (
                <div key={f.key} style={{ display: 'flex', gap: 10, padding: '10px 0', borderBottom: '1px solid var(--line)', alignItems: 'flex-start' }}>
                  <div style={{ width: 15, flex: 'none', paddingTop: 2 }}>
                    {fields[f.key] && (
                      <span style={{ display: 'inline-flex', color: 'var(--t1)', animation: 'popIn .3s ease' }}>
                        <Ic.check size={13} strokeWidth={1.7} />
                      </span>
                    )}
                  </div>
                  <div style={{ width: 84, flex: 'none', fontSize: 11.5, color: 'var(--ink-3)', paddingTop: 1 }}>
                    {f.label}
                  </div>
                  <div style={{ flex: 1, minWidth: 0, fontSize: 13, lineHeight: 1.5, color: fields[f.key] ? 'var(--ink)' : 'var(--ink-4)' }}>
                    {fields[f.key] || 'not asked yet'}
                  </div>
                </div>
              ))}
            </div>
            <div
              style={{
                display: 'flex',
                gap: 8,
                alignItems: 'flex-start',
                background: 'var(--surface-2)',
                borderRadius: 9,
                padding: '10px 11px',
              }}
            >
              <span style={{ flex: 'none', marginTop: 1, color: 'var(--t1)' }}>
                <Ic.shield size={15} />
              </span>
              <div style={{ fontSize: 11.5, lineHeight: 1.55, color: 'var(--ink-2)' }}>
                This profile is visible only to your workspace and the expert you hand off to.
              </div>
            </div>
          </div>
        )}

        {tab === 'research' && (
          <div>
            {researchStatus === 'idle' && (
              <div style={{ padding: '44px 8px', textAlign: 'center' }}>
                <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--ink-2)', marginBottom: 5 }}>No scan yet</div>
                <div style={{ fontSize: 12, lineHeight: 1.55, color: 'var(--ink-3)' }}>
                  {agentName} runs the external market scan once the intake questions are answered.
                </div>
              </div>
            )}
            {researchStatus === 'pending' && (
              <div style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>Searching · reading · synthesizing…</div>
            )}
            {researchStatus === 'error' && (
              <div style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>Market research is temporarily unavailable.</div>
            )}
            {researchStatus === 'done' && research && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 13 }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 3, color: 'var(--ink)' }}>
                    Market scan
                  </div>
                  <div style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                    {research.findings.length} finding{research.findings.length === 1 ? '' : 's'} ·{' '}
                    {research.citations.length} source{research.citations.length === 1 ? '' : 's'} cited
                  </div>
                </div>
                {research.findings.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {research.findings.map((f, i) => (
                      <div
                        key={i}
                        style={{
                          fontSize: 13,
                          lineHeight: 1.55,
                          color: 'var(--ink-2)',
                          border: '1px solid var(--line)',
                          borderRadius: 10,
                          padding: '10px 12px',
                        }}
                      >
                        {f.text}
                      </div>
                    ))}
                  </div>
                )}
                <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--ink-3)' }}>
                  Sources
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                  {research.citations.map((c) => (
                    <div
                      key={c.index}
                      style={{
                        display: 'flex',
                        gap: 9,
                        alignItems: 'center',
                        border: '1px solid var(--line)',
                        borderRadius: 8,
                        padding: '8px 10px',
                      }}
                    >
                      <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--ink-4)' }}>{c.index}</span>
                      <div style={{ fontSize: 12, color: 'var(--ink-2)', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {c.source}
                      </div>
                    </div>
                  ))}
                  {research.citations.length === 0 && (
                    <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>No citations returned for this scan.</div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {tab === 'cases' && (
          <div>
            {casesStatus === 'idle' && (
              <div style={{ padding: '44px 8px', textAlign: 'center' }}>
                <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--ink-2)', marginBottom: 5 }}>Nothing matched yet</div>
                <div style={{ fontSize: 12, lineHeight: 1.55, color: 'var(--ink-3)' }}>
                  Matches appear once there&apos;s a profile and a market scan to score against.
                </div>
              </div>
            )}
            {(casesStatus === 'pending' || casesStatus === 'error' || casesStatus === 'done') && (
              <CaseMatchCards status={casesStatus} result={cases ?? undefined} />
            )}
            {casesStatus === 'done' && (
              <div
                style={{
                  marginTop: 12,
                  display: 'flex',
                  gap: 8,
                  alignItems: 'flex-start',
                  background: 'var(--surface-2)',
                  borderRadius: 9,
                  padding: '10px 11px',
                }}
              >
                <div style={{ fontSize: 11.5, lineHeight: 1.55, color: 'var(--ink-2)' }}>
                  Case studies are read-only reference. Nothing you enter is added to the library or shown to another client.
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
