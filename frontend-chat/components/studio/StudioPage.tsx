'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { Ic } from '@/components/ui/Icon'
import { useIsMobile } from '@/lib/useIsMobile'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Mode = 'image' | 'video' | 'music'
type ResultTab = 'my_studio' | 'templates'

interface Generation {
  id: string
  type: Mode
  model_label: string
  status: string
  output_ref: string | null
  token_cost: number | null
  created_at: string
  parent_id?: string | null
}

// Returned only by GET /studio/generations/{id} — includes the decrypted
// prompt and settings so the detail view can be edited and resubmitted.
interface GenerationDetail extends Generation {
  prompt: string
  settings: Record<string, unknown> | null
}

interface Template {
  id: string
  type: string
  title: string
  preview_image?: string | null
  description: string
}

// ---------------------------------------------------------------------------
// Mode config
// ---------------------------------------------------------------------------

const MODE_CONFIG = {
  image: {
    label: 'Image',
    model: 'Gemini Flash Image',
    costBanner: 'Generating an image: 200k - 1M tokens',
    costBtn: '200k - 1M',
    promptLabel: 'Prompt',
    promptPlaceholder: 'Describe the scene you imagine',
  },
  video: {
    label: 'Video',
    model: 'Veo 3.1 Lite',
    costBanner: 'Generating a video: 2M - 5M tokens',
    costBtn: '2M - 5M',
    promptLabel: 'Prompt',
    promptPlaceholder: 'Describe the scene you imagine',
  },
  music: {
    label: 'Music',
    model: 'Lyria 3 Clip Preview',
    costBanner: 'Generating a 30s music clip: 50k - 150k tokens',
    costBtn: '50k - 150k',
    promptLabel: 'Style',
    promptPlaceholder: 'Describe the music you want to generate',
  },
} as const

// Gradient colours for music / video template cards
const GRADIENT_PALETTES = [
  'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
  'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
  'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
  'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)',
  'linear-gradient(135deg, #fa709a 0%, #fee140 100%)',
  'linear-gradient(135deg, #a18cd1 0%, #fbc2eb 100%)',
]

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ModeTabs({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) {
  return (
    <div style={{ display: 'flex', gap: 6 }}>
      {(['image', 'video', 'music'] as Mode[]).map((m) => {
        const active = m === mode
        return (
          <button
            key={m}
            onClick={() => onChange(m)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '7px 14px',
              borderRadius: 'var(--r-md)',
              border: active ? '1.5px solid var(--accent)' : '1.5px solid var(--line-2)',
              background: active ? 'var(--accent-weak)' : 'var(--surface)',
              color: active ? 'var(--accent)' : 'var(--ink-2)',
              fontWeight: active ? 600 : 500,
              fontSize: 13.5,
              cursor: 'pointer',
              transition: 'all 0.12s',
            }}
          >
            {m === 'image' && <Ic.spark size={14} />}
            {m === 'video' && <Ic.cpu size={14} />}
            {m === 'music' && <Ic.globe size={14} />}
            {MODE_CONFIG[m].label}
          </button>
        )
      })}
    </div>
  )
}

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!value)}
      style={{
        width: 36,
        height: 20,
        borderRadius: 10,
        border: 'none',
        background: value ? 'var(--accent)' : 'var(--line-2)',
        position: 'relative',
        cursor: 'pointer',
        flexShrink: 0,
        transition: 'background 0.15s',
      }}
    >
      <span style={{
        position: 'absolute',
        top: 2,
        left: value ? 18 : 2,
        width: 16,
        height: 16,
        borderRadius: '50%',
        background: '#fff',
        transition: 'left 0.15s',
        boxShadow: '0 1px 3px rgba(0,0,0,.2)',
      }} />
    </button>
  )
}

function SelectField({
  label, value, options, onChange,
}: {
  label: string
  value: string
  options: string[]
  onChange: (v: string) => void
}) {
  return (
    <div style={{ flex: 1 }}>
      <div style={{ fontSize: 12, color: 'var(--ink-3)', marginBottom: 5 }}>{label}</div>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          width: '100%',
          padding: '8px 10px',
          borderRadius: 'var(--r-md)',
          border: '1px solid var(--line-2)',
          background: 'var(--surface)',
          color: 'var(--ink)',
          fontSize: 13,
          cursor: 'pointer',
        }}
      >
        {options.map((o) => <option key={o}>{o}</option>)}
      </select>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

// ---------------------------------------------------------------------------
// Advanced Settings panels per mode
// ---------------------------------------------------------------------------

