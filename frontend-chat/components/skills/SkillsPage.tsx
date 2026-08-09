'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Ic } from '@/components/ui/Icon'
import SkillDetailModal from './SkillDetailModal'
import CreateWithAIModal from './CreateWithAIModal'
import { useIsMobile } from '@/lib/useIsMobile'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SkillItem {
  id: string
  user_id: string
  name: string
  description: string | null
  instructions: string | null
  source_markdown: string | null
  enabled: boolean
  visibility: string
  category: string | null
  created_at: string
  updated_at: string
}

type SkillTab = 'all' | 'mine'

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

const menuItemStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 8,
  width: '100%', padding: '10px 14px',
  background: 'none', border: 'none', textAlign: 'left',
  fontSize: 13, color: 'var(--ink-2)', cursor: 'pointer',
}

// ---------------------------------------------------------------------------
// Add ▾ menu — "Create with AI" / "Write skill instructions" / "Upload a skill"
// ---------------------------------------------------------------------------

function AddMenu({
  onCreateWithAI, onWrite, onUpload,
}: {
  onCreateWithAI: () => void
  onWrite: () => void
  onUpload: () => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          padding: '7px 16px',
          borderRadius: 'var(--r-md)',
          border: 'none',
          background: 'linear-gradient(135deg, #ff6b9d, #c44dff)',
          color: '#fff',
          fontWeight: 700,
          fontSize: 13,
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <Ic.plus size={14} strokeWidth={2.5} />
        Add
        <Ic.chevron size={12} strokeWidth={2.5} />
      </button>
      {open && (
        <div style={{
          position: 'absolute', right: 0, top: '110%',
          background: 'var(--surface)', border: '1px solid var(--line)',
          borderRadius: 'var(--r-md)', boxShadow: 'var(--shadow-2)',
          minWidth: 210, zIndex: 10, overflow: 'hidden',
        }}>
          <button onClick={() => { setOpen(false); onCreateWithAI() }} style={menuItemStyle}>
            <Ic.spark size={14} strokeWidth={2} />
            Create with AI
          </button>
          <button onClick={() => { setOpen(false); onWrite() }} style={menuItemStyle}>
            <Ic.file size={14} strokeWidth={2} />
            Write skill instructions
          </button>
          <button onClick={() => { setOpen(false); onUpload() }} style={menuItemStyle}>
            <Ic.upload size={14} strokeWidth={2} />
            Upload a skill
          </button>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Upload modal — paste or choose a SKILL.md
// ---------------------------------------------------------------------------

function UploadModal({ onClose, onUploaded }: { onClose: () => void; onUploaded: (s: SkillItem) => void }) {
  const [markdown, setMarkdown] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setMarkdown(await file.text())
  }

  async function handleSubmit() {
    if (!markdown.trim()) { setError('Paste or choose a SKILL.md file first.'); return }
    setSubmitting(true)
    setError('')
    try {
      const res = await fetch('/api/skills/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ markdown }),
      })
      if (res.ok) {
        onUploaded(await res.json())
      } else {
        const data = await res.json().catch(() => ({}))
        setError(data.detail ?? 'Upload failed.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 16 }}>
      <div onClick={e => e.stopPropagation()} style={{ background: 'var(--surface)', borderRadius: 'var(--r-xl)', width: '100%', maxWidth: 560, padding: 24, boxShadow: 'var(--shadow-3)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div style={{ fontWeight: 700, fontSize: 16, color: 'var(--ink)' }}>Upload a skill</div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-3)' }}>
            <Ic.x size={18} strokeWidth={2} />
          </button>
        </div>
        <div style={{ fontSize: 12.5, color: 'var(--ink-3)', marginBottom: 12 }}>
          Choose a SKILL.md file, or paste its contents below. The frontmatter <code>name</code> and{' '}
          <code>description</code> fields are read automatically.
        </div>
        <input type="file" accept=".md,text/markdown,text/plain" style={{ marginBottom: 10 }} onChange={handleFile} />
        <textarea
          value={markdown}
          onChange={e => setMarkdown(e.target.value)}
          placeholder={'---\nname: weekly-status-report\ndescription: Generate weekly status reports.\n---\n\nSummarize recent work...'}
          rows={10}
          style={{ width: '100%', padding: '9px 12px', borderRadius: 'var(--r-md)', border: '1px solid var(--line)', background: 'var(--surface)', fontSize: 12.5, fontFamily: 'monospace', color: 'var(--ink)', boxSizing: 'border-box', resize: 'vertical' }}
        />
        {error && <div style={{ fontSize: 12, color: '#e53e3e', marginTop: 8 }}>{error}</div>}
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 16 }}>
          <button onClick={onClose} disabled={submitting} style={{ padding: '9px 18px', borderRadius: 'var(--r-md)', border: '1px solid var(--line-2)', background: 'var(--surface)', color: 'var(--ink-2)', fontWeight: 600, fontSize: 13, cursor: 'pointer' }}>
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            style={{ padding: '9px 22px', borderRadius: 'var(--r-md)', border: 'none', background: submitting ? 'var(--ink-4)' : 'linear-gradient(135deg, #ff6b9d, #c44dff)', color: '#fff', fontWeight: 700, fontSize: 13, cursor: submitting ? 'not-allowed' : 'pointer' }}
          >
            {submitting ? 'Uploading…' : 'Upload'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// EmptyState
// ---------------------------------------------------------------------------

function EmptyState({ tab }: { tab: SkillTab }) {
  const router = useRouter()
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 280, gap: 10, color: 'var(--ink-3)' }}>
      <div style={{ width: 52, height: 52, borderRadius: '50%', border: '2px dashed var(--line-2)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--ink-4)' }}>
        <Ic.layers size={20} strokeWidth={1.5} />
      </div>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--ink-2)' }}>
          {tab === 'mine' ? 'No skills yet' : 'No skills found'}
        </div>
        <div style={{ fontSize: 12.5, color: 'var(--ink-4)', marginTop: 4 }}>
          {tab === 'mine' ? "You haven't created any skills yet." : 'Try a different search.'}
        </div>
      </div>
      {tab === 'mine' && (
        <button
          onClick={() => router.push('/skills/create')}
          style={{ padding: '9px 20px', borderRadius: 'var(--r-md)', border: 'none', background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 13, cursor: 'pointer' }}
        >
          Write your first skill
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// SkillsPage (main)
// ---------------------------------------------------------------------------

export default function SkillsPage() {
  const router = useRouter()
  const isMobile = useIsMobile()
  const [tab, setTab] = useState<SkillTab>('all')
  const [skills, setSkills] = useState<SkillItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [q, setQ] = useState('')
  const [detail, setDetail] = useState<SkillItem | null>(null)
  const [showUpload, setShowUpload] = useState(false)
  const [showCreateWithAI, setShowCreateWithAI] = useState(false)

  const loadSkills = useCallback(async () => {
    setLoading(true)
    try {
      const scope = tab === 'mine' ? 'mine' : 'all'
      const qs = new URLSearchParams({ scope, limit: '200' })
      if (q.trim()) qs.set('q', q.trim())
      const res = await fetch(`/api/skills?${qs}`, { cache: 'no-store' })
      if (res.ok) {
        const data = await res.json()
        setSkills(data.items ?? [])
        setTotal(data.total ?? 0)
      }
    } finally {
      setLoading(false)
    }
  }, [tab, q])

  useEffect(() => {
    const timer = setTimeout(loadSkills, q ? 300 : 0)
    return () => clearTimeout(timer)
  }, [loadSkills, q])

  function handleUploaded(skill: SkillItem) {
    setShowUpload(false)
    setSkills(prev => [skill, ...prev])
    setTotal(t => t + 1)
    setDetail(skill)
  }

  function handleToggled(updated: SkillItem) {
    setSkills(prev => prev.map(s => (s.id === updated.id ? updated : s)))
    setDetail(updated)
  }

  function handleDeleted(id: string) {
    setSkills(prev => prev.filter(s => s.id !== id))
    setTotal(t => Math.max(0, t - 1))
    setDetail(null)
  }

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1000, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink)', margin: 0 }}>Skills</h1>
        <AddMenu
          onCreateWithAI={() => setShowCreateWithAI(true)}
          onWrite={() => router.push('/skills/create')}
          onUpload={() => setShowUpload(true)}
        />
      </div>

      {/* Tab indicator */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 18, fontSize: 13.5, color: 'var(--ink-3)' }}>
        <button
          onClick={() => setTab('all')}
          style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', fontWeight: tab === 'all' ? 700 : 500, color: tab === 'all' ? 'var(--ink)' : 'var(--ink-3)', borderBottom: tab === 'all' ? '2px solid var(--accent)' : '2px solid transparent', paddingBottom: 4 }}
        >
          All Skills
        </button>
        <span style={{ color: 'var(--line-2)' }}>•</span>
        <button
          onClick={() => setTab('mine')}
          style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', fontWeight: tab === 'mine' ? 700 : 500, color: tab === 'mine' ? 'var(--ink)' : 'var(--ink-3)', borderBottom: tab === 'mine' ? '2px solid var(--accent)' : '2px solid transparent', paddingBottom: 4 }}
        >
          My Skills
        </button>
      </div>

      {/* Search */}
      <div style={{ position: 'relative', marginBottom: 16, maxWidth: 380 }}>
        <Ic.search size={14} strokeWidth={2} style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', color: 'var(--ink-4)' }} />
        <input
          value={q}
          onChange={e => setQ(e.target.value)}
          placeholder="Search skills..."
          style={{ width: '100%', padding: '8px 12px 8px 34px', borderRadius: 'var(--r-md)', border: '1px solid var(--line)', background: 'var(--surface)', fontSize: 13.5, color: 'var(--ink)', outline: 'none', boxSizing: 'border-box' }}
        />
      </div>

      {!loading && (
        <div style={{ fontSize: 13, color: 'var(--ink-3)', marginBottom: 12 }}>
          {total} skill{total !== 1 ? 's' : ''} available
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div style={{ color: 'var(--ink-3)', fontSize: 13 }}>Loading…</div>
      ) : skills.length === 0 ? (
        <EmptyState tab={tab} />
      ) : (
        <div style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', overflow: 'hidden' }}>
          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr 90px' : '1fr 140px 90px', background: 'var(--surface-2)', padding: '10px 16px', fontSize: 12, fontWeight: 700, color: 'var(--ink-3)' }}>
            <span>Skill</span>
            {!isMobile && <span>Last updated</span>}
            <span>Status</span>
          </div>
          {skills.map(skill => (
            <div
              key={skill.id}
              onClick={() => setDetail(skill)}
              style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr 90px' : '1fr 140px 90px', padding: '12px 16px', borderTop: '1px solid var(--line)', alignItems: 'center', cursor: 'pointer', background: 'var(--surface)' }}
              onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.background = 'var(--surface-2)' }}
              onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.background = 'var(--surface)' }}
            >
              <div>
                <div style={{ fontWeight: 600, fontSize: 13.5, color: 'var(--ink)', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Ic.layers size={13} strokeWidth={2} style={{ color: 'var(--ink-4)' }} />
                  {skill.name}
                </div>
                {skill.description && (
                  <div style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {skill.description}
                  </div>
                )}
              </div>
              {!isMobile && <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>{fmtDate(skill.updated_at)}</span>}
              <span style={{
                fontSize: 11.5, fontWeight: 600, padding: '2px 10px', borderRadius: 99, width: 'fit-content',
                color: skill.enabled ? '#0f7a3e' : 'var(--ink-4)',
                background: skill.enabled ? '#e3f8ec' : 'var(--surface-2)',
              }}>
                {skill.enabled ? 'On' : 'Off'}
              </span>
            </div>
          ))}
        </div>
      )}

      {detail && (
        <SkillDetailModal skill={detail} onClose={() => setDetail(null)} onToggled={handleToggled} onDeleted={handleDeleted} />
      )}
      {showUpload && <UploadModal onClose={() => setShowUpload(false)} onUploaded={handleUploaded} />}
      {showCreateWithAI && <CreateWithAIModal onClose={() => setShowCreateWithAI(false)} />}
    </div>
  )
}
