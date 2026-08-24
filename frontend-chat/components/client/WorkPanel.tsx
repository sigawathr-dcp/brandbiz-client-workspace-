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

// One correction as PATCH /client/intake/fields takes it (IntakeEditIn).
type ProfileUpdate = { field: string; option_index?: number; option_indices?: number[]; free_text?: string }

// How the server joins a multi-select answer into one stored string
// (client_intake.ANSWER_JOINER) — split on it to find which chips are current.
const ANSWER_JOINER = '; '

function sameSet(a: number[], b: number[]): boolean {
  return a.length === b.length && a.every((i) => b.includes(i))
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
  onSaveProfile: (updates: ProfileUpdate[]) => Promise<boolean>
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

  // Which chips are the saved answer for a field. A multi-select answer is
  // stored joined with ANSWER_JOINER, so it can match several chips; a
  // single-select answer matches at most one. Matched on `value` (what the
  // server stores) with the Thai `label` only as a fallback for an older
  // payload. Empty for a free-text answer that matches no chip.
  function currentIndicesOf(field: IntakeField): number[] {
    const current = fields[field.key] || ''
    if (!current) return []
    const parts = field.multi_select ? current.split(ANSWER_JOINER) : [current]
    return field.options.filter((o) => parts.includes(o.value ?? o.label)).map((o) => o.index)
  }

  function pickChip(field: IntakeField, option: { index: number; label: string }) {
    if (field.multi_select) {
      // Toggle the chip in/out of the pending set; the row's preview label
      // joins the picked labels the same way the server will ("; "). The
      // first tap starts from the saved set, so it adds/removes one chip
      // instead of silently dropping every other current answer.
      setPending((prev) => {
        const current = prev[field.key]?.option_indices ?? currentIndicesOf(field)
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
  // The pending entries that would actually change something. Tapping the chip
  // that is already the answer, or typing the answer back verbatim, is a no-op:
  // it must not arm Save, because saving re-runs the market scan and redrafts
  // the plan (ClientWorkspace.tsx::handleSaveProfile) — an expensive round trip
  // for an unchanged profile. An emptied free-text box is a no-op too.
  function effectiveUpdates(): ProfileUpdate[] {
    return Object.entries(pending).flatMap(([field, v]): ProfileUpdate[] => {
      const current = fields[field] || ''
      const def = intakeFields.find((f) => f.key === field)
      if (v.option_indices !== undefined) {
        if (v.option_indices.length === 0) return []
        // Same set as what is saved (in any order) stores the same joined
        // value — resolve_answers() sorts by ordinal, so compare as a set.
        if (def && sameSet(v.option_indices, currentIndicesOf(def))) return []
        return [{ field, option_indices: v.option_indices }]
      }
      if (v.option_index !== undefined) {
        const opt = def?.options.find((o) => o.index === v.option_index)
        // `value` is what the server stores for that chip; `label` is only a
        // fallback for an older payload that predates it.
        const resolved = opt?.value ?? opt?.label ?? ''
        return resolved && resolved === current ? [] : [{ field, option_index: v.option_index }]
      }
      const text = (v.free_text ?? '').trim()
      return !text || text === current ? [] : [{ field, free_text: text }]
    })
  }

  async function saveEdit() {
    const updates = effectiveUpdates()
    if (updates.length === 0) return // Save is disabled in this state anyway
    const ok = await onSaveProfile(updates)
    if (!ok) return // keep `pending` and edit mode — profileError explains why
    setPending({})
    setEditMode(false)
  }

  // Save stays disabled until at least one pending entry is a real change —
  // not merely a tap (see effectiveUpdates).
  const dirty = effectiveUpdates().length > 0

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
            {editMode && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--ink-3)' }}>
                <span style={{ display: 'inline-flex', color: 'var(--accent)' }}>
                  <Ic.check size={11} strokeWidth={2} />
                </span>
                marks your current answer — tap another chip to replace it (or toggle chips on a multi-choice question).
              </div>
            )}
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
                const current = fields[f.key] || ''
                // Which chips are the saved answer, so edit mode can keep them
                // marked. Every option used to render identically once edit
                // mode opened, so a mis-tap was invisible — you couldn't see
                // what you were about to overwrite. One index for a single-
                // select field, several for a multi-select one.
                const currentIndices = currentIndicesOf(f)
                // The chips a pending edit has picked, in either shape;
                // undefined while the pending entry is free text (or absent).
                const pendingIndices =
                  edit?.option_indices !== undefined
                    ? edit.option_indices
                    : edit?.option_index !== undefined
                      ? [edit.option_index]
                      : undefined
                // A pending edit only counts as a change once it has text —
                // an emptied free-text box is not yet a new answer. Re-tapping
                // the chip(s) that already are the answer isn't one either:
                // the Thai label never equals the stored English value, so
                // without this the row would show a bogus "old → new".
                const nextLabel = (edit?.label ?? '').trim()
                const reAffirmed = pendingIndices !== undefined && sameSet(pendingIndices, currentIndices)
                const changed = !!nextLabel && !!current && !reAffirmed && nextLabel !== current
                const freeText = (edit?.free_text ?? '').trim()
                const freeTextChanged = !!freeText && freeText !== current
                // An answer that matches no chip was typed — the input is
                // where its "current" marker has to live.
                const freeTextIsCurrent = currentIndices.length === 0 && !!current
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
                        {changed ? (
                          // old → new, so a wrong tap is obvious before Save
                          // commits it (saving re-runs research and the plan).
                          <>
                            <span style={{ color: 'var(--ink-4)', textDecoration: 'line-through' }}>{current}</span>
                            <span style={{ color: 'var(--ink-4)' }}> → </span>
                            <span style={{ color: 'var(--accent)', fontWeight: 500 }}>{nextLabel}</span>
                          </>
                        ) : (
                          (reAffirmed ? current : nextLabel) || current || 'not asked yet'
                        )}
                      </div>
                    </div>
                    {editMode && answered && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-start', gap: 6, paddingLeft: 25 }}>
                        {f.options.map((o) => {
                          // Stays marked even while another chip is picked —
                          // seeing the answer you are replacing is the whole
                          // point of the marker.
                          const isCurrent = currentIndices.includes(o.index)
                          const pickedNow = pendingIndices?.includes(o.index) ?? false
                          // Three accent states, no grey: an answer that is
                          // already chosen reads as chosen.
                          //   current      — accent tint + ✓ (what is saved)
                          //   replacement  — solid accent (what Save will store)
                          //   superseded   — a current one, faded, once it is
                          //                  no longer in the pending pick (or
                          //                  free text replaces the answer)
                          // On a multi-select field the pending pick is a set,
                          // so a current chip only fades when toggled out.
                          const replacement = pickedNow && !isCurrent
                          const superseded =
                            isCurrent && ((pendingIndices !== undefined && !pickedNow) || freeTextChanged)
                          const selected = isCurrent || replacement
                          return (
                            <button
                              key={o.index}
                              onClick={() => pickChip(f, o)}
                              aria-pressed={selected && !superseded}
                              title={isCurrent ? 'Your current answer' : undefined}
                              style={{
                                // A long option (Thai copy runs long) has to wrap
                                // inside the pill, not spill past it — so this is
                                // minHeight + vertical padding, never a fixed
                                // height.
                                minHeight: 24,
                                maxWidth: '100%',
                                display: 'inline-flex',
                                alignItems: 'flex-start',
                                gap: 4,
                                padding: '3px 9px',
                                borderRadius: 12,
                                border: selected ? '1px solid var(--accent)' : '1px solid var(--line-2)',
                                background: replacement
                                  ? 'var(--accent)'
                                  : isCurrent
                                    ? 'var(--accent-weak)'
                                    : 'var(--surface)',
                                color: replacement
                                  ? 'var(--accent-ink)'
                                  : isCurrent
                                    ? 'var(--accent)'
                                    : 'var(--ink-2)',
                                fontWeight: selected ? 500 : 400,
                                opacity: superseded ? 0.5 : 1,
                                fontSize: 11,
                                lineHeight: 1.45,
                                textAlign: 'left',
                                whiteSpace: 'normal',
                                overflowWrap: 'anywhere',
                                cursor: 'pointer',
                              }}
                            >
                              {isCurrent && (
                                <span style={{ flex: 'none', display: 'inline-flex', marginTop: 2, color: 'var(--accent)' }}>
                                  <Ic.check size={11} strokeWidth={2} />
                                </span>
                              )}
                              <span style={{ minWidth: 0 }}>{o.label}</span>
                            </button>
                          )
                        })}
                        <input
                          defaultValue=""
                          placeholder={freeTextIsCurrent ? `Now: ${current}` : 'Type your own…'}
                          onChange={(e) => typeFreeText(f.key, e.target.value)}
                          style={{
                            height: 24,
                            minWidth: 90,
                            flex: 1,
                            // Same accent language as the chips: a free-text
                            // answer that is already the saved one gets the
                            // tint, a typed change gets the accent outline.
                            border:
                              freeTextChanged || freeTextIsCurrent
                                ? '1px solid var(--accent)'
                                : '1px solid var(--line-2)',
                            borderRadius: 99,
                            padding: '0 9px',
                            fontSize: 11,
                            background: freeTextIsCurrent && !freeTextChanged ? 'var(--accent-weak)' : 'var(--surface)',
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
                  disabled={savingProfile || !dirty}
                  title={!dirty ? 'Pick a different answer first — nothing has changed yet' : undefined}
                  style={{
                    flex: 1,
                    height: 32,
                    borderRadius: 8,
                    border: 'none',
                    background: 'var(--accent)',
                    color: '#fff',
                    fontSize: 12.5,
                    fontWeight: 500,
                    cursor: savingProfile || !dirty ? 'default' : 'pointer',
                    opacity: savingProfile || !dirty ? 0.6 : 1,
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