function ImageAdvanced({
  settings, onChange, references, onReferencesChange,
}: {
  settings: Record<string, unknown>
  onChange: (k: string, v: unknown) => void
  references: string[]
  onReferencesChange: (refs: string[]) => void
}) {
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const batchSize = (settings.batch_size as number) ?? 1

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return
    const remaining = 10 - references.length
    if (remaining <= 0) return
    const toRead = Array.from(files).filter((f) => f.type.startsWith('image/')).slice(0, remaining)
    const dataUrls = await Promise.all(toRead.map(fileToDataUrl))
    onReferencesChange([...references, ...dataUrls])
  }

  function handleRemove(idx: number) {
    onReferencesChange(references.filter((_, i) => i !== idx))
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ fontSize: 12.5, color: 'var(--ink-3)', marginBottom: 2 }}>References</div>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        multiple
        style={{ display: 'none' }}
        onChange={(e) => handleFiles(e.target.files)}
        onClick={(e) => { (e.target as HTMLInputElement).value = '' }}
      />
      <div
        onClick={() => fileInputRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); handleFiles(e.dataTransfer.files) }}
        style={{
          border: '1.5px dashed var(--line-2)',
          borderRadius: 'var(--r-md)',
          padding: '12px 16px',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          color: 'var(--ink-3)',
          fontSize: 13,
          cursor: references.length >= 10 ? 'not-allowed' : 'pointer',
          opacity: references.length >= 10 ? 0.5 : 1,
        }}
      >
        <Ic.upload size={15} /> Image
        <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--ink-4)' }}>{references.length} / 10</span>
      </div>
      {references.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {references.map((src, idx) => (
            <div key={idx} style={{ position: 'relative', width: 56, height: 56 }}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={src}
                alt={`ref-${idx + 1}`}
                style={{ width: 56, height: 56, objectFit: 'cover', borderRadius: 'var(--r-sm)', border: '1px solid var(--line-2)' }}
              />
              <button
                onClick={(e) => { e.stopPropagation(); handleRemove(idx) }}
                style={{
                  position: 'absolute', top: -6, right: -6,
                  width: 18, height: 18, borderRadius: '50%',
                  background: 'var(--surface)', border: '1px solid var(--line-2)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  cursor: 'pointer', padding: 0,
                }}
                title="Remove"
              >
                <Ic.x size={10} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', gap: 10 }}>
        <SelectField
          label="Aspect Ratio"
          value={(settings.aspect_ratio as string) ?? '1:1'}
          options={['1:1', '9:16', '16:9', '4:3', '3:4']}
          onChange={(v) => onChange('aspect_ratio', v)}
        />
        <SelectField
          label="Resolution"
          value={(settings.resolution as string) ?? '2K'}
          options={['1K', '2K', '4K']}
          onChange={(v) => onChange('resolution', v)}
        />
      </div>

      <div>
        <div style={{ fontSize: 12, color: 'var(--ink-3)', marginBottom: 6 }}>Batch Size</div>
        <div style={{
          display: 'flex', alignItems: 'center', border: '1px solid var(--line-2)',
          borderRadius: 'var(--r-md)', overflow: 'hidden',
        }}>
          <button
            onClick={() => onChange('batch_size', Math.max(1, batchSize - 1))}
            style={{ padding: '8px 14px', background: 'none', border: 'none', color: 'var(--ink-2)', cursor: 'pointer', fontSize: 16 }}
          >−</button>
          <span style={{ flex: 1, textAlign: 'center', fontSize: 14, color: 'var(--ink)' }}>{batchSize}</span>
          <button
            onClick={() => onChange('batch_size', Math.min(4, batchSize + 1))}
            style={{ padding: '8px 14px', background: 'none', border: 'none', color: 'var(--ink-2)', cursor: 'pointer', fontSize: 16 }}
          >+</button>
        </div>
      </div>
    </div>
  )
}

function VideoAdvanced({
  settings, onChange,
}: {
  settings: Record<string, unknown>
  onChange: (k: string, v: unknown) => void
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div>
        <div style={{ fontSize: 12, color: 'var(--ink-3)', marginBottom: 6 }}>Frames</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <select style={{ flex: 1, padding: '7px 10px', borderRadius: 'var(--r-sm)', border: '1px solid var(--line-2)', background: 'var(--surface)', color: 'var(--ink)', fontSize: 13 }}>
            <option>First</option>
          </select>
          <span style={{ color: 'var(--ink-4)', fontSize: 13 }}>›</span>
          <select style={{ flex: 1, padding: '7px 10px', borderRadius: 'var(--r-sm)', border: '1px solid var(--line-2)', background: 'var(--surface)', color: 'var(--ink)', fontSize: 13 }}>
            <option>Last</option>
          </select>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 10 }}>
        <SelectField
          label="Aspect Ratio"
          value={(settings.aspect_ratio as string) ?? '16:9'}
          options={['16:9', '9:16']}
          onChange={(v) => onChange('aspect_ratio', v)}
        />
        <SelectField
          label="Resolution"
          value={(settings.resolution as string) ?? '720p'}
          options={['480p', '720p', '1080p']}
          onChange={(v) => onChange('resolution', v)}
        />
      </div>

      <SelectField
        label="Video Length"
        value={(settings.video_length as string) ?? '8s'}
        options={['4s', '6s', '8s']}
        onChange={(v) => onChange('video_length', v)}
      />

      {([
        ['audio', 'Audio'],
        ['camera_fixed', 'Camera Fixed'],
        ['fast_draft', 'Fast Draft'],
      ] as [string, string][]).map(([key, label]) => (
        <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ flex: 1, fontSize: 13.5, color: 'var(--ink-2)' }}>{label}</span>
          <Toggle
            value={!!(settings[key])}
            onChange={(v) => onChange(key, v)}
          />
        </div>
      ))}
    </div>
  )
}

const MUSIC_STRUCTURE_TAGS = ['Intro', 'Verse', 'Chorus', 'Bridge', 'Outro']
const MUSIC_GENRE_OPTIONS = ['Auto', 'Pop', 'Rock', 'Hip-Hop', 'R&B', 'Jazz', 'Classical', 'Electronic', 'Lo-fi', 'Country']
const MUSIC_BPM_OPTIONS = ['Auto', 'Slow (60-80)', 'Medium (90-110)', 'Upbeat (120-140)', 'Fast (150+)']

function NegativePromptField({ settings, onChange }: {
  settings: Record<string, unknown>
  onChange: (k: string, v: unknown) => void
}) {
  return (
    <div>
      <div style={{ fontSize: 12, color: 'var(--ink-3)', marginBottom: 5 }}>Negative Prompt</div>
      <input
        type="text"
        placeholder="What to exclude from your music"
        value={(settings.negative_prompt as string) ?? ''}
        onChange={(e) => onChange('negative_prompt', e.target.value)}
        style={{
          width: '100%',
          padding: '8px 10px',
          borderRadius: 'var(--r-md)',
          border: '1px solid var(--line-2)',
          background: 'var(--surface)',
          color: 'var(--ink)',
          fontSize: 13,
          boxSizing: 'border-box',
        }}
      />
    </div>
  )
}

function InstrumentalOnlyField({ settings, onChange }: {
  settings: Record<string, unknown>
  onChange: (k: string, v: unknown) => void
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <span style={{ flex: 1, fontSize: 13.5, color: 'var(--ink-2)' }}>Instrumental Only</span>
      <Toggle
        value={!!(settings.instrumental_only)}
        onChange={(v) => onChange('instrumental_only', v)}
      />
    </div>
  )
}

