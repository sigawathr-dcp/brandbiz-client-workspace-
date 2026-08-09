'use client'

import { useState } from 'react'
import type { UserSummary, Department } from '@/lib/admin-api'
import ConfirmDialog from './ConfirmDialog'

const ROLES = ['L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'ADMIN']

interface Props {
  user: UserSummary
  departments: Department[]
  onSave: (userId: string, changes: { role?: string; is_active?: boolean; department_ids?: number[] }) => Promise<void>
  onClose: () => void
}

export default function UserEditModal({ user, departments, onSave, onClose }: Props) {
  const [role, setRole] = useState(user.role)
  const [isActive, setIsActive] = useState(user.is_active)
  const [deptIds, setDeptIds] = useState<number[]>(user.department_ids)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [showConfirm, setShowConfirm] = useState(false)

  const changes: Record<string, unknown> = {}
  if (role !== user.role) changes.role = `${user.role} → ${role}`
  if (isActive !== user.is_active) changes.is_active = `${user.is_active} → ${isActive}`
  const deptChanged = JSON.stringify([...deptIds].sort()) !== JSON.stringify([...user.department_ids].sort())
  if (deptChanged) changes.department_ids = deptIds

  const hasChanges = Object.keys(changes).length > 0
  const confirmDescription = Object.entries(changes).map(([k, v]) => `${k}: ${v}`).join('\n')

  function toggleDept(id: number) {
    setDeptIds(prev => prev.includes(id) ? prev.filter(d => d !== id) : [...prev, id])
  }

  async function handleConfirm() {
    setSaving(true); setError('')
    try {
      const payload: { role?: string; is_active?: boolean; department_ids?: number[] } = {}
      if (role !== user.role) payload.role = role
      if (isActive !== user.is_active) payload.is_active = isActive
      if (deptChanged) payload.department_ids = deptIds
      await onSave(user.id, payload)
      onClose()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unknown error')
      setSaving(false); setShowConfirm(false)
    }
  }

  return (
    <>
      <div style={{ position: 'fixed', inset: 0, zIndex: 100, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, padding: 28, width: 480, maxWidth: '90vw' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
            <h2 style={{ fontSize: 16, fontWeight: 700 }}>Edit User</h2>
            <button className="ghost" onClick={onClose} style={{ padding: '2px 10px' }}>✕</button>
          </div>
          <p style={{ color: 'var(--muted)', fontSize: 12, marginBottom: 20 }}>{user.google_email}</p>
          {error && (
            <div style={{ background: '#450a0a', border: '1px solid var(--danger)', borderRadius: 6, padding: '8px 12px', marginBottom: 16, color: '#fca5a5', fontSize: 13 }}>
              {error}
            </div>
          )}
          <label style={{ display: 'block', marginBottom: 16 }}>
            <span style={{ color: 'var(--muted)', fontSize: 12, display: 'block', marginBottom: 4 }}>Role</span>
            <select value={role} onChange={e => setRole(e.target.value)} style={{ width: '100%' }}>
              {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20 }}>
            <input type="checkbox" checked={isActive} onChange={e => setIsActive(e.target.checked)} style={{ width: 16, height: 16 }} />
            <span style={{ fontSize: 13 }}>Active account</span>
          </label>
          {departments.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <span style={{ color: 'var(--muted)', fontSize: 12, display: 'block', marginBottom: 8 }}>Departments</span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {departments.map(d => (
                  <label key={d.id} style={{ display: 'flex', alignItems: 'center', gap: 6, background: deptIds.includes(d.id) ? '#1e3a5f' : 'transparent', border: '1px solid var(--border)', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 12 }}>
                    <input type="checkbox" checked={deptIds.includes(d.id)} onChange={() => toggleDept(d.id)} style={{ width: 12, height: 12 }} />
                    {d.name}
                  </label>
                ))}
              </div>
            </div>
          )}
          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
            <button className="ghost" onClick={onClose}>Cancel</button>
            <button className="primary" disabled={!hasChanges || saving} onClick={() => setShowConfirm(true)}>
              {saving ? 'Saving…' : 'Save changes'}
            </button>
          </div>
        </div>
      </div>
      {showConfirm && (
        <ConfirmDialog
          title="Confirm user changes"
          description={`Changes take effect on the user's next request:\n\n${confirmDescription}`}
          onConfirm={handleConfirm}
          onCancel={() => setShowConfirm(false)}
        />
      )}
    </>
  )
}
