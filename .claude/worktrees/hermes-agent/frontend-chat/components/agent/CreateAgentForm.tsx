'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Ic } from '@/components/ui/Icon'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ModelOption {
  code: string
  display_name: string
  provider: string
  is_local: boolean
}

interface FileItem {
  id: string
  filename: string
  size_bytes: number | null
  created_at: string
  is_processed: boolean
}

interface AgentFormState {
  name: string
  provider: string
  model: string
  description: string
  instructions: string
  web_search: boolean
  think_longer: boolean
  image_gen: boolean
  video_gen: boolean
  creativity_level: number
  visibility: string
  status: string
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CREATIVITY_STOPS = [
  { value: 0, label: 'Focused', desc: 'Precise and consistent responses' },
  { value: 50, label: 'Balanced', desc: 'Mix of creativity and accuracy' },
  { value: 100, label: 'Creative', desc: 'Imaginative and expressive responses' },
]

function creativityLabel(v: number): typeof CREATIVITY_STOPS[0] {
  if (v < 34) return CREATIVITY_STOPS[0]
  if (v < 67) return CREATIVITY_STOPS[1]
  return CREATIVITY_STOPS[2]
}

// ---------------------------------------------------------------------------
// Small UI helpers
// ---------------------------------------------------------------------------

function Label({ children, required }: { children: React.ReactNode; required?: boolean }) {
  return (
    <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink)', marginBottom: 6 }}>
      {children}{required && <span style={{ color: '#e53e3e', marginLeft: 3 }}>*</span>}
    </div>
  )
}

function CharCount({ value, max }: { value: string; max: number }) {
  return (
    <div style={{ fontSize: 11, color: 'var(--ink-4)', textAlign: 'right', marginTop: 2 }}>
      {value.length} / {max}
    </div>
  )
}

function inputStyle(error?: boolean): React.CSSProperties {
  return {
    width: '100%',
    padding: '9px 12px',
    borderRadius: 'var(--r-md)',
    border: `1px solid ${error ? '#e53e3e' : 'var(--line)'}`,
    background: 'var(--surface)',
    fontSize: 13.5,
    color: 'var(--ink)',
    outline: 'none',
    boxSizing: 'border-box',
  }
}

// ---------------------------------------------------------------------------
// CreateAgentForm
// ---------------------------------------------------------------------------

