'use client'

import { useEffect, useState } from 'react'
import { Ic } from '@/components/ui/Icon'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type LibraryTab = 'media' | 'file'

interface Generation {
  id: string
  type: 'image' | 'video' | 'music'
  model_label: string
  status: string
  output_ref: string | null
  token_cost: number | null
  created_at: string
}

interface FileItem {
  id: string
  filename: string
  mime_type: string | null
  size_bytes: number | null
  scope: string
  context: string
  created_at: string
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const GRADIENT_PALETTES = [
  'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
  'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
  'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
  'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)',
  'linear-gradient(135deg, #fa709a 0%, #fee140 100%)',
  'linear-gradient(135deg, #a18cd1 0%, #fbc2eb 100%)',
]

const TIME_PERIODS = ['All', 'Today', 'Yesterday', 'Previous 7 days', 'Previous 30 days'] as const
const CONTEXT_OPTIONS = ['All', 'Upload', 'Generate'] as const
const SORT_OPTIONS = ['Recent', 'Oldest'] as const

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function periodToRange(period: string): { date_from: string | null; date_to: string | null } {
  const now = new Date()
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const MS_DAY = 86_400_000

  if (period === 'Today') {
    return {
      date_from: todayStart.toISOString(),
      date_to: new Date(todayStart.getTime() + MS_DAY).toISOString(),
    }
  }
  if (period === 'Yesterday') {
    const y = new Date(todayStart.getTime() - MS_DAY)
    return { date_from: y.toISOString(), date_to: todayStart.toISOString() }
  }
  if (period === 'Previous 7 days') {
    return { date_from: new Date(todayStart.getTime() - 7 * MS_DAY).toISOString(), date_to: null }
  }
  if (period === 'Previous 30 days') {
    return { date_from: new Date(todayStart.getTime() - 30 * MS_DAY).toISOString(), date_to: null }
  }
  return { date_from: null, date_to: null }
}

function buildQS(opts: {
  period: string
  context: string
  sort: string
  q?: string
}): string {
  const { period, context, sort, q } = opts
  const { date_from, date_to } = periodToRange(period)
  const p = new URLSearchParams()
  if (date_from) p.set('date_from', date_from)
  if (date_to) p.set('date_to', date_to)
  if (context !== 'All') p.set('context', context.toLowerCase())
  p.set('sort', sort === 'Oldest' ? 'oldest' : 'recent')
  if (q?.trim()) p.set('q', q.trim())
  return p.toString()
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'long', day: 'numeric', year: 'numeric',
  })
}

function gradientForId(id: string): string {
  return GRADIENT_PALETTES[Math.abs(id.charCodeAt(0) - 48) % GRADIENT_PALETTES.length]
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Pill-style label + native select (matches the screenshot filter bar). */
function PillSelect({
  label, value, options, onChange,
}: {
  label: string
  value: string
  options: readonly string[]
  onChange: (v: string) => void
}) {
  return (
    <div style={{
      display: 'inline-flex',
      alignItems: 'center',
      border: '1px solid var(--line-2)',
      borderRadius: 'var(--r-md)',
      background: 'var(--surface)',
      padding: '0 4px 0 10px',
      height: 34,
    }}>
      <span style={{ fontSize: 13, color: 'var(--ink-3)', whiteSpace: 'nowrap' }}>{label}:&nbsp;</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          border: 'none',
          background: 'transparent',
          fontSize: 13,
          fontWeight: 500,
          color: 'var(--ink)',
          cursor: 'pointer',
          outline: 'none',
          padding: '0 4px 0 0',
          height: '100%',
        }}
      >
        {options.map((o) => <option key={o}>{o}</option>)}
      </select>
    </div>
  )
}

function Spinner() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: 64 }}>
      <div style={{
        width: 28, height: 28,
        border: '3px solid var(--line-2)',
        borderTopColor: 'var(--accent)',
        borderRadius: '50%',
        animation: 'lib-spin 0.8s linear infinite',
      }} />
    </div>
  )
}