function MusicAdvanced({
  settings, onChange,
}: {
  settings: Record<string, unknown>
  onChange: (k: string, v: unknown) => void
}) {
  const tab = (settings.music_tab as string) ?? 'general'
  const instrumentalOnly = !!(settings.instrumental_only)
  const vocalGender = (settings.music_vocal_gender as string) ?? 'auto'

  function insertStructureTag(label: string) {
    const current = (settings.music_detailed_prompt as string) ?? ''
    const marker = `[${label}]`
    const next = current.trim().length > 0 ? `${current}\n${marker}\n` : `${marker}\n`
    onChange('music_detailed_prompt', next)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{
        display: 'flex',
        border: '1px solid var(--line-2)',
        borderRadius: 'var(--r-md)',
        overflow: 'hidden',
      }}>
        {['General', 'Custom'].map((t) => {
          const active = tab === t.toLowerCase()
          return (
            <button
              key={t}
              onClick={() => onChange('music_tab', t.toLowerCase())}
              style={{
                flex: 1,
                padding: '7px',
                border: 'none',
                background: active ? 'var(--surface-2)' : 'transparent',
                color: active ? 'var(--ink)' : 'var(--ink-3)',
                fontWeight: active ? 600 : 400,
                fontSize: 13,
                cursor: 'pointer',
              }}
            >{t}</button>
          )
        })}
      </div>

      {tab === 'general' && (
        <>
          <NegativePromptField settings={settings} onChange={onChange} />

          <div>
            <div style={{ fontSize: 12, color: 'var(--ink-3)', marginBottom: 3 }}>Duration</div>
            <div style={{ fontSize: 13, color: 'var(--ink-2)', padding: '7px 10px', background: 'var(--surface-2)', borderRadius: 'var(--r-md)' }}>
              30s (fixed — Lyria 3 Clip)
            </div>
          </div>

          <InstrumentalOnlyField settings={settings} onChange={onChange} />
        </>
      )}

      {tab === 'custom' && (
        <>
          <div>
            <div style={{ fontSize: 12, color: 'var(--ink-3)', marginBottom: 8 }}>Detailed Prompt</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
              {MUSIC_STRUCTURE_TAGS.map((t) => (
                <button
                  key={t}
                  onClick={() => insertStructureTag(t)}
                  style={{
                    padding: '5px 14px',
                    borderRadius: 99,
                    border: 'none',
                    background: 'var(--accent-weak)',
                    color: 'var(--accent)',
                    fontSize: 12.5,
                    fontWeight: 500,
                    cursor: 'pointer',
                  }}
                >{t}</button>
              ))}
            </div>
            <textarea
              placeholder="Add specific instructions for your music"
              value={(settings.music_detailed_prompt as string) ?? ''}
              onChange={(e) => onChange('music_detailed_prompt', e.target.value)}
              rows={4}
              style={{
                width: '100%',
                padding: '10px',
                borderRadius: 'var(--r-md)',
                border: '1px solid var(--line-2)',
                background: 'var(--surface)',
                color: 'var(--ink)',
                fontSize: 13,
                resize: 'vertical',
                boxSizing: 'border-box',
                fontFamily: 'inherit',
              }}
            />
          </div>

          <NegativePromptField settings={settings} onChange={onChange} />

          <SelectField
            label="Duration"
            value={(settings.music_duration as string) ?? 'Auto'}
            options={['Auto']}
            onChange={(v) => onChange('music_duration', v)}
          />

          <div style={{ display: 'flex', gap: 10 }}>
            <SelectField
              label="Genre"
              value={(settings.music_genre as string) ?? 'Auto'}
              options={MUSIC_GENRE_OPTIONS}
              onChange={(v) => onChange('music_genre', v)}
            />
            <SelectField
              label="BPM"
              value={(settings.music_bpm as string) ?? 'Auto'}
              options={MUSIC_BPM_OPTIONS}
              onChange={(v) => onChange('music_bpm', v)}
            />
          </div>

          <div>
            <div style={{ fontSize: 12, color: 'var(--ink-3)', marginBottom: 5 }}>Vocal Gender</div>
            <div style={{ display: 'flex', gap: 8, opacity: instrumentalOnly ? 0.5 : 1 }}>
              {(['auto', 'male', 'female'] as const).map((g) => {
                const active = vocalGender === g
                return (
                  <button
                    key={g}
                    disabled={instrumentalOnly}
                    onClick={() => onChange('music_vocal_gender', g)}
                    style={{
                      flex: 1,
                      padding: '10px 8px',
                      borderRadius: 'var(--r-md)',
                      border: `1px solid ${active ? 'var(--accent)' : 'var(--line-2)'}`,
                      background: active ? 'var(--accent-weak)' : 'var(--surface)',
                      color: active ? 'var(--accent)' : 'var(--ink-2)',
                      fontSize: 12.5,
                      fontWeight: active ? 600 : 400,
                      cursor: instrumentalOnly ? 'not-allowed' : 'pointer',
                      textTransform: 'capitalize',
                    }}
                  >{g}</button>
                )
              })}
            </div>
          </div>

          <InstrumentalOnlyField settings={settings} onChange={onChange} />
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Results panel
// ---------------------------------------------------------------------------

function GenerationCard({ gen, onOpen }: { gen: Generation; onOpen: (g: Generation) => void }) {
  const isImage = gen.type === 'image' && gen.status === 'completed' && gen.output_ref?.startsWith('data:')
  const isVideo = gen.type === 'video' && gen.status === 'completed' && gen.output_ref?.startsWith('data:')
  const isMusic = gen.type === 'music' && gen.status === 'completed' && !!gen.output_ref?.startsWith('data:audio')
  const isMedia = isImage || isVideo || isMusic
  const isProcessing = gen.status === 'processing'
  const typeBadgeColor = { image: '#6366f1', video: '#10b981', music: '#f59e0b' }[gen.type] ?? '#888'
  const gradientBg = GRADIENT_PALETTES[Math.abs(gen.id.charCodeAt(0) - 48) % GRADIENT_PALETTES.length]

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
        <div style={{
          width: '100%',
          background: gradientBg,
          padding: '16px 12px',
          boxSizing: 'border-box',
        }}>
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
          width: '100%',
          aspectRatio: isProcessing ? '16/9' : '1/1',
          background: gradientBg,
          display: 'grid',
          placeItems: 'center',
        }}>
          {isProcessing ? (
            <div style={{ textAlign: 'center', color: 'rgba(255,255,255,0.9)' }}>
              <div style={{
                width: 28, height: 28, border: '3px solid rgba(255,255,255,0.4)',
                borderTopColor: '#fff', borderRadius: '50%',
                animation: 'spin 0.8s linear infinite', margin: '0 auto 6px',
              }} />
              <span style={{ fontSize: 11, fontWeight: 500 }}>Generating…</span>
            </div>
          ) : (
            <>
              {gen.type === 'video' && <Ic.cpu size={28} style={{ color: 'rgba(255,255,255,0.8)' }} />}
              {gen.type === 'music' && <Ic.globe size={28} style={{ color: 'rgba(255,255,255,0.8)' }} />}
              {gen.type === 'image' && gen.status === 'mocked' && (
                <Ic.spark size={28} style={{ color: 'rgba(255,255,255,0.8)' }} />
              )}
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
            fontSize: 10,
            fontWeight: 600,
            color: '#fff',
            background: typeBadgeColor,
            padding: '1px 7px',
            borderRadius: 99,
            textTransform: 'capitalize',
          }}>{gen.type}</span>
          {gen.parent_id && (
            <span
              title="Edited from an earlier generation — open to see the original"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 3,
                fontSize: 10,
                fontWeight: 600,
                color: 'var(--ink-3)',
                background: 'var(--surface-2)',
                border: '1px solid var(--line-2)',
                padding: '1px 7px',
                borderRadius: 99,
              }}
            >
              <Ic.pencil size={9} />
              edited
            </span>
          )}
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

