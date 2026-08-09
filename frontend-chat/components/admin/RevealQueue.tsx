'use client'

import { useState } from 'react'
import type { RevealRequestSummary } from '@/lib/admin-api'

const STATUS_COLOR: Record<string, string> = {
  pending: 'var(--warning)',
  approved: 'var(--success)',
  denied: 'var(--danger)',
  expired: 'var(--muted)',
  completed: 'var(--muted)',
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span style={{
      fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 999,
      background: `${STATUS_COLOR[status] ?? 'var(--muted)'}22`,
      color: STATUS_COLOR[status] ?? 'var(--muted)',
    }}>
      {status}
    </span>
  )
}

function CreateRequestModal({ onClose, onCreated }: {
  onClose: () => void
  onCreated: (item: RevealRequestSummary) => void
}) {
  const [messageId, setMessageId] = useState('')
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const res = await fetch('/api/admin/reveals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_message_id: messageId.trim(), reason: reason.trim() }),
      })
      if (!res.ok) {
        const text = await res.text()
        setError(text || `Error ${res.status}`)
        return
      }
      const created: RevealRequestSummary = await res.json()
      onCreated(created)
      onClose()
    } catch (e) {
      setError(String(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }} onClick={onClose}>
      <div style={{
        background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 10,
        padding: 28, width: 480, maxWidth: '90vw', boxShadow: '0 8px 32px rgba(0,0,0,0.2)',
      }} onClick={e => e.stopPropagation()}>
        <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>Create Reveal Request</h2>
        <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 20 }}>
          A second admin must approve before you can view the decrypted message.
        </p>

        {error && (
          <div style={{
            background: 'rgba(239,68,68,0.1)', border: '1px solid var(--danger)',
            borderRadius: 6, padding: '10px 14px', marginBottom: 16,
            color: 'var(--danger)', fontSize: 13,
          }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 6 }}>
              Message ID (UUID)
            </label>
            <input
              type="text"
              required
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              value={messageId}
              onChange={e => setMessageId(e.target.value)}
              style={{
                width: '100%', boxSizing: 'border-box',
                padding: '8px 12px', borderRadius: 6,
                border: '1px solid var(--border)', background: 'var(--surface)',
                color: 'var(--fg)', fontSize: 13, fontFamily: 'monospace',
              }}
            />
          </div>

          <div style={{ marginBottom: 24 }}>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 6 }}>
              Reason
            </label>
            <textarea
              required
              rows={3}
              placeholder="Compliance review, incident investigation…"
              value={reason}
              onChange={e => setReason(e.target.value)}
              style={{
                width: '100%', boxSizing: 'border-box',
                padding: '8px 12px', borderRadius: 6,
                border: '1px solid var(--border)', background: 'var(--surface)',
                color: 'var(--fg)', fontSize: 13, resize: 'vertical',
              }}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
            <button type="button" onClick={onClose} style={{ fontSize: 13, padding: '7px 16px' }}>
              Cancel
            </button>
            <button className="primary" type="submit" disabled={submitting} style={{ fontSize: 13, padding: '7px 16px' }}>
              {submitting ? 'Submitting…' : 'Submit request'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function RevealQueue({ initialItems }: { initialItems: RevealRequestSummary[] }) {
  const [items, setItems] = useState(initialItems)
  const [processing, setProcessing] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)

  const pending = items.filter(r => r.status === 'pending')
  const other = items.filter(r => r.status !== 'pending')

  async function act(id: string, action: 'approve' | 'deny') {
    setProcessing(id)
    setError(null)
    try {
      const res = await fetch(`/api/admin/reveals/${id}/${action}`, { method: 'POST' })
      if (!res.ok) { setError(`${action} failed: ${await res.text()}`); return }
      const updated: RevealRequestSummary = await res.json()
      setItems(prev => prev.map(r => r.id === id ? updated : r))
    } catch (e) {
      setError(String(e))
    } finally {
      setProcessing(null)
    }
  }

  function handleCreated(item: RevealRequestSummary) {
    setItems(prev => [item, ...prev])
  }

  return (
    <div>
      {showCreate && (
        <CreateRequestModal onClose={() => setShowCreate(false)} onCreated={handleCreated} />
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700 }}>Reveal Queue</h1>
          <p style={{ color: 'var(--muted)', fontSize: 13, marginTop: 4 }}>
            4-eyes reveal requests. Approver must differ from requester (enforced server-side).
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {pending.length > 0 && (
            <div style={{
              background: 'var(--warning-bg)', border: '1px solid var(--warning)',
              borderRadius: 6, padding: '6px 12px', fontSize: 12,
              color: 'var(--warning)', fontWeight: 600,
            }}>
              {pending.length} pending
            </div>
          )}
          <button className="primary" onClick={() => setShowCreate(true)} style={{ fontSize: 13, padding: '7px 16px' }}>
            + Create request
          </button>
        </div>
      </div>

      {error && (
        <div style={{
          background: 'rgba(239,68,68,0.1)', border: '1px solid var(--danger)',
          borderRadius: 6, padding: '10px 14px', marginBottom: 12,
          color: 'var(--danger)', fontSize: 13,
        }}>
          {error}
        </div>
      )}

      {pending.length > 0 && (
        <section style={{ marginBottom: 36 }}>
          <h2 style={{ fontSize: 13, fontWeight: 600, marginBottom: 14, color: 'var(--warning)' }}>
            Pending ({pending.length})
          </h2>
          <ItemList items={pending} processing={processing} onAct={act} />
        </section>
      )}

      {other.length > 0 && (
        <section>
          <h2 style={{ fontSize: 13, fontWeight: 600, marginBottom: 14, color: 'var(--muted)' }}>
            Recent ({other.length})
          </h2>
          <ItemList items={other} processing={processing} onAct={act} />
        </section>
      )}

      {items.length === 0 && (
        <div style={{
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 8, padding: 48, textAlign: 'center', color: 'var(--muted)', fontSize: 13,
        }}>
          No reveal requests yet.
        </div>
      )}
    </div>
  )
}