function EmptyState({ text }: { text: string }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', height: 280, color: 'var(--ink-4)', gap: 12,
    }}>
      <Ic.Package size={36} strokeWidth={1.4} />
      <span style={{ fontSize: 14 }}>{text}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// MediaCard — adapted from GenerationCard in StudioPage
// ---------------------------------------------------------------------------

function MediaCard({ gen, onOpen }: { gen: Generation; onOpen: (g: Generation) => void }) {
  const isImage = gen.type === 'image' && gen.status === 'completed' && !!gen.output_ref?.startsWith('data:')
  const isVideo = gen.type === 'video' && gen.status === 'completed' && !!gen.output_ref?.startsWith('data:')
  const isMusic = gen.type === 'music' && gen.status === 'completed' && !!gen.output_ref?.startsWith('data:audio')
  const isMedia = isImage || isVideo || isMusic
  const isProcessing = gen.status === 'processing'
  const typeBadgeColor: Record<string, string> = { image: '#6366f1', video: '#10b981', music: '#f59e0b' }
  const gradBg = gradientForId(gen.id)

  return (
    <div
      style={{
        borderRadius: 'var(--r-md)',
        border: '1px solid var(--line)',
        overflow: 'hidden',
        background: 'var(--surface)',
        cursor: isMedia ? 'pointer' : 'default',
        transition: 'box-shadow 0.12s',
      }}
      onClick={isMedia ? () => onOpen(gen) : undefined}
      onMouseEnter={isMedia ? (e) => (e.currentTarget.style.boxShadow = 'var(--shadow-2)') : undefined}
      onMouseLeave={isMedia ? (e) => (e.currentTarget.style.boxShadow = 'none') : undefined}
    >
      {isImage ? (
        <img
          src={gen.output_ref!}
          alt="Generated"
          style={{ width: '100%', display: 'block', aspectRatio: '1/1', objectFit: 'cover' }}
        />
      ) : isVideo ? (
        <div style={{ position: 'relative', width: '100%', aspectRatio: '16/9', background: '#000' }}>
          <video
            src={gen.output_ref!}
            muted
            preload="metadata"
            style={{ width: '100%', height: '100%', display: 'block', objectFit: 'cover', pointerEvents: 'none' }}
          />
          <div style={{
            position: 'absolute', inset: 0, display: 'grid', placeItems: 'center',
            background: 'rgba(0,0,0,.2)',
          }}>
            <div style={{
              width: 44, height: 44, borderRadius: '50%',
              background: 'rgba(255,255,255,.85)',
              display: 'grid', placeItems: 'center',
            }}>
              <Ic.play size={18} style={{ color: '#111', marginLeft: 3 }} />
            </div>
          </div>
        </div>
      ) : isMusic ? (
        <div style={{ width: '100%', background: gradBg, padding: '16px 12px', boxSizing: 'border-box' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <Ic.globe size={16} style={{ color: 'rgba(255,255,255,0.9)', flexShrink: 0 }} />
            <span style={{ fontSize: 12, fontWeight: 600, color: 'rgba(255,255,255,0.9)' }}>
              30s clip · Lyria 3 Clip
            </span>
          </div>
          <div style={{ display: 'grid', placeItems: 'center', height: 56 }}>
            <div style={{
              width: 44, height: 44, borderRadius: '50%',
              background: 'rgba(255,255,255,.2)',
              border: '2px solid rgba(255,255,255,.7)',
              display: 'grid', placeItems: 'center',
            }}>
              <Ic.play size={18} style={{ color: '#fff', marginLeft: 3 }} />
            </div>
          </div>
        </div>
      ) : (
        <div style={{
          width: '100%', aspectRatio: isProcessing ? '16/9' : '1/1',
          background: gradBg, display: 'grid', placeItems: 'center',
        }}>
          {isProcessing ? (
            <div style={{ textAlign: 'center', color: 'rgba(255,255,255,0.9)' }}>
              <div style={{
                width: 28, height: 28, border: '3px solid rgba(255,255,255,0.4)',
                borderTopColor: '#fff', borderRadius: '50%',
                animation: 'lib-spin 0.8s linear infinite', margin: '0 auto 6px',
              }} />
              <span style={{ fontSize: 11, fontWeight: 500 }}>Generating…</span>
            </div>
          ) : (
            <>
              {gen.type === 'video' && <Ic.cpu size={28} style={{ color: 'rgba(255,255,255,0.8)' }} />}
              {gen.type === 'music' && <Ic.globe size={28} style={{ color: 'rgba(255,255,255,0.8)' }} />}
              {gen.status === 'failed' && (
                <span style={{ color: 'rgba(255,255,255,0.7)', fontSize: 11 }}>Failed</span>
              )}
            </>
          )}
        </div>
      )}

      <div style={{ padding: '8px 10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
          <span style={{
            fontSize: 10, fontWeight: 600, color: '#fff',
            background: typeBadgeColor[gen.type] ?? '#888',
            padding: '1px 7px', borderRadius: 99, textTransform: 'capitalize',
          }}>{gen.type}</span>
          {gen.status === 'mocked' && (
            <span style={{ fontSize: 10, color: 'var(--ink-4)', fontStyle: 'italic' }}>preview</span>
          )}
          {gen.status === 'processing' && (
            <span style={{ fontSize: 10, color: 'var(--ink-4)', fontStyle: 'italic' }}>processing…</span>
          )}
          {gen.status === 'failed' && (
            <span style={{ fontSize: 10, color: '#ef4444', fontStyle: 'italic' }}>failed</span>
          )}
        </div>
        <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>{gen.model_label}</div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// MediaLightbox — adapted from ImageLightbox in StudioPage
// ---------------------------------------------------------------------------

function MediaLightbox({ gen, onClose }: { gen: Generation; onClose: () => void }) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,.65)',
        display: 'grid', placeItems: 'center', zIndex: 50, padding: 24,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--surface)', borderRadius: 'var(--r-md)',
          border: '1px solid var(--line)', overflow: 'hidden',
          maxWidth: gen.type === 'video' ? 960 : gen.type === 'music' ? 440 : 720,
          width: '100%', display: 'flex', flexDirection: 'column',
        }}
      >
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '12px 16px', borderBottom: '1px solid var(--line)', flexShrink: 0,
        }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>
            Preview — {gen.model_label}
          </span>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-3)', padding: 4, lineHeight: 0 }}
          >
            <Ic.x size={16} />
          </button>
        </div>

        <div style={{ background: '#000', display: 'flex', justifyContent: 'center' }}>
          {gen.type === 'video' ? (
            <video
              src={gen.output_ref!}
              controls
              autoPlay
              style={{ maxHeight: '80vh', maxWidth: '100%', display: 'block' }}
            />
          ) : gen.type === 'music' ? (
            <div style={{ width: '100%', background: gradientForId(gen.id), padding: '28px 24px', boxSizing: 'border-box' }}>
              <audio controls autoPlay src={gen.output_ref!} style={{ width: '100%' }} />
            </div>
          ) : (
            <img
              src={gen.output_ref!}
              alt="Generated image"
              style={{ maxHeight: '70vh', maxWidth: '100%', objectFit: 'contain', display: 'block' }}
            />
          )}
        </div>

        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '10px 16px', borderTop: '1px solid var(--line)', gap: 12, flexShrink: 0,
        }}>
          <div style={{ display: 'flex', gap: 16, fontSize: 12, color: 'var(--ink-3)' }}>
            <span><span style={{ fontWeight: 600, color: 'var(--ink-2)' }}>Type</span> {gen.type}</span>
            <span><span style={{ fontWeight: 600, color: 'var(--ink-2)' }}>Status</span> {gen.status}</span>
            {gen.token_cost != null && (
              <span><span style={{ fontWeight: 600, color: 'var(--ink-2)' }}>Tokens</span> {gen.token_cost.toLocaleString()}</span>
            )}
            <span>{new Date(gen.created_at).toLocaleString()}</span>
          </div>
          <a
            href={gen.output_ref!}
            download={`library-${gen.id}.${gen.type === 'video' ? 'mp4' : gen.type === 'music' ? 'mp3' : 'png'}`}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '7px 14px', borderRadius: 'var(--r-md)',
              background: 'var(--accent)', color: '#fff',
              fontSize: 13, fontWeight: 600, textDecoration: 'none', flexShrink: 0,
            }}
          >
            <Ic.download size={13} /> Download
          </a>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// FileIcon
