'use client'

import { useState } from 'react'
import { MarkdownContent } from '../ui/Markdown'
import { Ic } from '../ui/Icon'
import CaseMatchCards from './CaseMatchCards'
import { findingsToMarkdown } from './researchMarkdown'
import type { CasesResult, IntakeField, ResearchResult } from './types'

export type WorkTab = 'profile' | 'research' | 'cases'

// One pending correction for a single intake field — mirrors
// IntakeFieldEditIn on the backend (app/routers/client.py). `label` is
// display-only (what the row shows while unsaved); it never goes over the
// wire — the server resolves the real value from option_index/free_text
// exactly like the original intake answer did (client_intake.resolve_answer).
interface PendingEdit {
  option_index?: number
  // Multi-select fields (IntakeField.multi_select) collect every toggled
  // chip here instead of replacing option_index on each tap.
  option_indices?: number[]
  free_text?: string
  label: string
}

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
  onSaveProfile,
  savingProfile,
  profileError,
  intakeStep,
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
  // Task 5.11 — editable company profile. Submits corrections to already-
  // answered fields; PATCH /client/intake/fields is the only write path
  // (see ClientWorkspace.tsx::handleSaveProfile for the resubmit cascade
  // this triggers once intake is complete).
  // Resolves to whether the server accepted the edit. A `false` keeps the
  // pending chips and edit mode on screen so the client can see what failed
  // and retry, instead of the correction silently disappearing.
  onSaveProfile: (
    updates: { field: string; option_index?: number; option_indices?: number[]; free_text?: string }[]
  ) => Promise<boolean>
  savingProfile: boolean
  profileError: string
  // engagement_steps.progress_current for the interview step, straight from
  // GET /client/bootstrap. The backend rejects an edit to any question the
  // client hasn't reached (idx >= progress_current — app/routers/client.py::
  // edit_intake_fields), so the UI gates on the same number rather than
  // re-deriving its own rule that can disagree with it.
  intakeStep: number
}) {
  const filled = intakeFields.filter((f) => fields[f.key]).length
  const pct = intakeFields.length > 0 ? Math.round((filled / intakeFields.length) * 100) : 0

  const [editMode, setEditMode] = useState(false)
  const [pending, setPending] = useState<Record<string, PendingEdit>>({})

  function pickChip(field: IntakeField, option: { index: number; label: string }) {
    if (field.multi_select) {
      // Toggle the chip in/out of the pending set; the row's preview label
      // joins the picked labels the same way the server will ("; ").
      setPending((prev) => {
        const current = prev[field.key]?.option_indices ?? []
        const next = current.includes(option.index)
          ? current.filter((i) => i !== option.index)
          : [...current, option.index].sort((a, b) => a - b)
        if (next.length === 0) {
          const { [field.key]: _dropped, ...rest } = prev
          return rest
        }
        const label = field.options
          .filter((o) => next.includes(o.index))
          .map((o) => o.label)
          .join('; ')
        return { ...prev, [field.key]: { option_indices: next, label } }
      })
      return
    }
    setPending((prev) => ({ ...prev, [field.key]: { option_index: option.index, label: option.label } }))
  }
  function typeFreeText(fieldKey: string, text: string) {
    setPending((prev) => ({ ...prev, [fieldKey]: { free_text: text, label: text } }))
  }
  function cancelEdit() {
    setPending({})
    setEditMode(false)
  }
  async function saveEdit() {
    const updates = Object.entries(pending)
      .filter(
        ([, v]) =>
          v.option_index !== undefined || (v.option_indices?.length ?? 0) > 0 || (v.free_text ?? '').trim()
      )
      .map(([field, v]) => ({
        field,
        option_index: v.option_index,
        option_indices: v.option_indices,
        free_text: v.free_text,
      }))
    const ok = await onSaveProfile(updates)
    if (!ok) return // keep `pending` and edit mode — profileError explains why
    setPending({})
    setEditMode(false)
  }

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
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 3, color: 'var(--ink)' }}>
                  Company profile
                </div>
                <div style={{ fontSize: 11.5, lineHeight: 1.5, color: 'var(--ink-3)' }}>
                  {filled} of {intakeFields.length} filled
                </div>
              </div>
              {!editMode && filled > 0 && (
                <button
                  onClick={() => setEditMode(true)}
                  style={{
                    flex: 'none',
                    height: 26,
                    padding: '0 10px',
                    borderRadius: 7,
                    border: '1px solid var(--line-2)',
                    background: 'var(--surface)',
                    color: 'var(--ink-2)',
                    fontSize: 11.5,
                    fontWeight: 500,
                    cursor: 'pointer',
                  }}
                >
                  Edit
                </button>
              )}
            </div>
            <div style={{ height: 4, borderRadius: 2, background: 'var(--surface-sunk)', overflow: 'hidden' }}>
              <div style={{ height: '100%', background: 'var(--accent)', width: `${pct}%`, transition: 'width .5s ease' }} />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {intakeFields.map((f, idx) => {
                // The backend's own rule, verbatim: a question is correctable
                // exactly when the client has already reached it
                // (idx < progress_current — app/routers/client.py::
                // edit_intake_fields). This used to be re-derived here as
                // `!!fields[f.key]`, which can disagree with the server and
                // offer chips the PATCH then rejects with a 400.
                const answered = idx < intakeStep
                const edit = pending[f.key]
                return (
                  <div key={f.key} style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '10px 0', borderBottom: '1px solid var(--line)' }}>
                    <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                      <div style={{ width: 15, flex: 'none', paddingTop: 2 }}>
                        {answered && (
                          <span style={{ display: 'inline-flex', color: 'var(--t1)', animation: 'popIn .3s ease' }}>
                            <Ic.check size={13} strokeWidth={1.7} />
                          </span>
                        )}
                      </div>
                      <div style={{ width: 84, flex: 'none', fontSize: 11.5, color: 'var(--ink-3)', paddingTop: 1 }}>
                        {f.label}
                      </div>
                      <div style={{ flex: 1, minWidth: 0, fontSize: 13, lineHeight: 1.5, color: answered ? 'var(--ink)' : 'var(--ink-4)' }}>
                        {edit ? edit.label : fields[f.key] || 'not asked yet'}
                      </div>
                    </div>
                    {editMode && answered && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-start', gap: 6, paddingLeft: 25 }}>
                        {f.options.map((o) => {
                          const picked =
                            edit?.option_index === o.index ||
                            (edit?.option_indices?.includes(o.index) ?? false)
                          return (
                            <button
                              key={o.index}
                              onClick={() => pickChip(f, o)}
                              style={{
                                // A long option (Thai copy runs long) has to wrap
                                // inside the pill, not spill past it — so this is
                                // minHeight + vertical padding, never a fixed
                                // height.
                                minHeight: 24,
                                maxWidth: '100%',
                                padding: '3px 9px',
                                borderRadius: 12,
                                border: picked ? '1px solid var(--accent)' : '1px solid var(--line-2)',
                                background: picked ? 'var(--accent-weak)' : 'var(--surface)',
                                color: picked ? 'var(--accent)' : 'var(--ink-2)',
                                fontSize: 11,
                                lineHeight: 1.45,
                                textAlign: 'left',
                                whiteSpace: 'normal',
                                overflowWrap: 'anywhere',
                                cursor: 'pointer',
                              }}
                            >
                              {o.label}
                            </button>
                          )
                        })}
                        <input
                          defaultValue=""
                          placeholder="Type your own…"
                          onChange={(e) => typeFreeText(f.key, e.target.value)}
                          style={{
                            height: 24,
                            minWidth: 90,
                            flex: 1,
                            border: '1px solid var(--line-2)',
                            borderRadius: 99,
                            padding: '0 9px',
                            fontSize: 11,
                            background: 'var(--surface)',
                            color: 'var(--ink)',
                          }}
                        />
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
            {profileError && (
              <div role="alert" style={{ fontSize: 11.5, lineHeight: 1.55, color: 'var(--danger, #b91c1c)' }}>
                {profileError}
              </div>
            )}
            {editMode ? (
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  onClick={() => void saveEdit()}
                  disabled={savingProfile || Object.keys(pending).length === 0}
                  style={{
                    flex: 1,
                    height: 32,
                    borderRadius: 8,
                    border: 'none',
                    background: 'var(--accent)',
                    color: '#fff',
                    fontSize: 12.5,
                    fontWeight: 500,
                    cursor: savingProfile || Object.keys(pending).length === 0 ? 'default' : 'pointer',
                    opacity: savingProfile || Object.keys(pending).length === 0 ? 0.6 : 1,
                  }}
                >
                  {savingProfile ? 'Saving…' : 'Save & regenerate plan'}
                </button>
                <button
                  onClick={cancelEdit}
                  disabled={savingProfile}
                  style={{
                    flex: 'none',
                    height: 32,
                    padding: '0 12px',
                    borderRadius: 8,
                    border: '1px solid var(--line-2)',
                    background: 'var(--surface)',
                    color: 'var(--ink-2)',
                    fontSize: 12.5,
                    fontWeight: 500,
                    cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
              </div>
            ) : (
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
            )}
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
                  <div
                    style={{
                      fontSize: 13,
                      lineHeight: 1.55,
                      color: 'var(--ink-2)',
                      border: '1px solid var(--line)',
                      borderRadius: 10,
                      padding: '10px 12px',
                    }}
                  >
                    <MarkdownContent text={findingsToMarkdown(research.findings)} />
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
