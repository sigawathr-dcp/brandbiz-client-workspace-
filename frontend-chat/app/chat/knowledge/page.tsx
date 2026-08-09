'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { Ic } from '@/components/ui/Icon'
import StageStepper from '@/components/ui/StageStepper'
import { TIERS } from '@/lib/domain'
import type { TierKey } from '@/lib/domain'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Stage = 'uploading' | 'classifying' | 'embedding' | 'indexed'
type Scope = 'personal' | 'org'

interface DocCard {
  id: string          // file_id from the backend (UUID string)
  name: string
  size: string
  stage: Stage
  tier: TierKey
  scope: Scope
  progress: number    // 0-100 (local animation only)
  embeddingLocal: boolean
}

interface LibraryItem {
  id: string
  name: string
  scope: Scope
  tier: TierKey
  size: string
  date: string
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STAGES: Stage[] = ['uploading', 'classifying', 'embedding', 'indexed']

const STAGE_LABEL: Record<Stage, string> = {
  uploading:   'Uploading',
  classifying: 'Classifying',
  embedding:   'Embedding',
  indexed:     'Indexed',
}

function tierKey(raw: string | null | undefined): TierKey {
  if (!raw) return 'T1'
  if (raw.includes('4')) return 'T4'
  if (raw.includes('3')) return 'T3'
  if (raw.includes('2')) return 'T2'
  return 'T1'
}

function fmtSize(bytes: number | null | undefined): string {
  if (!bytes) return '—'
  if (bytes >= 1_000_000) return (bytes / 1_000_000).toFixed(1) + ' MB'
  return Math.round(bytes / 1024) + ' KB'
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

// ---------------------------------------------------------------------------
// FileGlyph
// ---------------------------------------------------------------------------
function FileGlyph({ name }: { name: string }) {
  const ext = name.split('.').pop()?.toLowerCase() ?? ''
  const color = ext === 'pdf' ? '#e11d48' : ext === 'csv' ? '#16a34a' : ext === 'md' ? '#7c3aed' : 'var(--accent)'
  const letter = ext === 'pdf' ? 'PDF' : ext === 'csv' ? 'CSV' : ext === 'md' ? 'MD' : 'DOC'
  return (
    <div style={{
      width: 36, height: 36, borderRadius: 'var(--r-sm)',
      background: color + '18', display: 'grid', placeItems: 'center',
      flexShrink: 0, fontFamily: 'var(--font-mono)', fontSize: 9,
      fontWeight: 700, color, letterSpacing: '.03em',
    }}>
      {letter}
    </div>
  )
}

// ---------------------------------------------------------------------------
// DocCardView
// ---------------------------------------------------------------------------
function DocCardView({ doc }: { doc: DocCard }) {
  const t = TIERS[doc.tier]
  const isIndexed = doc.stage === 'indexed'
  return (
    <div style={{
      border: '1px solid var(--line)', borderRadius: 'var(--r-md)',
      padding: '14px 16px', background: 'var(--surface)', animation: 'fadeUp .2s ease',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <FileGlyph name={doc.name} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {doc.name}
            </span>
            <span style={{ flexShrink: 0, fontSize: 10.5, fontWeight: 600, color: t.color, background: t.bg, padding: '1px 7px', borderRadius: 99 }}>
              {doc.tier}
            </span>
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--ink-4)', marginTop: 2 }}>
            {doc.size} · Scope: <span style={{ fontWeight: 600 }}>{doc.scope}</span>
            {doc.embeddingLocal && (
              <span style={{ marginLeft: 8, color: 'var(--t3)', fontWeight: 600 }}>· On-prem embeddings</span>
            )}
          </div>
        </div>
        {isIndexed && <Ic.check size={18} strokeWidth={2.2} style={{ color: 'var(--t1)', flexShrink: 0 }} />}
      </div>

      {!isIndexed && (
        <div style={{ marginTop: 10 }}>
          <div style={{ height: 4, borderRadius: 99, background: 'var(--surface-sunk)', overflow: 'hidden' }}>
            <div style={{ width: doc.progress + '%', height: '100%', borderRadius: 99, background: 'var(--accent)', transition: 'width .4s ease' }} />
          </div>
          <StageStepper stages={STAGES} labels={STAGE_LABEL} current={doc.stage} />
        </div>
      )}

      {isIndexed && <StageStepper stages={STAGES} labels={STAGE_LABEL} current={doc.stage} />}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function KnowledgePage() {
  const [processing, setProcessing] = useState<DocCard[]>([])
  const [library, setLibrary] = useState<LibraryItem[]>([])
  const [scope, setScope] = useState<Scope>('personal')
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const pollRef = useRef<Record<string, ReturnType<typeof setInterval>>>({})

  // Load existing indexed files on mount
  useEffect(() => {
    loadLibrary()
    return () => {
      // Clear all poll intervals on unmount
      Object.values(pollRef.current).forEach(clearInterval)
    }
  }, [])

  async function loadLibrary() {
    try {
      const res = await fetch('/api/files')
      if (!res.ok) return
      const data = await res.json()
      const items: LibraryItem[] = (data.items ?? [])
        .filter((f: any) => f.is_processed)
        .map((f: any) => ({
          id: f.id,
          name: f.filename,
          scope: f.scope as Scope,
          tier: tierKey(f.detected_tier),
          size: fmtSize(f.size_bytes),
          date: fmtDate(f.created_at),
        }))
      setLibrary(items)
    } catch {
      // Non-fatal: library shows empty
    }
  }

  function startPolling(fileId: string) {
    // Progress animation stages while waiting for backend
    const STEPS: [Stage, number][] = [
      ['uploading', 25],
      ['classifying', 55],
      ['embedding', 80],
    ]
    let step = 0
    // Advance local stage animation
    const animInterval = setInterval(() => {
      if (step < STEPS.length) {
        const [stage, progress] = STEPS[step++]
        setProcessing(prev => prev.map(d => d.id === fileId ? { ...d, stage, progress } : d))
      } else {
        clearInterval(animInterval)
      }
    }, 1000)

    // Poll backend for is_processed
    const pollInterval = setInterval(async () => {
      try {
        const res = await fetch(`/api/files/${fileId}`)
        if (!res.ok) return
        const status = await res.json()
        if (status.is_processed) {
          clearInterval(pollInterval)
          clearInterval(animInterval)
          delete pollRef.current[fileId]
          setProcessing(prev => prev.map(d =>
            d.id === fileId ? { ...d, stage: 'indexed', progress: 100 } : d
          ))
          // Move to library after brief delay
          setTimeout(() => {
            setProcessing(prev => prev.filter(d => d.id !== fileId))
            loadLibrary()
          }, 1500)
        }
      } catch {
        // Keep polling
      }
    }, 3000)

    pollRef.current[fileId] = pollInterval
  }

  async function uploadFile(file: File) {
    setError(null)
    const form = new FormData()
    form.append('file', file)
    form.append('scope', scope)

    // Add optimistic card immediately
    const tempId = 'pending-' + Math.random().toString(36).slice(2)
    const sizeStr = fmtSize(file.size)
    const tier: TierKey = 'T1' // placeholder until backend responds
    const card: DocCard = {
      id: tempId, name: file.name, size: sizeStr, stage: 'uploading',
      tier, scope, progress: 5, embeddingLocal: false,
    }
    setProcessing(prev => [card, ...prev])

    try {
      const res = await fetch('/api/files', { method: 'POST', body: form })
      if (!res.ok) {
        const body = await res.text()
        setProcessing(prev => prev.filter(d => d.id !== tempId))
        setError(`Upload failed: ${body}`)
        return
      }
      const data = await res.json()
      const realTier = tierKey(data.detected_tier)
      const realScope = (data.scope ?? scope) as Scope

      // Replace temp card with real file_id
      setProcessing(prev => prev.map(d =>
        d.id === tempId ? {
          ...d, id: data.file_id, tier: realTier, scope: realScope,
          stage: 'classifying', progress: 35,
          embeddingLocal: realTier === 'T3' || realTier === 'T4',
        } : d
      ))
      startPolling(data.file_id)
    } catch (err) {
      setProcessing(prev => prev.filter(d => d.id !== tempId))
      setError('Upload failed — check your connection.')
    }
  }

  function handleFiles(files: FileList) {
    Array.from(files).forEach(f => uploadFile(f))
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files)
  }

  const scopedLibrary = library.filter(l => l.scope === scope)
  const indexedCount = scopedLibrary.length
  const processingCount = processing.filter(d => d.stage !== 'indexed').length

  return (
    <div style={{ height: '100%', overflowY: 'auto', background: 'var(--bg)' }}>
      <div style={{ maxWidth: 760, margin: '0 auto', padding: '28px 24px 40px' }}>

        {/* ── Error banner ── */}
        {error && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 9, padding: '10px 14px', marginBottom: 16,
            background: 'var(--t4-bg)', border: '1px solid var(--t4)', borderRadius: 'var(--r-md)',
            fontSize: 12.5, color: 'var(--ink-2)',
          }}>
            <Ic.AlertTriangle size={14} style={{ color: 'var(--t4)', flexShrink: 0 }} />
            <span>{error}</span>
            <button onClick={() => setError(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-4)' }}>✕</button>
          </div>
        )}

        {/* ── Header ── */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 24 }}>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 700, color: 'var(--ink)', margin: 0, letterSpacing: '-.01em' }}>
              Knowledge base
            </h1>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--ink-3)' }}>
              Upload documents — they are classified and embedded before use in chat.
            </p>
          </div>
          <div style={{ display: 'flex', gap: 16, flexShrink: 0 }}>
            {[
              { label: 'Indexed', value: indexedCount },
              { label: 'Processing', value: processingCount },
            ].map(s => (
              <div key={s.label} style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink)', lineHeight: 1 }}>{s.value}</div>
                <div style={{ fontSize: 11, color: 'var(--ink-4)', marginTop: 2 }}>{s.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* ── Scope selector ── */}
        <div style={{ display: 'flex', gap: 6, marginBottom: 16 }}>
          {(['personal', 'org'] as Scope[]).map(s => (
            <button
              key={s}
              onClick={() => setScope(s)}
              style={{
                padding: '6px 16px', borderRadius: 'var(--r-sm)',
                border: `1.5px solid ${scope === s ? 'var(--accent)' : 'var(--line)'}`,
                background: scope === s ? 'var(--accent-weak)' : 'transparent',
                color: scope === s ? 'var(--accent)' : 'var(--ink-2)',
                fontSize: 12.5, fontWeight: 600, cursor: 'pointer', textTransform: 'capitalize',
              }}
            >
              {s === 'org' ? 'Organisation' : 'Personal'}
            </button>
          ))}
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 11.5, color: 'var(--ink-4)', alignSelf: 'center' }}>
            New uploads go to <strong style={{ color: 'var(--ink-2)' }}>{scope === 'org' ? 'Organisation' : 'Personal'}</strong> scope
          </span>
        </div>

        {/* ── Drop zone ── */}
        <div
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
          style={{
            border: `2px dashed ${dragging ? 'var(--accent)' : 'var(--line-2)'}`,
            borderRadius: 'var(--r-lg)', padding: '36px 24px', textAlign: 'center',
            cursor: 'pointer', background: dragging ? 'var(--accent-weak)' : 'var(--surface)',
            transition: 'border-color .2s, background .2s', marginBottom: 24,
          }}
        >
          <input
            ref={fileRef} type="file" multiple
            accept=".pdf,.docx,.txt,.md,.csv"
            style={{ display: 'none' }}
            onChange={e => e.target.files && handleFiles(e.target.files)}
          />
          <Ic.upload size={28} style={{ color: dragging ? 'var(--accent)' : 'var(--ink-3)', display: 'block', margin: '0 auto 12px' }} />
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink)', marginBottom: 4 }}>
            Drop files here or click to browse
          </div>
          <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>
            PDF, DOCX, CSV, MD, TXT · Max 50 MB per file
          </div>
        </div>

        {/* ── Active processing queue ── */}
        {processing.length > 0 && (
          <div style={{ marginBottom: 28 }}>
            <SectionLabel>Processing queue</SectionLabel>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {processing.map(doc => <DocCardView key={doc.id} doc={doc} />)}
            </div>
          </div>
        )}

        {/* ── Library ── */}
        <div>
          <SectionLabel>Indexed documents</SectionLabel>
          {scopedLibrary.length === 0 ? (
            <div style={{ padding: '24px', textAlign: 'center', color: 'var(--ink-4)', fontSize: 13, border: '1px dashed var(--line)', borderRadius: 'var(--r-md)' }}>
              No indexed documents yet. Upload files above to get started.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 1, border: '1px solid var(--line)', borderRadius: 'var(--r-md)', overflow: 'hidden' }}>
              {scopedLibrary.map((lib, i) => {
                const t = TIERS[lib.tier]
                return (
                  <div
                    key={lib.id}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px',
                      background: 'var(--surface)',
                      borderBottom: i < scopedLibrary.length - 1 ? '1px solid var(--line)' : 'none',
                    }}
                  >
                    <FileGlyph name={lib.name} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {lib.name}
                        </span>
                        <span style={{ flexShrink: 0, fontSize: 10.5, fontWeight: 600, color: t.color, background: t.bg, padding: '1px 7px', borderRadius: 99 }}>
                          {lib.tier}
                        </span>
                      </div>
                      <div style={{ fontSize: 11.5, color: 'var(--ink-4)', marginTop: 2 }}>
                        {lib.scope} · {lib.size} · Indexed {lib.date}
                      </div>
                    </div>
                    <Ic.check size={16} strokeWidth={2.2} style={{ color: 'var(--t1)', flexShrink: 0 }} />
                  </div>
                )
              })}
            </div>
          )}
        </div>

      </div>
    </div>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 11, fontWeight: 600, color: 'var(--ink-4)',
      textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 10,
    }}>
      {children}
    </div>
  )
}