// ---------------------------------------------------------------------------

function FileIcon({ mime }: { mime: string | null }) {
  const bg = mime?.includes('pdf') ? '#ef4444' : 'var(--accent)'
  return (
    <div style={{
      width: 28, height: 28, borderRadius: 5,
      background: bg, display: 'grid', placeItems: 'center', flexShrink: 0,
    }}>
      <Ic.file size={14} style={{ color: '#fff' }} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function LibraryPage() {
  const [tab, setTab] = useState<LibraryTab>('media')
  const [period, setPeriod] = useState('All')
  const [context, setContext] = useState('All')
  const [sort, setSort] = useState('Recent')

  // Media tab
  const [generations, setGenerations] = useState<Generation[]>([])
  const [mediaLoading, setMediaLoading] = useState(false)
  const [lightbox, setLightbox] = useState<Generation | null>(null)

  // File tab
  const [files, setFiles] = useState<FileItem[]>([])
  const [fileLoading, setFileLoading] = useState(false)
  const [search, setSearch] = useState('')

  // Single effect — re-runs whenever any filter or tab changes
  useEffect(() => {
    let cancelled = false

    async function load() {
      if (tab === 'media') {
        setMediaLoading(true)
        try {
          const qs = buildQS({ period, context, sort })
          const res = await fetch(`/api/library/media${qs ? '?' + qs : ''}`, { cache: 'no-store' })
          if (!cancelled && res.ok) setGenerations(await res.json())
        } finally {
          if (!cancelled) setMediaLoading(false)
        }
      } else {
        setFileLoading(true)
        try {
          const qs = buildQS({ period, context, sort, q: search })
          const res = await fetch(`/api/library/files${qs ? '?' + qs : ''}`, { cache: 'no-store' })
          if (!cancelled && res.ok) {
            const data = await res.json()
            setFiles(data.items ?? [])
          }
        } finally {
          if (!cancelled) setFileLoading(false)
        }
      }
    }

    load()
    return () => { cancelled = true }
  }, [tab, period, context, sort, search])

  async function handleDelete(id: string) {
    await fetch(`/api/library/files/${id}`, { method: 'DELETE' })
    setFiles((prev) => prev.filter((f) => f.id !== id))
  }

  const isMediaLoading = tab === 'media' && mediaLoading
  const isFileLoading = tab === 'file' && fileLoading

  return (
    <div style={{ padding: '32px 36px', maxWidth: 1100, margin: '0 auto' }}>
      {/* ── Header ── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--ink)', margin: 0 }}>Library</h1>

        {/* Segmented tab control: Image & Video | File */}
        <div style={{
          display: 'flex', border: '1px solid var(--line-2)',
          borderRadius: 'var(--r-md)', overflow: 'hidden',
        }}>
          {(['media', 'file'] as LibraryTab[]).map((t) => {
            const active = t === tab
            return (
              <button
                key={t}
                onClick={() => setTab(t)}
                style={{
                  padding: '8px 22px', border: 'none',
                  background: active ? 'var(--surface-2)' : 'var(--surface)',
                  color: active ? 'var(--ink)' : 'var(--ink-3)',
                  fontWeight: active ? 600 : 400,
                  fontSize: 13.5, cursor: 'pointer', transition: 'all 0.1s',
                }}
              >
                {t === 'media' ? 'Image & Video' : 'File'}
              </button>
            )
          })}
        </div>
      </div>

      {/* ── File search bar (file tab only) ── */}
      {tab === 'file' && (
        <div style={{ marginBottom: 14 }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 10,
            border: '1px solid var(--line-2)', borderRadius: 'var(--r-md)',
            padding: '0 14px', background: 'var(--surface)', height: 40,
          }}>
            <Ic.search size={15} style={{ color: 'var(--ink-4)', flexShrink: 0 }} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search..."
              style={{
                border: 'none', outline: 'none', background: 'transparent',
                fontSize: 13.5, color: 'var(--ink)', flex: 1,
              }}
            />
          </div>
        </div>
      )}

      {/* ── Filter bar ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24 }}>
        <PillSelect
          label="Time Period"
          value={period}
          options={TIME_PERIODS}
          onChange={setPeriod}
        />
        <PillSelect
          label="Context"
          value={context}
          options={CONTEXT_OPTIONS}
          onChange={setContext}
        />
        <div style={{ flex: 1 }} />
        <PillSelect
          label="Sort"
          value={sort}
          options={SORT_OPTIONS}
          onChange={setSort}
        />
      </div>

      {/* ── Content ── */}

      {/* Media grid */}
      {tab === 'media' && (
        isMediaLoading ? <Spinner /> :
        generations.length === 0 ? (
          <EmptyState text="No media found" />
        ) : (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
            gap: 14,
          }}>
            {generations.map((g) => (
              <MediaCard key={g.id} gen={g} onOpen={setLightbox} />
            ))}
          </div>
        )
      )}

      {/* File table */}
      {tab === 'file' && (
        isFileLoading ? <Spinner /> :
        files.length === 0 ? (
          <EmptyState text="No files found" />
        ) : (
          <table>
            <thead>
              <tr>
                <th style={{
                  textAlign: 'left', padding: '8px 12px',
                  fontSize: 12.5, fontWeight: 600, color: 'var(--ink-3)',
                  background: 'var(--surface-2)',
                  borderBottom: '1px solid var(--line)',
                }}>Name</th>
                <th style={{
                  textAlign: 'left', padding: '8px 12px',
                  fontSize: 12.5, fontWeight: 600, color: 'var(--ink-3)',
                  background: 'var(--surface-2)',
                  borderBottom: '1px solid var(--line)',
                }}>Date created</th>
                <th style={{
                  textAlign: 'left', padding: '8px 12px',
                  fontSize: 12.5, fontWeight: 600, color: 'var(--ink-3)',
                  background: 'var(--surface-2)',
                  borderBottom: '1px solid var(--line)',
                }}>Context</th>
                <th style={{ background: 'var(--surface-2)', borderBottom: '1px solid var(--line)' }} />
              </tr>
            </thead>
            <tbody>
              {files.map((f) => (
                <tr
                  key={f.id}
                  style={{ borderBottom: '1px solid var(--line)' }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--surface-2)')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                >
                  <td style={{ padding: '10px 12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <FileIcon mime={f.mime_type} />
                      <span style={{ fontSize: 13.5, color: 'var(--ink)', fontWeight: 500 }}>
                        {f.filename}
                      </span>
                    </div>
                  </td>
                  <td style={{ padding: '10px 12px', fontSize: 13, color: 'var(--ink-2)' }}>
                    {formatDate(f.created_at)}
                  </td>
                  <td style={{ padding: '10px 12px', fontSize: 13, color: 'var(--accent)' }}>
                    {f.context || f.scope}
                  </td>
                  <td style={{ padding: '10px 12px', textAlign: 'right' }}>
                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 4 }}>
                      {/* Download */}
                      <a
                        href={`/api/library/files/${f.id}/download`}
                        download={f.filename}
                        title="Download"
                        style={{
                          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                          padding: 7, borderRadius: 'var(--r-sm)',
                          color: 'var(--ink-3)', textDecoration: 'none', lineHeight: 0,
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--surface-2)')}
                        onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                      >
                        <Ic.download size={15} />
                      </a>
                      {/* Delete */}
                      <button
                        onClick={() => handleDelete(f.id)}
                        title="Delete"
                        style={{
                          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                          padding: 7, borderRadius: 'var(--r-sm)',
                          border: 'none', background: 'transparent',
                          color: 'var(--ink-3)', cursor: 'pointer', lineHeight: 0,
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--surface-2)'; e.currentTarget.style.color = '#ef4444' }}
                        onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--ink-3)' }}
                      >
                        <Ic.trash size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}

      {/* Lightbox */}
      {lightbox && <MediaLightbox gen={lightbox} onClose={() => setLightbox(null)} />}

      {/* Keyframe for spinner — scoped name to avoid collision with Studio's 'spin' */}
      <style>{`@keyframes lib-spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
