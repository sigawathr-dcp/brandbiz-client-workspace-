'use client'

import { useEffect, useState } from 'react'
import { npsVerdict } from '@/lib/nps'

interface Lead {
  id: string
  workspace_id: string
  plan_id: string | null
  contact_name: string | null
  contact_phone_or_line: string | null
  best_time: string | null
  status: 'new' | 'assigned' | 'done'
  assigned_to: string | null
  n8n_error: string | null
  created_at: string
  // PLAN.md Task 5.10 — only present when the client rated the plan; a
  // missing rating renders nothing, not a "—" that reads like a zero.
  nps_score: number | null
  nps_comment: string | null
}

// Client Workspaces (Phase 5, D21/D22) — the expert handoff inbox. Backs
// the design's "Expert handoff inbox" card in Internal mode. Every row
// here came from a real "Talk to an expert" submission
// (POST /client/leads -> app/services/lead.py::submit), not staged data.
export default function LeadsInboxPage() {
  const [leads, setLeads] = useState<Lead[] | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  async function load() {
    const res = await fetch('/api/admin/leads', { credentials: 'include', cache: 'no-store' })
    if (res.ok) setLeads(await res.json())
  }

  useEffect(() => {
    load()
  }, [])

  async function act(id: string, action: 'assign' | 'done') {
    setBusyId(id)
    try {
      await fetch(`/api/admin/leads/${id}/${action}`, { method: 'PATCH', credentials: 'include' })
      await load()
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div style={{ padding: 32, maxWidth: 900, margin: '0 auto' }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink)' }}>Expert handoff inbox</h1>
        <p style={{ color: 'var(--ink-3)', fontSize: 13, marginTop: 4 }}>
          Leads submitted from a client workspace&apos;s &quot;Talk to an expert&quot; CTA.
        </p>
      </div>

      {leads === null && <div style={{ fontSize: 13, color: 'var(--ink-3)' }}>Loading…</div>}
      {leads !== null && leads.length === 0 && (
        <div style={{ fontSize: 13, color: 'var(--ink-3)' }}>No leads yet.</div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
        {leads?.map((lead) => (
          <div
            key={lead.id}
            style={{
              border: '1px solid var(--line)',
              borderRadius: 9,
              padding: '10px 11px',
              background: 'var(--surface)',
              display: 'flex',
              gap: 10,
              alignItems: 'flex-start',
            }}
          >
            <span
              style={{
                fontSize: 10,
                fontWeight: 600,
                color:
                  lead.status === 'new' ? 'var(--info)' : lead.status === 'assigned' ? 'var(--warning)' : 'var(--ink-3)',
                background:
                  lead.status === 'new' ? 'var(--info-bg)' : lead.status === 'assigned' ? 'var(--warning-bg)' : 'var(--surface-2)',
                borderRadius: 4,
                padding: '2px 6px',
                flex: 'none',
                marginTop: 1,
                textTransform: 'uppercase',
              }}
            >
              {lead.status}
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--ink)' }}>
                  {lead.contact_name || 'Unnamed contact'}
                </div>
                {lead.nps_score !== null && (
                  <span
                    title={`Rated ${lead.nps_score}/10 on the plan — ${npsVerdict(lead.nps_score).bucket}`}
                    style={{
                      fontSize: 10.5,
                      fontWeight: 600,
                      fontFamily: 'var(--font-mono)',
                      color: npsVerdict(lead.nps_score).color,
                      background: npsVerdict(lead.nps_score).background,
                      borderRadius: 4,
                      padding: '2px 6px',
                    }}
                  >
                    NPS {lead.nps_score}
                  </span>
                )}
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>
                {lead.contact_phone_or_line || 'no contact given'} · {lead.best_time || 'no preferred time'} ·{' '}
                {new Date(lead.created_at).toLocaleString()}
                {lead.n8n_error && <span style={{ color: 'var(--danger)' }}> · webhook failed, retry needed</span>}
              </div>
              {lead.nps_comment && (
                <div style={{ fontSize: 11.5, color: 'var(--ink-2)', lineHeight: 1.5, marginTop: 3, fontStyle: 'italic' }}>
                  &quot;{lead.nps_comment}&quot;
                </div>
              )}
            </div>
            {lead.status === 'new' && (
              <button
                onClick={() => act(lead.id, 'assign')}
                disabled={busyId === lead.id}
                style={{
                  fontSize: 12,
                  padding: '5px 10px',
                  borderRadius: 6,
                  border: '1px solid var(--line-2)',
                  background: 'var(--surface)',
                  cursor: 'pointer',
                }}
              >
                Assign to me
              </button>
            )}
            {lead.status === 'assigned' && (
              <button
                onClick={() => act(lead.id, 'done')}
                disabled={busyId === lead.id}
                style={{
                  fontSize: 12,
                  padding: '5px 10px',
                  borderRadius: 6,
                  border: 'none',
                  background: 'var(--accent)',
                  color: '#fff',
                  cursor: 'pointer',
                }}
              >
                Mark done
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