function TemplateCard({ tpl, onUse }: { tpl: Template; onUse: (tpl: Template) => void }) {
  const [imgError, setImgError] = useState(false)
  const idx = tpl.id.charCodeAt(tpl.id.length - 1) % GRADIENT_PALETTES.length
  const typeBadgeColor = { image: '#6366f1', video: '#10b981', music: '#f59e0b' }[tpl.type] ?? '#888'
  const showImage = !!tpl.preview_image && !imgError

  return (
    <div style={{
      borderRadius: 'var(--r-md)',
      border: '1px solid var(--line)',
      overflow: 'hidden',
      background: 'var(--surface)',
      cursor: 'pointer',
      transition: 'box-shadow 0.12s',
    }}
      onClick={() => onUse(tpl)}
      onMouseEnter={e => (e.currentTarget.style.boxShadow = 'var(--shadow-2)')}
      onMouseLeave={e => (e.currentTarget.style.boxShadow = 'none')}
    >
      {/* Header: preview image or gradient fallback */}
      <div style={{ position: 'relative', width: '100%', aspectRatio: '4/3' }}>
        {showImage ? (
          <img
            src={tpl.preview_image!}
            alt={tpl.title}
            onError={() => setImgError(true)}
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
          />
        ) : (
          <div style={{
            width: '100%',
            height: '100%',
            background: GRADIENT_PALETTES[idx],
            display: 'grid',
            placeItems: 'center',
          }}>
            {tpl.type === 'image' && <Ic.spark size={28} style={{ color: 'rgba(255,255,255,0.8)' }} />}
            {tpl.type === 'video' && <Ic.cpu size={28} style={{ color: 'rgba(255,255,255,0.8)' }} />}
            {tpl.type === 'music' && <Ic.globe size={28} style={{ color: 'rgba(255,255,255,0.8)' }} />}
          </div>
        )}
        {/* Type badge overlays both image and gradient */}
        <span style={{
          position: 'absolute', top: 8, right: 8,
          fontSize: 10, fontWeight: 600,
          color: '#fff',
          background: typeBadgeColor,
          padding: '1px 7px', borderRadius: 99,
          textTransform: 'capitalize',
        }}>{tpl.type}</span>
      </div>

      {/* Body: title + description */}
      <div style={{ padding: '8px 10px' }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)', marginBottom: 3 }}>
          {tpl.title}
        </div>
        <p style={{
          margin: 0,
          fontSize: 11.5,
          color: 'var(--ink-3)',
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
        }}>{tpl.description}</p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function StudioPage() {
  const isMobile = useIsMobile()
  const [mode, setMode] = useState<Mode>('image')
  const [prompt, setPrompt] = useState('')
  const [settings, setSettings] = useState<Record<string, unknown>>({})
  const [references, setReferences] = useState<string[]>([])
  const [advancedOpen, setAdvancedOpen] = useState(true)
  const [resultTab, setResultTab] = useState<ResultTab>('my_studio')
  const [isGenerating, setIsGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [generations, setGenerations] = useState<Generation[]>([])
  const [templates, setTemplates] = useState<Template[]>([])
  const [isLoadingGens, setIsLoadingGens] = useState(true)
  const [isLoadingTmpls, setIsLoadingTmpls] = useState(true)
  const [previewGen, setPreviewGen] = useState<Generation | null>(null)
  const [appliedNote, setAppliedNote] = useState(false)
  const promptRef = useRef<HTMLTextAreaElement | null>(null)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const cfg = MODE_CONFIG[mode]

  const loadGenerations = useCallback(async () => {
    setIsLoadingGens(true)
    try {
      const res = await fetch('/api/studio/generations', { cache: 'no-store' })
      if (res.ok) setGenerations(await res.json())
    } finally {
      setIsLoadingGens(false)
    }
  }, [])

  const loadTemplates = useCallback(async () => {
    setIsLoadingTmpls(true)
    try {
      const res = await fetch('/api/studio/templates', { cache: 'no-store' })
      if (res.ok) setTemplates(await res.json())
    } finally {
      setIsLoadingTmpls(false)
    }
  }, [])

  useEffect(() => {
    loadGenerations()
    loadTemplates()
  }, [loadGenerations, loadTemplates])

  // Poll processing video/music generations every 5 s until all are done
  useEffect(() => {
    const processingIds = generations
      .filter((g) => g.status === 'processing')
      .map((g) => g.id)

    if (processingIds.length === 0) {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current)
        pollTimerRef.current = null
      }
      return
    }

    if (pollTimerRef.current) return  // already polling

    pollTimerRef.current = setInterval(async () => {
      const current = processingIds.slice()  // snapshot
      const updates = await Promise.all(
        current.map(async (id) => {
          try {
            const res = await fetch(`/api/studio/generations/${id}`, { cache: 'no-store' })
            if (res.ok) return (await res.json()) as Generation
          } catch { /* network blip — retry next tick */ }
          return null
        })
      )
      updates.forEach((updated) => {
        if (!updated) return
        setGenerations((prev) =>
          prev.map((g) => (g.id === updated.id ? updated : g))
        )
      })
    }, 5000)

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current)
        pollTimerRef.current = null
      }
    }
  }, [generations])

  function handleSettingChange(k: string, v: unknown) {
    setSettings((s) => ({ ...s, [k]: v }))
  }

  async function handleGenerate() {
    if (!prompt.trim()) return
    setError(null)
    setIsGenerating(true)
    try {
      const res = await fetch('/api/studio/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: mode,
          model_label: cfg.model,
          prompt: prompt.trim(),
          settings,
          references: mode === 'image' ? references : [],
        }),
      })
      const data = await res.json()
      if (!res.ok) {
        const msg = data?.detail?.message ?? data?.detail ?? 'Generation failed.'
        setError(typeof msg === 'string' ? msg : JSON.stringify(msg))
        return
      }
      // Prepend new generation and switch to My Studio
      setGenerations((prev) => [data as Generation, ...prev])
      setReferences([])
      setResultTab('my_studio')
    } catch {
      setError('Network error — please try again.')
    } finally {
      setIsGenerating(false)
    }
  }

  // Called by the detail modal after a successful edit/regenerate submission.
  function handleGenerationEdited(newGen: Generation) {
    setGenerations((prev) => [newGen, ...prev])
    if (newGen.type === 'image') {
      // Image edits are synchronous — show the result immediately in-place.
      setPreviewGen(newGen)
    } else {
      // Video/music edits are async ('processing') — close and let the
      // existing My Studio polling flow pick up the new card.
      setPreviewGen(null)
      setResultTab('my_studio')
    }
  }

  // Called by the detail modal's "Use as Template" button — loads the
  // generation's prompt/settings/output back into the main form.
  function handleUseGenerationAsTemplate(detail: GenerationDetail) {
    setMode(detail.type)
    setPrompt(detail.prompt)
    setSettings(detail.settings ?? {})
    setReferences(detail.type === 'image' && detail.output_ref ? [detail.output_ref] : [])
    setError(null)
    setPreviewGen(null)
    setAppliedNote(true)
    setTimeout(() => setAppliedNote(false), 2000)
    setTimeout(() => {
      promptRef.current?.focus()
      promptRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 0)
  }

  function handleUseTemplate(tpl: Template) {
    setMode(tpl.type as Mode)
    setPrompt(tpl.description)
    setError(null)
    setAppliedNote(true)
    setTimeout(() => setAppliedNote(false), 2000)
    setTimeout(() => {
      promptRef.current?.focus()
      promptRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 0)
  }

  // Filter templates by current mode when on templates tab
  const visibleTemplates = resultTab === 'templates'
    ? templates.filter((t) => t.type === mode)
    : []

  return (
    <div style={{
      display: 'flex',
      flexDirection: isMobile ? 'column' : 'row',
      height: isMobile ? 'auto' : '100%',
      overflow: isMobile ? 'visible' : 'hidden',
    }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
      {/* ── Left panel — form ─────────────────────────────────────── */}
      <div style={{
        width: isMobile ? '100%' : 480,
        flexShrink: 0,
        borderRight: isMobile ? 'none' : '1px solid var(--line)',
        borderBottom: isMobile ? '1px solid var(--line)' : 'none',
        display: 'flex',
        flexDirection: 'column',
        overflow: isMobile ? 'visible' : 'hidden',
      }}>
        <div style={{ flex: 1, overflowY: 'auto', padding: '28px 24px 16px' }}>
          {/* Header */}
          <div style={{ marginBottom: 20 }}>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: 'var(--ink)', letterSpacing: '-.02em' }}>
              AI Studio
            </h1>
            <p style={{ margin: '4px 0 0', fontSize: 13.5, color: 'var(--ink-3)' }}>
              Turn ideas into stunning AI visuals, videos, and music.
            </p>
          </div>

          {/* Mode tabs */}
          <div style={{ marginBottom: 16 }}>
            <ModeTabs mode={mode} onChange={(m) => { setMode(m); setSettings({}); setReferences([]); setError(null) }} />
          </div>

          {/* Token cost banner */}
          <div style={{
            background: 'var(--surface-2)',
            border: '1px solid var(--line)',
            borderRadius: 'var(--r-md)',
            padding: '8px 12px',
            fontSize: 13,
            color: 'var(--ink-3)',
            marginBottom: 18,
          }}>
            {cfg.costBanner}
          </div>

          {/* Model dropdown */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)', marginBottom: 6 }}>Model</div>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '9px 12px',
              borderRadius: 'var(--r-md)',
              border: '1px solid var(--line-2)',
              background: 'var(--surface)',
              fontSize: 13.5,
              color: 'var(--ink)',
            }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)', display: 'inline-block' }} />
                {cfg.model}
              </span>
              <Ic.chevron size={14} style={{ color: 'var(--ink-4)' }} />
            </div>
          </div>

          {/* Prompt / Style */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)' }}>{cfg.promptLabel}</span>
              {appliedNote && (
                <span style={{ fontSize: 11.5, color: 'var(--accent)', fontWeight: 500 }}>
                  ✓ Template applied
                </span>
              )}
            </div>
            <div style={{ position: 'relative' }}>
              <textarea
                ref={promptRef}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder={cfg.promptPlaceholder}
                rows={4}
                style={{
                  width: '100%',
                  padding: '10px 40px 10px 12px',
                  borderRadius: 'var(--r-md)',
                  border: '1px solid var(--line-2)',
                  background: 'var(--surface)',
                  color: 'var(--ink)',
                  fontSize: 13.5,
                  resize: 'vertical',
                  minHeight: 100,
                  fontFamily: 'inherit',
                  boxSizing: 'border-box',
                }}
              />
              <button
                title="Clear"
                onClick={() => setPrompt('')}
                style={{
                  position: 'absolute', top: 8, right: 8,
                  background: 'none', border: 'none', cursor: 'pointer',
                  color: 'var(--ink-4)', padding: 2,
                }}
              >
                <Ic.x size={14} />
              </button>
            </div>
          </div>

          {/* Advanced Settings */}
          <div style={{
            border: '1px solid var(--line-2)',
            borderRadius: 'var(--r-md)',
            overflow: 'hidden',
            marginBottom: 16,
          }}>
            <button
              onClick={() => setAdvancedOpen((o) => !o)}
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '10px 14px',
                background: 'var(--surface)',
                border: 'none',
                cursor: 'pointer',
                color: 'var(--ink)',
                fontWeight: 600,
                fontSize: 13.5,
              }}
            >
              <Ic.sliders size={15} />
              <span style={{ flex: 1, textAlign: 'left' }}>Advanced Setting</span>
              {advancedOpen
                ? <Ic.chevron size={14} style={{ transform: 'rotate(180deg)', color: 'var(--ink-3)' }} />
                : <Ic.chevron size={14} style={{ color: 'var(--ink-3)' }} />
              }
            </button>
            {advancedOpen && (
              <div style={{ padding: '14px 14px 16px', borderTop: '1px solid var(--line)' }}>
                {mode === 'image' && <ImageAdvanced settings={settings} onChange={handleSettingChange} references={references} onReferencesChange={setReferences} />}
                {mode === 'video' && <VideoAdvanced settings={settings} onChange={handleSettingChange} />}
                {mode === 'music' && <MusicAdvanced settings={settings} onChange={handleSettingChange} />}
              </div>
            )}
          </div>

          {/* Error */}
          {error && (
            <div style={{
              background: 'color-mix(in srgb, #ef4444 10%, transparent)',
              border: '1px solid #ef4444',
              borderRadius: 'var(--r-md)',
              padding: '10px 12px',
              fontSize: 13,
              color: '#dc2626',
              marginBottom: 12,
            }}>
              <Ic.alert size={14} style={{ marginRight: 6, verticalAlign: 'text-bottom' }} />
              {error}
            </div>
          )}
        </div>

        {/* Generate button — pinned at bottom */}
        <div style={{ padding: '12px 24px 16px', borderTop: '1px solid var(--line)', flexShrink: 0 }}>
          <button
            onClick={handleGenerate}
            disabled={isGenerating || !prompt.trim()}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              padding: '12px',
              borderRadius: 'var(--r-md)',
              border: 'none',
              background: isGenerating || !prompt.trim() ? 'var(--surface-2)' : 'var(--accent)',
              color: isGenerating || !prompt.trim() ? 'var(--ink-4)' : '#fff',
              fontWeight: 600,
              fontSize: 14,
              cursor: isGenerating || !prompt.trim() ? 'not-allowed' : 'pointer',
              transition: 'background 0.12s',
            }}
          >
            <Ic.spark size={15} />
            {isGenerating ? 'Generating…' : `Generate`}
            {!isGenerating && (
              <span style={{ fontSize: 12, opacity: 0.8, marginLeft: 2 }}>{cfg.costBtn}</span>
            )}
          </button>
        </div>
      </div>

      {/* ── Detail / edit modal ──────────────────────────────────── */}
      {previewGen && (
        <GenerationDetailModal
          gen={previewGen}
          onClose={() => setPreviewGen(null)}
          onGenerated={handleGenerationEdited}
          onUseAsTemplate={handleUseGenerationAsTemplate}
          onOpenGeneration={(g) => setPreviewGen(g)}
        />
      )}

      {/* ── Right panel — results ──────────────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: isMobile ? 'visible' : 'hidden', minHeight: isMobile ? 400 : undefined }}>
        {/* Result tabs */}
        <div style={{
          padding: '18px 24px 0',
          display: 'flex',
          gap: 4,
          borderBottom: '1px solid var(--line)',
          flexShrink: 0,
        }}>
          {(['my_studio', 'templates'] as ResultTab[]).map((t) => (
            <button
              key={t}
              onClick={() => setResultTab(t)}
              style={{
                padding: '8px 20px',
                borderRadius: 'var(--r-md) var(--r-md) 0 0',
                border: 'none',
                background: resultTab === t ? 'var(--surface-2)' : 'transparent',
                color: resultTab === t ? 'var(--ink)' : 'var(--ink-3)',
                fontWeight: resultTab === t ? 600 : 500,
                fontSize: 13.5,
                cursor: 'pointer',
                borderBottom: resultTab === t ? '2px solid var(--accent)' : '2px solid transparent',
              }}
            >
              {t === 'my_studio' ? 'My Studio' : 'Templates'}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: 24 }}>
          {resultTab === 'my_studio' ? (
            isLoadingGens ? (
              <EmptyState icon={<Ic.clock size={32} />} text="Loading…" />
            ) : generations.length === 0 ? (
              <EmptyState icon={<Ic.spark size={32} />} text="No generation history found" />
            ) : (
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
                gap: 14,
              }}>
                {generations.map((g) => <GenerationCard key={g.id} gen={g} onOpen={setPreviewGen} />)}
              </div>
            )
          ) : (
            // Templates tab
            isLoadingTmpls ? (
              <EmptyState icon={<Ic.clock size={32} />} text="Loading templates…" />
            ) : visibleTemplates.length === 0 ? (
              <EmptyState icon={<Ic.spark size={32} />} text="No templates found" />
            ) : (
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
                gap: 14,
              }}>
                {visibleTemplates.map((t) => (
                  <TemplateCard key={t.id} tpl={t} onUse={handleUseTemplate} />
                ))}
              </div>
            )
          )}
        </div>
      </div>
    </div>
  )
}