export default function CreateAgentForm({ agentId }: { agentId?: string }) {
  const router = useRouter()
  const isEdit = Boolean(agentId)

  const [form, setForm] = useState<AgentFormState>({
    name: '',
    provider: '',
    model: '',
    description: '',
    instructions: '',
    web_search: false,
    think_longer: false,
    image_gen: false,
    video_gen: false,
    creativity_level: 0,
    visibility: 'public',
    status: 'published',
  })

  const [models, setModels] = useState<ModelOption[]>([])
  const [knowledgeFiles, setKnowledgeFiles] = useState<FileItem[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Load available models
  useEffect(() => {
    fetch('/api/models', { cache: 'no-store' })
      .then(r => r.json())
      .then(data => setModels(Array.isArray(data) ? data : []))
      .catch(() => {})
  }, [])

  // Load existing agent in edit mode
  useEffect(() => {
    if (!agentId) return
    fetch(`/api/agent/${agentId}`, { cache: 'no-store' })
      .then(r => r.json())
      .then(data => {
        const caps = data.capabilities ?? {}
        setForm({
          name: data.name ?? '',
          provider: data.provider ?? '',
          model: data.model ?? '',
          description: data.description ?? '',
          instructions: data.instructions ?? '',
          web_search: Boolean(caps.web_search),
          think_longer: Boolean(caps.think_longer),
          image_gen: Boolean(caps.image_gen),
          video_gen: Boolean(caps.video_gen),
          creativity_level: data.creativity_level ?? 0,
          visibility: data.visibility ?? 'public',
          status: data.status ?? 'published',
        })
      })
      .catch(() => {})
  }, [agentId])

  // Derived: unique providers from permitted models
  const providers = Array.from(new Set(models.map(m => m.provider)))
  const modelsForProvider = models.filter(m => m.provider === form.provider)

  function setField<K extends keyof AgentFormState>(k: K, v: AgentFormState[K]) {
    setForm(prev => ({ ...prev, [k]: v }))
    if (errors[k]) setErrors(prev => { const n = { ...prev }; delete n[k]; return n })
  }

  function validate() {
    const e: Record<string, string> = {}
    if (!form.name.trim()) e.name = 'Agent name is required'
    if (!form.provider) e.provider = 'Provider is required'
    if (!form.model) e.model = 'AI Model is required'
    if (!form.description.trim()) e.description = 'Description is required'
    if (!form.instructions.trim()) e.instructions = 'Instructions are required'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  async function handleSubmit(targetStatus: 'published' | 'draft') {
    if (!validate()) return
    setSubmitting(true)
    const body = {
      name: form.name.slice(0, 100),
      provider: form.provider,
      model: form.model,
      description: form.description.slice(0, 1000),
      instructions: form.instructions.slice(0, 4000),
      capabilities: {
        web_search: form.web_search,
        think_longer: form.think_longer,
        image_gen: form.image_gen,
        video_gen: form.video_gen,
      },
      creativity_level: form.creativity_level,
      visibility: form.visibility,
      status: targetStatus,
    }
    try {
      const res = isEdit
        ? await fetch(`/api/agent/${agentId}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
        : await fetch('/api/agent', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      if (res.ok) {
        router.push('/agent?scope=mine')
      } else {
        const data = await res.json().catch(() => ({}))
        setErrors({ _global: data.detail ?? 'Something went wrong.' })
      }
    } finally {
      setSubmitting(false)
    }
  }

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file || !agentId) return
    const fd = new FormData()
    fd.append('file', file)
    fd.append('scope', 'personal')
    const res = await fetch('/api/library/files', { method: 'POST', body: fd })
    if (res.ok) {
      const data = await res.json()
      await fetch(`/api/agent/${agentId}/knowledge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_id: data.id }),
      })
      setKnowledgeFiles(prev => [...prev, data])
    }
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const clevel = creativityLabel(form.creativity_level)

  return (
    <div style={{ padding: '28px 32px', maxWidth: 780 }}>
      {/* Breadcrumb */}
      <div style={{ fontSize: 13, color: 'var(--ink-3)', marginBottom: 18, display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ cursor: 'pointer', color: 'var(--accent)' }} onClick={() => router.push('/agent')}>All AI Agent</span>
        <span>•</span>
        <span style={{ cursor: 'pointer', color: 'var(--accent)' }} onClick={() => router.push('/agent?scope=mine')}>My Agent</span>
        <span>•</span>
        <span>{isEdit ? 'Edit Agent' : 'Create Agent'}</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink)', margin: 0 }}>
          {isEdit ? 'Edit Agent' : 'Create Agent'}
        </h1>
        <button
          onClick={() => handleSubmit('draft')}
          disabled={submitting}
          style={{
            padding: '7px 16px',
            borderRadius: 'var(--r-md)',
            border: '1px solid var(--line-2)',
            background: 'var(--surface)',
            color: 'var(--ink-2)',
            fontWeight: 600,
            fontSize: 13,
            cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: 6,
          }}
        >
          <Ic.file size={13} strokeWidth={2} />
          Save Draft
        </button>
      </div>

      {errors._global && (
        <div style={{ padding: '10px 14px', background: '#fff5f5', border: '1px solid #fed7d7', borderRadius: 'var(--r-md)', fontSize: 13, color: '#c53030', marginBottom: 18 }}>
          {errors._global}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        {/* Agent Name */}
        <div>
          <Label required>Agent Name</Label>
          <input
            value={form.name}
            onChange={e => setField('name', e.target.value)}
            placeholder="Agent Name"
            maxLength={100}
            style={inputStyle(Boolean(errors.name))}
          />
          <CharCount value={form.name} max={100} />
          {errors.name && <div style={{ fontSize: 12, color: '#e53e3e', marginTop: 3 }}>{errors.name}</div>}
        </div>

        {/* Provider + Model */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          <div>
            <Label required>Provider</Label>
            <select
              value={form.provider}
              onChange={e => { setField('provider', e.target.value); setField('model', '') }}
              style={{ ...inputStyle(Boolean(errors.provider)), appearance: 'none', cursor: 'pointer' }}
            >
              <option value="">Provider</option>
              {providers.map(p => (
                <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
              ))}
            </select>
            {errors.provider && <div style={{ fontSize: 12, color: '#e53e3e', marginTop: 3 }}>{errors.provider}</div>}
          </div>
          <div>
            <Label required>AI Model</Label>
            <select
              value={form.model}
              onChange={e => setField('model', e.target.value)}
              disabled={!form.provider}
              style={{ ...inputStyle(Boolean(errors.model)), appearance: 'none', cursor: form.provider ? 'pointer' : 'not-allowed', opacity: form.provider ? 1 : 0.5 }}
            >
              <option value="">Model</option>
              {modelsForProvider.map(m => (
                <option key={m.code} value={m.code}>{m.display_name}</option>
              ))}
            </select>
            {errors.model && <div style={{ fontSize: 12, color: '#e53e3e', marginTop: 3 }}>{errors.model}</div>}
          </div>
        </div>

        {/* Description */}
        <div>
          <Label required>Description</Label>
          <textarea
            value={form.description}
            onChange={e => setField('description', e.target.value)}
            placeholder="Add a short Description about what this agent does"
            maxLength={1000}
            rows={3}
            style={{ ...inputStyle(Boolean(errors.description)), resize: 'vertical', fontFamily: 'inherit' }}
          />
          <CharCount value={form.description} max={1000} />
          {errors.description && <div style={{ fontSize: 12, color: '#e53e3e', marginTop: 3 }}>{errors.description}</div>}
        </div>

        {/* Instructions */}
        <div>
          <Label required>Instructions</Label>
          <textarea
            value={form.instructions}
            onChange={e => setField('instructions', e.target.value)}
            placeholder={'What does this Agent do ?\nHow does it behave?\nWhat should it avoid doing?'}
            maxLength={4000}
            rows={6}
            style={{ ...inputStyle(Boolean(errors.instructions)), resize: 'vertical', fontFamily: 'inherit' }}
          />
          <CharCount value={form.instructions} max={4000} />
          {errors.instructions && <div style={{ fontSize: 12, color: '#e53e3e', marginTop: 3 }}>{errors.instructions}</div>}
        </div>

        {/* Capabilities */}
        <div>
          <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink)', marginBottom: 10 }}>Capabilities</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {([
              ['web_search', 'Web Search'],
              ['image_gen', 'Image Generator'],
              ['think_longer', 'Think Longer'],
              ['video_gen', 'Video Generator'],
            ] as const).map(([key, label]) => (
              <label key={key} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13.5, color: 'var(--ink-2)' }}>
                <input
                  type="checkbox"
                  checked={form[key]}
                  onChange={e => setField(key, e.target.checked)}
                  style={{ width: 15, height: 15, accentColor: 'var(--accent)', cursor: 'pointer' }}
                />
                {label}
              </label>
            ))}
          </div>
        </div>

        <hr style={{ border: 'none', borderTop: '1px solid var(--line)', margin: '4px 0' }} />

        {/* Creativity Level */}
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--ink)', marginBottom: 4 }}>Creativity Level</div>
          <div style={{ fontSize: 12.5, color: 'var(--ink-3)', marginBottom: 14 }}>
            Lower values = focused & precise | Higher values = imaginative & expressive
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5, fontWeight: 600, color: 'var(--ink-3)', marginBottom: 8 }}>
            <span>🎯 Focused</span>
            <span>💡 Balanced</span>
            <span>🎨 Creative</span>
          </div>
          <input
            type="range"
            min={0}
            max={100}
            step={1}
            value={form.creativity_level}
            onChange={e => setField('creativity_level', Number(e.target.value))}
            style={{ width: '100%', accentColor: 'var(--accent)', cursor: 'pointer' }}
          />
          <div style={{
            marginTop: 10,
            background: 'var(--surface-2)',
            borderRadius: 'var(--r-md)',
            padding: '10px 14px',
            display: 'flex',
            alignItems: 'center',
            gap: 12,
          }}>
            <div style={{
              width: 32, height: 32, borderRadius: '50%',
              background: 'var(--ink-2)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: '#fff', fontWeight: 700, fontSize: 12,
              flexShrink: 0,
            }}>
              {form.creativity_level}
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 13.5 }}>{clevel.label}</div>
              <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>{clevel.desc}</div>
            </div>
          </div>
        </div>

        {/* Agent Knowledge */}
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--ink)', marginBottom: 12 }}>Agent Knowledge</div>
          <div style={{ display: 'flex', gap: 10, marginBottom: 12 }}>
            <div style={{ position: 'relative', flex: 1 }}>
              <Ic.search size={13} strokeWidth={2} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--ink-4)' }} />
              <input placeholder="Search" style={{ ...inputStyle(), paddingLeft: 30 }} readOnly />
            </div>
            {isEdit ? (
              <>
                <input ref={fileInputRef} type="file" style={{ display: 'none' }} onChange={handleFileUpload} />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  style={{
                    padding: '8px 16px', borderRadius: 'var(--r-md)',
                    border: '1px solid var(--line-2)', background: 'var(--surface)',
                    fontSize: 13, fontWeight: 600, color: 'var(--ink-2)', cursor: 'pointer',
                    display: 'flex', alignItems: 'center', gap: 6,
                  }}
                >
                  <Ic.plus size={13} strokeWidth={2.5} /> Upload File
                </button>
              </>
            ) : (
              <div style={{ fontSize: 12, color: 'var(--ink-3)', alignSelf: 'center' }}>
                Save first to attach knowledge files.
              </div>
            )}
          </div>

          {/* Table */}
          <div style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-md)', overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 0, background: 'var(--surface-2)', padding: '8px 14px', fontSize: 12, fontWeight: 700, color: 'var(--ink-3)' }}>
              <span>Name</span>
              <span>Date Created</span>
            </div>
            {knowledgeFiles.length === 0 ? (
              <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--ink-4)' }}>
                <Ic.database size={28} strokeWidth={1.4} style={{ marginBottom: 8, display: 'block', margin: '0 auto 8px' }} />
                <div style={{ fontWeight: 600 }}>No file</div>
                <div style={{ fontSize: 12 }}>You have no file</div>
              </div>
            ) : knowledgeFiles.map(f => (
              <div key={f.id} style={{ display: 'grid', gridTemplateColumns: '1fr auto', padding: '8px 14px', fontSize: 13, borderTop: '1px solid var(--line)', alignItems: 'center' }}>
                <span style={{ color: 'var(--ink-2)' }}>{f.filename}</span>
                <span style={{ color: 'var(--ink-4)', fontSize: 12 }}>{new Date(f.created_at).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Visibility */}
        <div>
          <Label>Visibility</Label>
          <select
            value={form.visibility}
            onChange={e => setField('visibility', e.target.value)}
            style={{ ...inputStyle(), appearance: 'none', cursor: 'pointer', maxWidth: 200 }}
          >
            <option value="public">Public (all employees)</option>
            <option value="personal">Personal (only me)</option>
          </select>
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', paddingTop: 8 }}>
          <button
            onClick={() => router.back()}
            disabled={submitting}
            style={{
              padding: '10px 22px', borderRadius: 'var(--r-md)',
              border: '1px solid var(--line-2)', background: 'var(--surface)',
              color: 'var(--ink-2)', fontWeight: 600, fontSize: 14, cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={() => handleSubmit('published')}
            disabled={submitting}
            style={{
              padding: '10px 28px', borderRadius: 'var(--r-md)',
              border: 'none',
              background: submitting ? 'var(--ink-4)' : 'linear-gradient(135deg, #ff6b9d, #c44dff)',
              color: '#fff', fontWeight: 700, fontSize: 14, cursor: submitting ? 'not-allowed' : 'pointer',
            }}
          >
            {submitting ? 'Saving…' : isEdit ? 'Update' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  )
}
