'use client'

import { useState, useCallback } from 'react'
import type { UserSummary, Department } from '@/lib/admin-api'
import UserEditModal from './UserEditModal'

const ROLES = ['', 'L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'ADMIN']
const ROLE_BADGE: Record<string, string> = {
  L1: 'badge-l1', L2: 'badge-l2', L3: 'badge-l3',
  L4: 'badge-l4', L5: 'badge-l5', L6: 'badge-l6', ADMIN: 'badge-admin',
}
const LIMIT = 50

interface Props {
  initialItems: UserSummary[]
  initialTotal: number
  departments: Department[]
}

export default function UsersTable({ initialItems, initialTotal, departments }: Props) {
  const [items, setItems] = useState(initialItems)
  const [total, setTotal] = useState(initialTotal)
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [activeFilter, setActiveFilter] = useState('')
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(false)
  const [editingUser, setEditingUser] = useState<UserSummary | null>(null)

  const fetchPage = useCallback(async (opts: { search?: string; role?: string; is_active?: string; offset?: number } = {}) => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (opts.search) params.set('search', opts.search)
      if (opts.role) params.set('role', opts.role)
      if (opts.is_active !== undefined && opts.is_active !== '') params.set('is_active', opts.is_active)
      params.set('limit', String(LIMIT))
      params.set('offset', String(opts.offset ?? 0))
      const res = await fetch(`/api/admin/users?${params}`)
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setItems(data.items); setTotal(data.total)
    } finally {
      setLoading(false)
    }
  }, [])

  function applyFilters() {
    setOffset(0)
    fetchPage({ search, role: roleFilter, is_active: activeFilter, offset: 0 })
  }

  async function handleSave(userId: string, changes: { role?: string; is_active?: boolean; department_ids?: number[] }) {
    const res = await fetch(`/api/admin/users/${userId}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(changes),
    })
    if (!res.ok) throw new Error(await res.text())
    const updated: UserSummary = await res.json()
    setItems(prev => prev.map(u => u.id === userId ? updated : u))
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <input placeholder="Search email…" value={search} onChange={e => setSearch(e.target.value)} onKeyDown={e => e.key === 'Enter' && applyFilters()} style={{ flexGrow: 1, minWidth: 200 }} />
        <select value={roleFilter} onChange={e => setRoleFilter(e.target.value)}>
          {ROLES.map(r => <option key={r} value={r}>{r || 'All roles'}</option>)}
        </select>
        <select value={activeFilter} onChange={e => setActiveFilter(e.target.value)}>
          <option value="">Any status</option>
          <option value="true">Active</option>
          <option value="false">Inactive</option>
        </select>
        <button className="primary" onClick={applyFilters}>{loading ? 'Loading…' : 'Filter'}</button>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th>Email</th>
              <th>Name</th>
              <th>Role</th>
              <th>Status</th>
              <th>Departments</th>
              <th>Last login</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {items.map(u => {
              const deptNames = u.department_ids.map(id => departments.find(d => d.id === id)?.name ?? String(id))
              return (
                <tr key={u.id}>
                  <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{u.google_email}</td>
                  <td>{u.display_name ?? '—'}</td>
                  <td><span className={`badge ${ROLE_BADGE[u.role] ?? ''}`}>{u.role}</span></td>
                  <td><span className={`badge ${u.is_active ? 'badge-active' : 'badge-inactive'}`}>{u.is_active ? 'active' : 'inactive'}</span></td>
                  <td style={{ color: 'var(--muted)', fontSize: 12 }}>{deptNames.join(', ') || '—'}</td>
                  <td style={{ color: 'var(--muted)', fontSize: 12 }}>{u.last_login_at ? new Date(u.last_login_at).toLocaleDateString() : '—'}</td>
                  <td><button className="ghost" onClick={() => setEditingUser(u)}>Edit</button></td>
                </tr>
              )
            })}
            {items.length === 0 && (
              <tr><td colSpan={7} style={{ textAlign: 'center', color: 'var(--muted)', padding: 32 }}>No users found</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 16 }}>
        <span style={{ color: 'var(--muted)', fontSize: 12 }}>
          {total} total · showing {offset + 1}–{Math.min(offset + LIMIT, total)}
        </span>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="ghost" disabled={offset === 0} onClick={() => { const n = Math.max(0, offset - LIMIT); setOffset(n); fetchPage({ search, role: roleFilter, is_active: activeFilter, offset: n }) }}>← Prev</button>
          <button className="ghost" disabled={offset + LIMIT >= total} onClick={() => { const n = offset + LIMIT; setOffset(n); fetchPage({ search, role: roleFilter, is_active: activeFilter, offset: n }) }}>Next →</button>
        </div>
      </div>

      {editingUser && (
        <UserEditModal user={editingUser} departments={departments} onSave={handleSave} onClose={() => setEditingUser(null)} />
      )}
    </div>
  )
}