function EmptyState({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '60%',
      color: 'var(--ink-4)',
      gap: 10,
    }}>
      {icon}
      <span style={{ fontSize: 14 }}>{text}</span>
    </div>
  )
}

// Compact row in the detail modal linking an edited generation back to the
// generation it was derived from (thumbnail + original prompt, click to open).
function ParentGenerationLink({ parent, onOpen }: {
  parent: GenerationDetail
  onOpen: (g: Generation) => void
}) {
  // Same media guard as GenerationCard — the modal's media pane needs a data URL.
  const hasMedia = parent.status === 'completed' && !!parent.output_ref?.startsWith('data:')
  const isImage = parent.type === 'image' && hasMedia
  const isVideo = parent.type === 'video' && hasMedia
  const gradientBg = GRADIENT_PALETTES[Math.abs(parent.id.charCodeAt(0) - 48) % GRADIENT_PALETTES.length]
  const fallbackIcon = parent.type === 'video' ? <Ic.cpu size={18} style={{ color: 'rgba(255,255,255,0.85)' }} />
    : parent.type === 'music' ? <Ic.globe size={18} style={{ color: 'rgba(255,255,255,0.85)' }} />
    : <Ic.spark size={18} style={{ color: 'rgba(255,255,255,0.85)' }} />

  return (
    <div>
      <div style={{ fontSize: 12, color: 'var(--ink-3)', marginBottom: 4 }}>Edited from</div>
      <div
        role={hasMedia ? 'button' : undefined}
        title={hasMedia ? 'View original' : undefined}
        onClick={hasMedia ? () => onOpen(parent) : undefined}
        onMouseEnter={hasMedia ? (e) => (e.currentTarget.style.boxShadow = 'var(--shadow-2)') : undefined}
        onMouseLeave={hasMedia ? (e) => (e.currentTarget.style.boxShadow = 'none') : undefined}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: 8,
          borderRadius: 'var(--r-md)',
          border: '1px solid var(--line-2)',
          background: 'var(--surface-2)',
          cursor: hasMedia ? 'pointer' : 'default',
          transition: 'box-shadow 0.12s',
        }}
      >
        <div style={{
          width: 56, height: 56, flexShrink: 0,
          borderRadius: 8, overflow: 'hidden', position: 'relative',
          background: isImage || isVideo ? '#000' : gradientBg,
          display: 'grid', placeItems: 'center',
        }}>
          {isImage ? (
            <img
              src={parent.output_ref!}
              alt="Original"
              style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
            />
          ) : isVideo ? (
            <>
              <video
                src={parent.output_ref!}
                muted
                preload="metadata"
                style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block', pointerEvents: 'none' }}
              />
              <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', background: 'rgba(0,0,0,.2)' }}>
                <Ic.play size={16} style={{ color: '#fff' }} />
              </div>
            </>
          ) : (
            fallbackIcon
          )}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: 12.5,
            color: 'var(--ink-2)',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}>
            {parent.prompt}
          </div>
          <div style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 2 }}>
            {parent.model_label}
            {hasMedia && <span> · View original</span>}
          </div>
        </div>
        {hasMedia && (
          <Ic.chevron size={14} style={{ color: 'var(--ink-3)', flexShrink: 0, transform: 'rotate(-90deg)' }} />
        )}
      </div>
    </div>
  )
}

