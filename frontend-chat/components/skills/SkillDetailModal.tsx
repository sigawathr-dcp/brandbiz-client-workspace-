'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Ic } from '@/components/ui/Icon'
import type { SkillItem } from './SkillsPage'

interface Props {
  skill: SkillItem
  onClose: () => void
  onToggled: (skill: SkillItem) => void
  onDeleted: (id: string) => void
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function SkillDetailModal({ skill, onClose, onToggled, onDeleted }: Props) {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  async function handleToggle() {
    setBusy(true)
    try {
      const res = await fetch(`/api/skills/${skill.id}/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !skill.enabled }),
      })
      if (res.ok) onToggled(await res.json())
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete() {
    setBusy(true)
    try {
      const res = await fetch(`/api/skills/${skill.id}`, { method: 'DELETE' })
      if (res.ok || res.status === 204) onDeleted(skill.id)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      onClick={onClose}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 16 }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{ background: 'var(--surface)', borderRadius: 'var(--r-xl)', width: '100%', maxWidth: 520, maxHeight: '90vh', overflowY: 'auto', padding: 28, position: 'relative', boxShadow: 'var(--shadow-3)' }}
      >
        <button onClick={onClose} style={{ position: 'absolute', top: 16, right: 16, background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-3)', padding: 4 }}>
          <Ic.x size={18} strokeWidth={2} />
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
          <div style={{ width: 40, height: 40, borderRadius: 10, background: 'var(--surface-2)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--ink-3)', flexShrink: 0 }}>
            <Ic.layers size={18} strokeWidth={1.8} />
          </div>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 700, fontSize: 16, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {skill.name}
            </div>
            <div style={{ fontSize: 11.5, color: 'var(--ink-4)' }}>
              {skill.visibility === 'public' ? 'Public' : 'Personal'} · Updated {fmtDate(skill.updated_at)}
            </div>
          </div>
          <label style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }} title={skill.enabled ? 'Disable skill' : 'Enable skill'}>
            <input
              type="checkbox"
              checked={skill.enabled}
              disabled={busy}
              onChange={handleToggle}
              style={{ width: 32, height: 18, accentColor: 'var(--accent)', cursor: busy ? 'not-allowed' : 'pointer' }}
            />
          </label>
        </div>

        {skill.description && (
          <div style={{ fontSize: 13, color: 'var(--ink-3)', marginTop: 12, lineHeight: 1.5 }}>
            {skill.description}
          </div>
        )}

        <hr style={{ border: 'none', borderTop: '1px solid var(--line)', margin: '16px 0' }} />

        <div style={{ fontSize: 12, color: 'var(--ink-4)', fontWeight: 600, marginBottom: 6 }}>Instructions</div>
        <div style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.6, whiteSpace: 'pre-wrap', background: 'var(--surface-2)', padding: 12, borderRadius: 'var(--r-md)', maxHeight: 260, overflowY: 'auto' }}>
          {skill.instructions || <span style={{ color: 'var(--ink-4)' }}>No instructions.</span>}
        </div>

        <div style={{ fontSize: 11.5, color: 'var(--ink-4)', marginTop: 10 }}>
          Auto-loads when your message matches the description above, or invoke it directly with{' '}
          <code>/{skill.name}</code>.
        </div>

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 20 }}>
          {confirmDelete ? (
            <>
              <button
                onClick={() => setConfirmDelete(false)}
                disabled={busy}
                style={{ padding: '9px 18px', borderRadius: 'var(--r-md)', border: '1px solid var(--line-2)', background: 'var(--surface)', color: 'var(--ink-2)', fontWeight: 600, fontSize: 13, cursor: 'pointer' }}
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                disabled={busy}
                style={{ padding: '9px 18px', borderRadius: 'var(--r-md)', border: 'none', background: '#e53e3e', color: '#fff', fontWeight: 700, fontSize: 13, cursor: busy ? 'not-allowed' : 'pointer' }}
              >
                {busy ? 'Deleting…' : 'Confirm delete'}
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => setConfirmDelete(true)}
                disabled={busy}
                style={{ padding: '9px 18px', borderRadius: 'var(--r-md)', border: '1px solid var(--line-2)', background: 'var(--surface)', color: '#e53e3e', fontWeight: 600, fontSize: 13, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}
              >
                <Ic.trash size={13} strokeWidth={2} />
                Delete
              </button>
              <button
                onClick={() => router.push(`/skills/${skill.id}/edit`)}
                style={{ padding: '9px 20px', borderRadius: 'var(--r-md)', border: 'none', background: 'linear-gradient(135deg, #ff6b9d, #c44dff)', color: '#fff', fontWeight: 700, fontSize: 13, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}
              >
                <Ic.pencil size={13} strokeWidth={2} />
                Edit
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