function ItemList({ items, processing, onAct }: {
  items: RevealRequestSummary[]
  processing: string | null
  onAct: (id: string, action: 'approve' | 'deny') => void
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {items.map(r => (
        <div key={r.id} style={{
          background: 'var(--surface)',
          border: `1px solid ${r.status === 'pending' ? 'var(--warning)' : 'var(--border)'}`,
          borderRadius: 8, padding: '16px 20px',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <StatusBadge status={r.status} />
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>{new Date(r.created_at).toLocaleString()}</span>
              </div>
              <div style={{ fontWeight: 500, marginBottom: 4, wordBreak: 'break-all' }}>Reason: {r.reason}</div>
              <div style={{ fontSize: 12, color: 'var(--muted)', display: 'flex', flexWrap: 'wrap', gap: '4px 16px' }}>
                <span>Requester: <code>{r.requester_id.slice(0, 8)}…</code></span>
                <span>Message: <code>{r.target_message_id.slice(0, 8)}…</code></span>
                {r.approver_id && <span>Approver: <code>{r.approver_id.slice(0, 8)}…</code></span>}
                {r.approved_at && <span>Approved: {new Date(r.approved_at).toLocaleString()}</span>}
                {r.expires_at && r.status === 'approved' && (
                  <span style={{ color: 'var(--warning)' }}>Expires: {new Date(r.expires_at).toLocaleString()}</span>
                )}
              </div>
            </div>
            {r.status === 'pending' && (
              <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                <button className="primary" disabled={processing === r.id} onClick={() => onAct(r.id, 'approve')} style={{ fontSize: 12, padding: '5px 12px' }}>
                  {processing === r.id ? '…' : 'Approve'}
                </button>
                <button className="danger" disabled={processing === r.id} onClick={() => onAct(r.id, 'deny')} style={{ fontSize: 12, padding: '5px 12px' }}>
                  Deny
                </button>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
