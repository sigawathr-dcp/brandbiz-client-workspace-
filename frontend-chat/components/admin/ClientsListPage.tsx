'use client'

import { useEffect, useState } from 'react'

interface Workspace {
  id: string
  name: string
  slug: string
  kind: string
  contact_name: string | null
  contact_email: string | null
  created_at: string
}

// Client Workspaces admin screen (Phase 5/6, D21/D22) — backs the design's
// "Client workspaces" table in Internal mode. Provisioning a workspace here
// is the prerequisite for everything else in Phase 5: an invite can only be
// minted against a workspace that exists.
export default function ClientsListPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [kind, setKind] = useState<'demo' | 'client'>('demo')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    const res = await fetch('/api/admin/clients', { credentials: 'include', cache: 'no-store' })
    if (res.ok) setWorkspaces(await res.json())
  }

  useEffect(() => {
    load()
  }, [])

  async function create() {
    if (!name.trim() || !slug.trim()) return
    setSaving(true)
    setError('')
    try {
      const res = await fetch('/api/admin/clients', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ name, slug, kind }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError(data.detail || 'Could not create workspace')
        return
      }
      setName('')
      setSlug('')
      setShowForm(false)
      await load()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{ padding: 32, maxWidth: 900, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 14, marginBottom: 20, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink)' }}>Client workspaces</h1>
          <p style={{ fontSize: 13, color: 'var(--ink-3)', marginTop: 4 }}>
            Provision a workspace, then mint an invite link from its detail page.
          </p>
        </div>
        <div style={{ flex: 1 }} />
        <button
          onClick={() => setShowForm((s) => !s)}
          style={{ height: 36, padding: '0 15px', borderRadius: 8, border: 'none', background: 'var(--accent)', color: '#fff', fontSize: 13.5, fontWeight: 500, cursor: 'pointer' }}
        >
          {showForm ? 'Cancel' : 'Provision client'}
        </button>
      </div>

      {showForm && (
        <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 12, padding: 16, marginBottom: 20, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Workspace name (e.g. Common Grounds Co.)"
              style={{ flex: '1 1 220px', height: 36, borderRadius: 7, border: '1px solid var(--line-2)', padding: '0 10px', fontSize: 13.5 }}
            />
            <input
              value={slug}
              onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-'))}
              placeholder="slug (e.g. common-grounds)"
              style={{ flex: '1 1 160px', height: 36, borderRadius: 7, border: '1px solid var(--line-2)', padding: '0 10px', fontSize: 13.5, fontFamily: 'var(--font-mono)' }}
            />
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value as 'demo' | 'client')}
              style={{ height: 36, borderRadius: 7, border: '1px solid var(--line-2)', padding: '0 10px', fontSize: 13.5 }}
            >
              <option value="demo">demo</option>
              <option value="client">client</option>
            </select>
          </div>
          {error && <div style={{ fontSize: 12, color: 'var(--danger)' }}>{error}</div>}
          <div>
            <button
              onClick={create}
              disabled={saving}
              style={{ height: 34, padding: '0 14px', borderRadius: 7, border: 'none', background: 'var(--accent)', color: '#fff', fontSize: 13, fontWeight: 500, cursor: saving ? 'default' : 'pointer' }}
            >
              {saving ? 'Creating…' : 'Create'}
            </button>
          </div>
        </div>
      )}

      {workspaces === null && <div style={{ fontSize: 13, color: 'var(--ink-3)' }}>Loading…</div>}
      {workspaces !== null && workspaces.length === 0 && (
        <div style={{ fontSize: 13, color: 'var(--ink-3)' }}>No workspaces yet.</div>
      )}
      <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 12, overflow: 'hidden' }}>
        {workspaces?.map((w, i) => (
          <a
            key={w.id}
            href={`/clients/${w.id}`}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '12px 16px',
              borderTop: i === 0 ? 'none' : '1px solid var(--line)',
              textDecoration: 'none',
              color: 'inherit',
            }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--ink)' }}>{w.name}</div>
              <div style={{ fontSize: 11.5, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>{w.slug}</div>
            </div>
            <span
              style={{
                fontSize: 11,
                fontWeight: 500,
                color: 'var(--ink-2)',
                background: 'var(--surface-2)',
                border: '1px solid var(--line)',
                borderRadius: 99,
                padding: '2px 8px',
              }}
            >
              {w.kind}
            </span>
          </a>
        ))}
      </div>
    </div>
  )
}
