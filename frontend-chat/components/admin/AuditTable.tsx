'use client'

import { useCallback, useEffect, useState } from 'react'
import type { AuditLogEntry, AuditLogListResponse } from '@/lib/admin-api'

const AUDIT_ACTIONS = [
  'login', 'logout',
  'message_sent', 'message_received',
  'model_blocked', 'pii_detected', 'tier_blocked', 'quota_exceeded',
  'reveal_requested', 'reveal_approved', 'reveal_denied', 'reveal_viewed',
  'admin_user_created', 'admin_role_changed', 'admin_quota_changed',
  'admin_permission_changed',
]

const LIMIT = 50

interface Filters {
  action: string
  resource_type: string
  date_from: string
  date_to: string
}

const EMPTY: Filters = { action: '', resource_type: '', date_from: '', date_to: '' }

function badge(action: string) {
  const color =
    action.startsWith('pii') || action.startsWith('tier') || action.startsWith('model_blocked')
      ? 'var(--danger)'
      : action.startsWith('reveal')
      ? 'var(--warning)'
      : action.startsWith('admin')
      ? 'var(--accent)'
      : 'var(--muted)'
  return (
    <span style={{
      fontSize: 11, fontWeight: 600, padding: '2px 7px', borderRadius: 999,
      background: `${color}22`, color,
    }}>
      {action}
    </span>
  )
}

export default function AuditTable({ initialData }: { initialData: AuditLogListResponse }) {
  const [data, setData] = useState(initialData)
  const [filters, setFilters] = useState<Filters>(EMPTY)
  const [pending, setPending] = useState<Filters>(EMPTY)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async (f: Filters, off: number) => {
    setLoading(true)
    try {
      const p = new URLSearchParams({ limit: String(LIMIT), offset: String(off) })
      if (f.action) p.set('action', f.action)
      if (f.resource_type) p.set('resource_type', f.resource_type)
      if (f.date_from) p.set('date_from', new Date(f.date_from).toISOString())
      if (f.date_to) p.set('date_to', new Date(f.date_to + 'T23:59:59').toISOString())
      const res = await fetch(`/api/admin/audit?${p}`)
      if (res.ok) setData(await res.json())
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load(filters, offset) }, [filters, offset, load])

  function applyFilters() { setFilters(pending); setOffset(0) }
  function clearFilters() { setPending(EMPTY); setFilters(EMPTY); setOffset(0) }

  const totalPages = Math.ceil(data.total / LIMIT)
  const currentPage = Math.floor(offset / LIMIT) + 1

  return (
    <div>
      <div style={{
        display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end',
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 8, padding: '14px 16px', marginBottom: 16,
      }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label style={{ fontSize: 11, color: 'var(--muted)' }}>Action</label>
          <select value={pending.action} onChange={e => setPending(p => ({ ...p, action: e.target.value }))} style={{ minWidth: 160 }}>
            <option value="">All actions</option>
            {AUDIT_ACTIONS.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label style={{ fontSize: 11, color: 'var(--muted)' }}>Resource type</label>
          <input type="text" placeholder="e.g. message" value={pending.resource_type} onChange={e => setPending(p => ({ ...p, resource_type: e.target.value }))} style={{ width: 120 }} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label style={{ fontSize: 11, color: 'var(--muted)' }}>From</label>
          <input type="date" value={pending.date_from} onChange={e => setPending(p => ({ ...p, date_from: e.target.value }))} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label style={{ fontSize: 11, color: 'var(--muted)' }}>To</label>
          <input type="date" value={pending.date_to} onChange={e => setPending(p => ({ ...p, date_to: e.target.value }))} />
        </div>
        <div style={{ display: 'flex', gap: 8, alignSelf: 'flex-end' }}>
          <button className="primary" onClick={applyFilters}>Apply</button>
          <button className="ghost" onClick={clearFilters}>Clear</button>
        </div>
      </div>

      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden' }}>
        <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--border)', color: 'var(--muted)', fontSize: 12, display: 'flex', justifyContent: 'space-between' }}>
          <span>{loading ? 'Loading…' : `${data.total.toLocaleString()} entries`}</span>
          <span>Page {currentPage} of {totalPages || 1}</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Action</th>
              <th>User</th>
              <th>Resource</th>
              <th>IP</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map(row => <AuditRow key={row.id} row={row} />)}
            {data.items.length === 0 && !loading && (
              <tr>
                <td colSpan={5} style={{ textAlign: 'center', color: 'var(--muted)', padding: 32 }}>
                  No entries match the current filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        {data.total > LIMIT && (
          <div style={{ padding: '10px 16px', borderTop: '1px solid var(--border)', display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="ghost" disabled={offset === 0} onClick={() => setOffset(o => Math.max(0, o - LIMIT))}>Previous</button>
            <button className="ghost" disabled={offset + LIMIT >= data.total} onClick={() => setOffset(o => o + LIMIT)}>Next</button>
          </div>
        )}
      </div>
    </div>
  )
}

function AuditRow({ row }: { row: AuditLogEntry }) {
  const [expanded, setExpanded] = useState(false)
  const dt = new Date(row.created_at)
  const dtStr = `${dt.toLocaleDateString()} ${dt.toLocaleTimeString()}`
  return (
    <>
      <tr onClick={() => row.details && setExpanded(e => !e)} style={{ cursor: row.details ? 'pointer' : 'default' }}>
        <td style={{ fontSize: 12, color: 'var(--muted)', whiteSpace: 'nowrap' }}>{dtStr}</td>
        <td>{badge(row.action)}</td>
        <td style={{ fontSize: 12, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {row.user_id?.slice(0, 8)}…
        </td>
        <td style={{ fontSize: 12, color: 'var(--muted)' }}>
          {row.resource_type}{row.resource_id ? `/${row.resource_id.slice(0, 8)}…` : ''}
        </td>
        <td style={{ fontSize: 12, color: 'var(--muted)' }}>{row.ip_address || '—'}</td>
      </tr>
      {expanded && row.details && (
        <tr>
          <td colSpan={5} style={{ background: 'rgba(0,0,0,0.2)', padding: '8px 16px' }}>
            <pre style={{ fontSize: 11, color: 'var(--muted)', margin: 0, whiteSpace: 'pre-wrap' }}>
              {JSON.stringify(row.details, null, 2)}
            </pre>
          </td>
        </tr>
      )}
    </>
  )
}