function GenerationDetailModal({
  gen, onClose, onGenerated, onUseAsTemplate, onOpenGeneration,
}: {
  gen: Generation
  onClose: () => void
  onGenerated: (newGen: Generation) => void
  onUseAsTemplate: (detail: GenerationDetail) => void
  onOpenGeneration: (g: Generation) => void
}) {
  const [detail, setDetail] = useState<GenerationDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(true)
  const [parent, setParent] = useState<GenerationDetail | null>(null)
  const [editPrompt, setEditPrompt] = useState('')
  const [editSettings, setEditSettings] = useState<Record<string, unknown>>({})
  const [editReferences, setEditReferences] = useState<string[]>([])
  const [editAdvancedOpen, setEditAdvancedOpen] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)

  const isImageEdit = gen.type === 'image'

  // Close on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // Load the decrypted prompt + settings whenever we're showing a different generation.
  useEffect(() => {
    let cancelled = false
    setLoadingDetail(true)
    setDetail(null)
    setEditReferences([])
    setEditError(null)
    setEditAdvancedOpen(false)
    fetch(`/api/studio/generations/${gen.id}`, { cache: 'no-store' })
      .then((res) => (res.ok ? res.json() : null))
      .then((data: GenerationDetail | null) => {
        if (cancelled || !data) return
        setDetail(data)
        setEditPrompt(gen.type === 'image' ? '' : data.prompt)
        setEditSettings(data.settings ?? {})
      })
      .finally(() => { if (!cancelled) setLoadingDetail(false) })
    return () => { cancelled = true }
  }, [gen.id, gen.type])

  // Load the parent generation (if any) so the "Edited from" section can show
  // the original media + prompt. Any failure just hides the section.
  useEffect(() => {
    setParent(null)
    if (!gen.parent_id) return
    let cancelled = false
    fetch(`/api/studio/generations/${gen.parent_id}`, { cache: 'no-store' })
      .then((res) => (res.ok ? res.json() : null))
      .then((data: GenerationDetail | null) => {
        if (!cancelled && data) setParent(data)
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [gen.parent_id])

  function handleEditSettingChange(k: string, v: unknown) {
    setEditSettings((s) => ({ ...s, [k]: v }))
  }

  async function handleEditSubmit() {
    if (!editPrompt.trim()) return
    setIsSubmitting(true)
    setEditError(null)
    try {
      const body: Record<string, unknown> = {
        type: gen.type,
        model_label: gen.model_label,
        prompt: editPrompt.trim(),
        settings: editSettings,
        parent_id: gen.id,
      }
      if (isImageEdit) {
        body.references = [gen.output_ref, ...editReferences].filter(Boolean)
      }
      const res = await fetch('/api/studio/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      if (!res.ok) {
        const msg = data?.detail?.message ?? data?.detail ?? 'Edit failed.'
        setEditError(typeof msg === 'string' ? msg : JSON.stringify(msg))
        return
      }
      onGenerated(data as Generation)
    } catch {
      setEditError('Network error — please try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const formattedDate = new Date(gen.created_at).toLocaleString()

  return (
    // Overlay — click outside to close
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,.65)',
        display: 'grid',
        placeItems: 'center',
        zIndex: 50,
        padding: 24,
      }}
    >
      {/* Inner card — stop propagation so clicking inside doesn't close */}
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--surface)',
          borderRadius: 'var(--r-md)',
          border: '1px solid var(--line)',
          overflow: 'hidden',
          maxWidth: 1040,
          width: '100%',
          maxHeight: '88vh',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Top bar: title + close */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          borderBottom: '1px solid var(--line)',
          flexShrink: 0,
        }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>
            Preview — {gen.model_label}
          </span>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--ink-3)',
              padding: 4,
              lineHeight: 0,
            }}
          >
            <Ic.x size={16} />
          </button>
        </div>

        {/* Body: media (left) + info/edit (right) */}
        <div style={{ display: 'flex', flex: 1, overflow: 'hidden', flexWrap: 'wrap' }}>
          {/* Media */}
          <div style={{ flex: '1 1 380px', background: '#000', display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 260 }}>
            {gen.type === 'video' ? (
              <video
                key={gen.id}
                src={gen.output_ref!}
                controls
                autoPlay
                style={{ maxHeight: '78vh', maxWidth: '100%', display: 'block' }}
              />
            ) : gen.type === 'music' ? (
              <div style={{ width: '100%', background: GRADIENT_PALETTES[Math.abs(gen.id.charCodeAt(0) - 48) % GRADIENT_PALETTES.length], padding: '28px 24px', boxSizing: 'border-box' }}>
                <audio key={gen.id} controls autoPlay src={gen.output_ref!} style={{ width: '100%' }} />
              </div>
            ) : (
              <img
                key={gen.id}
                src={gen.output_ref!}
                alt="Generated"
                style={{ maxHeight: '78vh', maxWidth: '100%', objectFit: 'contain', display: 'block' }}
              />
            )}
          </div>

          {/* Info + edit panel */}
          <div style={{
            flex: '1 1 340px',
            maxWidth: 400,
            display: 'flex',
            flexDirection: 'column',
            borderLeft: '1px solid var(--line)',
            overflowY: 'auto',
          }}>
            {/* Meta + download */}
            <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--line)' }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, fontSize: 12, color: 'var(--ink-3)', marginBottom: 10 }}>
                <span style={{ textTransform: 'capitalize' }}>
                  <span style={{ fontWeight: 600, color: 'var(--ink-2)' }}>Type</span> {gen.type}
                </span>
                <span>
                  <span style={{ fontWeight: 600, color: 'var(--ink-2)' }}>Status</span> {gen.status}
                </span>
                {gen.token_cost != null && (
                  <span>
                    <span style={{ fontWeight: 600, color: 'var(--ink-2)' }}>Tokens</span>{' '}
                    {gen.token_cost.toLocaleString()}
                  </span>
                )}
                <span>{formattedDate}</span>
              </div>
              <a
                href={gen.output_ref!}
                download={`studio-${gen.id}.${gen.type === 'video' ? 'mp4' : gen.type === 'music' ? 'mp3' : 'png'}`}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '7px 14px',
                  borderRadius: 'var(--r-md)',
                  background: 'var(--surface-2)',
                  border: '1px solid var(--line-2)',
                  color: 'var(--ink)',
                  fontSize: 13,
                  fontWeight: 600,
                  textDecoration: 'none',
                }}
              >
                <Ic.download size={13} />
                Download
              </a>
            </div>

            {/* Edit form */}
            <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 12, flex: 1 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--ink)' }}>Edit</div>

              {loadingDetail ? (
                <div style={{ fontSize: 13, color: 'var(--ink-4)' }}>Loading…</div>
              ) : !detail ? (
                <div style={{ fontSize: 13, color: 'var(--ink-4)' }}>Couldn't load details.</div>
              ) : (
                <>
                  {parent && (
                    <ParentGenerationLink parent={parent} onOpen={onOpenGeneration} />
                  )}

                  {isImageEdit && (
                    <div>
                      <div style={{ fontSize: 12, color: 'var(--ink-3)', marginBottom: 4 }}>
                        {gen.parent_id ? 'Prompt used for this edit' : 'Original prompt'}
                      </div>
                      <div style={{ fontSize: 12.5, color: 'var(--ink-2)', background: 'var(--surface-2)', borderRadius: 'var(--r-md)', padding: '8px 10px', maxHeight: 72, overflowY: 'auto' }}>
                        {detail.prompt}
                      </div>
                    </div>
                  )}

                  <div>
                    <div style={{ fontSize: 12, color: 'var(--ink-3)', marginBottom: 5 }}>
                      {isImageEdit ? 'Describe your changes' : MODE_CONFIG[gen.type].promptLabel}
                    </div>
                    <textarea
                      value={editPrompt}
                      onChange={(e) => setEditPrompt(e.target.value)}
                      placeholder={isImageEdit ? 'e.g. make the sky sunset orange' : MODE_CONFIG[gen.type].promptPlaceholder}
                      rows={4}
                      style={{
                        width: '100%',
                        padding: '10px 12px',
                        borderRadius: 'var(--r-md)',
                        border: '1px solid var(--line-2)',
                        background: 'var(--surface)',
                        color: 'var(--ink)',
                        fontSize: 13,
                        resize: 'vertical',
                        fontFamily: 'inherit',
                        boxSizing: 'border-box',
                      }}
                    />
                  </div>

                  <div style={{ border: '1px solid var(--line-2)', borderRadius: 'var(--r-md)', overflow: 'hidden' }}>
                    <button
                      onClick={() => setEditAdvancedOpen((o) => !o)}
                      style={{
                        width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                        padding: '8px 12px', background: 'var(--surface)', border: 'none',
                        cursor: 'pointer', color: 'var(--ink)', fontWeight: 600, fontSize: 13,
                      }}
                    >
                      <Ic.sliders size={14} />
                      <span style={{ flex: 1, textAlign: 'left' }}>Advanced Setting</span>
                      <Ic.chevron size={13} style={{ color: 'var(--ink-3)', transform: editAdvancedOpen ? 'rotate(180deg)' : undefined }} />
                    </button>
                    {editAdvancedOpen && (
                      <div style={{ padding: '12px 12px 14px', borderTop: '1px solid var(--line)' }}>
                        {gen.type === 'image' && (
                          <ImageAdvanced settings={editSettings} onChange={handleEditSettingChange} references={editReferences} onReferencesChange={setEditReferences} />
                        )}
                        {gen.type === 'video' && (
                          <VideoAdvanced settings={editSettings} onChange={handleEditSettingChange} />
                        )}
                        {gen.type === 'music' && (
                          <MusicAdvanced settings={editSettings} onChange={handleEditSettingChange} />
                        )}
                      </div>
                    )}
                  </div>

                  {editError && (
                    <div style={{
                      background: 'color-mix(in srgb, #ef4444 10%, transparent)',
                      border: '1px solid #ef4444',
                      borderRadius: 'var(--r-md)',
                      padding: '8px 10px',
                      fontSize: 12.5,
                      color: '#dc2626',
                    }}>
                      <Ic.alert size={13} style={{ marginRight: 5, verticalAlign: 'text-bottom' }} />
                      {editError}
                    </div>
                  )}

                  <button
                    onClick={handleEditSubmit}
                    disabled={isSubmitting || !editPrompt.trim()}
                    style={{
                      width: '100%',
                      display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                      padding: '11px',
                      borderRadius: 'var(--r-md)',
                      border: 'none',
                      background: isSubmitting || !editPrompt.trim() ? 'var(--surface-2)' : 'var(--accent)',
                      color: isSubmitting || !editPrompt.trim() ? 'var(--ink-4)' : '#fff',
                      fontWeight: 600,
                      fontSize: 13.5,
                      cursor: isSubmitting || !editPrompt.trim() ? 'not-allowed' : 'pointer',
                    }}
                  >
                    <Ic.spark size={14} />
                    {isSubmitting ? 'Working…' : isImageEdit ? 'Generate Edit' : 'Regenerate'}
                  </button>

                  <button
                    onClick={() => onUseAsTemplate(detail)}
                    style={{
                      width: '100%',
                      padding: '9px',
                      borderRadius: 'var(--r-md)',
                      border: '1px solid var(--line-2)',
                      background: 'var(--surface)',
                      color: 'var(--ink-2)',
                      fontWeight: 500,
                      fontSize: 13,
                      cursor: 'pointer',
                    }}
                  >
                    Use as Template in form
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
