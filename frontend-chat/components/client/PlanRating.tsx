'use client'

import { useState } from 'react'
import { npsVerdict } from '@/lib/nps'
import type { PlanRatingData } from './types'

function ratingPrompt(score: number | null, agentName: string): string {
  if (score === null) return `How likely are you to recommend ${agentName} to another business owner?`
  if (score <= 6) return `What made this fall short? ${agentName} can't fix what it isn't told.`
  if (score <= 8) return 'What would have made this a 10?'
  return "What worked best? We'll tell the strategist before your call."
}

// Client Workspaces redesign (PLAN.md Task 5.10) — collects an NPS-style
// rating on the saved plan document, so the strategist sees it before the
// handoff call (app/routers/admin_leads.py's LeadOut.nps_score/nps_comment).
// One rating per (plan, user), upserted — see app/services/plan_rating.py.
export default function PlanRating({
  planId,
  initial,
  agentName,
}: {
  planId: string
  initial: PlanRatingData | null
  agentName: string
}) {
  const [score, setScore] = useState<number | null>(initial?.score ?? null)
  const [hoverScore, setHoverScore] = useState<number | null>(null)
  const [comment, setComment] = useState(initial?.comment ?? '')
  const [submitting, setSubmitting] = useState(false)
  const [logged, setLogged] = useState(initial !== null)
  const [loggedScore, setLoggedScore] = useState(initial?.score ?? null)
  const [error, setError] = useState('')

  async function submit() {
    if (score === null) return
    setSubmitting(true)
    setError('')
    try {
      const res = await fetch(`/api/client/plans/${planId}/rating`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ score, comment: comment.trim() || null }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError(data.detail || 'Could not save your rating right now — please try again.')
        return
      }
      setLoggedScore(score)
      setLogged(true)
    } catch {
      setError('Network error — please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (logged && loggedScore !== null) {
    const verdict = npsVerdict(loggedScore)
    return (
      <div className="no-print" style={{ display: 'flex', gap: 13, alignItems: 'flex-start' }}>
        <div
          style={{
            width: 30,
            height: 30,
            flex: 'none',
            borderRadius: '50%',
            background: 'var(--t1-bg)',
            display: 'grid',
            placeItems: 'center',
            color: 'var(--t1)',
          }}
        >
          ✓
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 4 }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--ink)' }}>Thanks — logged</div>
            <span
              style={{
                fontSize: 11.5,
                fontWeight: 600,
                borderRadius: 99,
                padding: '3px 9px',
                color: verdict.color,
                background: verdict.background,
              }}
            >
              {verdict.label}
            </span>
          </div>
          <div style={{ fontSize: 13, lineHeight: 1.55, color: 'var(--ink-3)' }}>
            Attached to this plan, so the strategist sees your rating before they call.
          </div>
        </div>
      </div>
    )
  }

  const verdict = score !== null ? npsVerdict(score) : null

  return (
    <div className="no-print">
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 5 }}>
        <div style={{ fontSize: 15, fontWeight: 600, letterSpacing: '-.01em', color: 'var(--ink)' }}>Rate this plan</div>
        {verdict && (
          <span
            style={{
              fontSize: 11.5,
              fontWeight: 600,
              borderRadius: 99,
              padding: '3px 9px',
              color: verdict.color,
              background: verdict.background,
            }}
          >
            {verdict.label}
          </span>
        )}
      </div>
      <div style={{ fontSize: 13.5, lineHeight: 1.55, color: 'var(--ink-3)', marginBottom: 14 }}>
        {ratingPrompt(score, agentName)}
      </div>
      <div onMouseLeave={() => setHoverScore(null)} className="client-nps-grid" style={{ display: 'grid', gap: 6 }}>
        {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => {
          const active = (hoverScore ?? score ?? 0) >= n
          const chosen = score === n
          return (
            <button
              key={n}
              onClick={() => setScore(n)}
              onMouseEnter={() => setHoverScore(n)}
              style={{
                width: '100%',
                height: 42,
                borderRadius: 9,
                fontSize: 14,
                fontWeight: 500,
                cursor: 'pointer',
                fontFamily: 'var(--font-sans)',
                transition: 'background .12s, border-color .12s',
                border: chosen || active ? '1px solid var(--accent)' : '1px solid var(--line-2)',
                background: chosen ? 'var(--accent)' : active ? 'var(--accent-weak)' : 'var(--surface)',
                color: chosen ? '#fff' : active ? 'var(--accent)' : 'var(--ink-2)',
              }}
            >
              {n}
            </button>
          )
        })}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, fontSize: 11, color: 'var(--ink-4)' }}>
        <span>Not at all likely</span>
        <span>Extremely likely</span>
      </div>

      {score !== null && (
        <div style={{ marginTop: 16, animation: 'popIn .24s ease' }}>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Optional — one line is plenty"
            style={{
              width: '100%',
              height: 74,
              resize: 'none',
              borderRadius: 9,
              border: '1px solid var(--line-2)',
              background: 'var(--surface)',
              padding: '10px 12px',
              fontSize: 13.5,
              lineHeight: 1.55,
              fontFamily: 'var(--font-sans)',
              color: 'var(--ink)',
              outline: 'none',
              boxSizing: 'border-box',
            }}
          />
          {error && <div style={{ marginTop: 8, fontSize: 12, color: 'var(--danger)' }}>{error}</div>}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 12 }}>
            <button
              onClick={submit}
              disabled={submitting}
              style={{
                height: 38,
                padding: '0 17px',
                borderRadius: 8,
                border: 'none',
                background: 'var(--accent)',
                color: '#fff',
                fontSize: 13.5,
                fontWeight: 500,
                cursor: submitting ? 'default' : 'pointer',
                opacity: submitting ? 0.7 : 1,
              }}
            >
              {submitting ? 'Submitting…' : 'Submit feedback'}
            </button>
            <span style={{ fontSize: 11.5, lineHeight: 1.5, color: 'var(--ink-4)', flex: 1 }}>
              Goes to the Brandbiz team and the strategist on your handoff.
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
