'use client'

import { useState } from 'react'

// Client Workspaces (Phase 5, D21/D22) — "Talk to a Brandbiz expert", the
// commercial point of the whole funnel (per DSME_ai.md: "the only real
// code" in the demo track). Keeps the consent line honest: a named
// strategist reading this conversation is exactly the reveal-flow access
// pattern (D15), surfaced here rather than left implicit.
export default function LeadModal({
  planId,
  onClose,
}: {
  planId: string | null
  onClose: () => void
}) {
  const [name, setName] = useState('')
  const [contact, setContact] = useState('')
  const [bestTime, setBestTime] = useState('')
  const [sent, setSent] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')

  async function submit() {
    setSending(true)
    setError('')
    try {
      const res = await fetch('/api/client/leads', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          plan_id: planId,
          contact_name: name || null,
          contact_phone_or_line: contact || null,
          best_time: bestTime || null,
        }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError(data.detail || 'Could not send this right now — please try again.')
        return
      }
      setSent(true)
    } catch {
      setError('Network error — please try again.')
    } finally {
      setSending(false)
    }
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(16,18,23,.42)',
        display: 'grid',
        placeItems: 'center',
        zIndex: 20,
      }}
      onClick={onClose}
    >
      <div
        className="client-leadmodal-card"
        style={{ maxWidth: '92vw', background: 'var(--surface)', borderRadius: 16, boxShadow: 'var(--shadow-3)', overflow: 'hidden' }}
        onClick={(e) => e.stopPropagation()}
      >
        {!sent ? (
          <div className="client-leadmodal-body">
            <div style={{ fontSize: 19, fontWeight: 600, letterSpacing: '-.01em', marginBottom: 5, color: 'var(--ink)' }}>
              Talk to a Brandbiz expert
            </div>
            <div style={{ fontSize: 13.5, lineHeight: 1.55, color: 'var(--ink-3)', marginBottom: 20 }}>
              We&apos;ll send this plan and your profile to a strategist. They reply within one working day.
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 13 }}>
              <div>
                <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--ink-2)', marginBottom: 5 }}>Name</div>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  style={{ width: '100%', height: 38, borderRadius: 7, border: '1px solid var(--line-2)', padding: '0 10px', fontSize: 13.5, boxSizing: 'border-box' }}
                />
              </div>
              <div>
                <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--ink-2)', marginBottom: 5 }}>Phone or LINE</div>
                <input
                  value={contact}
                  onChange={(e) => setContact(e.target.value)}
                  placeholder="08x-xxx-xxxx"
                  style={{ width: '100%', height: 38, borderRadius: 7, border: '1px solid var(--line-2)', padding: '0 10px', fontSize: 13.5, boxSizing: 'border-box' }}
                />
              </div>
              <div>
                <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--ink-2)', marginBottom: 5 }}>Best time to reach you</div>
                <input
                  value={bestTime}
                  onChange={(e) => setBestTime(e.target.value)}
                  placeholder="Weekday afternoons"
                  style={{ width: '100%', height: 38, borderRadius: 7, border: '1px solid var(--line-2)', padding: '0 10px', fontSize: 13.5, boxSizing: 'border-box' }}
                />
              </div>
              <div style={{ display: 'flex', gap: 9, alignItems: 'flex-start', background: 'var(--surface-2)', borderRadius: 8, padding: '10px 11px' }}>
                <div style={{ fontSize: 11.5, lineHeight: 1.55, color: 'var(--ink-2)' }}>
                  Sharing this plan lets a named Brandbiz strategist read this conversation. That access is logged and shown to you.
                </div>
              </div>
              {error && <div style={{ fontSize: 12, color: 'var(--danger)' }}>{error}</div>}
            </div>
            <div className="client-leadmodal-actions" style={{ marginTop: 20 }}>
              <button
                onClick={onClose}
                style={{ height: 38, padding: '0 14px', borderRadius: 8, border: '1px solid var(--line-2)', background: 'var(--surface)', color: 'var(--ink-2)', fontSize: 13.5, cursor: 'pointer' }}
              >
                Cancel
              </button>
              <button
                onClick={submit}
                disabled={sending}
                style={{ height: 38, padding: '0 16px', borderRadius: 8, border: 'none', background: 'var(--accent)', color: '#fff', fontSize: 13.5, fontWeight: 500, cursor: sending ? 'default' : 'pointer', opacity: sending ? 0.7 : 1 }}
              >
                {sending ? 'Sending…' : 'Send to an expert'}
              </button>
            </div>
          </div>
        ) : (
          <div style={{ padding: '34px 26px 26px', textAlign: 'center' }}>
            <div style={{ width: 44, height: 44, margin: '0 auto 14px', borderRadius: '50%', background: 'var(--t1-bg)', display: 'grid', placeItems: 'center', color: 'var(--t1)', fontSize: 22 }}>
              ✓
            </div>
            <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 6, color: 'var(--ink)' }}>Sent</div>
            <div style={{ fontSize: 13.5, lineHeight: 1.6, color: 'var(--ink-3)', marginBottom: 18 }}>
              Your plan and profile are with a Brandbiz strategist. You&apos;ll hear back within one working day.
            </div>
            <button
              onClick={onClose}
              style={{ height: 38, padding: '0 18px', borderRadius: 8, border: 'none', background: 'var(--accent)', color: '#fff', fontSize: 13.5, fontWeight: 500, cursor: 'pointer' }}
            >
              Back to my plan
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
