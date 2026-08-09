'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SkillFormState {
  name: string
  description: string
  instructions: string
  visibility: string
}

const SLUG_RE = /^[a-z0-9][a-z0-9-]*$/

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
// SkillForm — "Write skill instructions", used for both create and edit
// ---------------------------------------------------------------------------

export default function SkillForm({ skillId }: { skillId?: string }) {
  const router = useRouter()
  const isEdit = Boolean(skillId)

  const [form, setForm] = useState<SkillFormState>({
    name: '',
    description: '',
    instructions: '',
    visibility: 'personal',
  })
  const [submitting, setSubmitting] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})

  // Load existing skill in edit mode
  useEffect(() => {
    if (!skillId) return
    fetch(`/api/skills/${skillId}`, { cache: 'no-store' })
      .then(r => r.json())
      .then(data => {
        setForm({
          name: data.name ?? '',
          description: data.description ?? '',
          instructions: data.instructions ?? '',
          visibility: data.visibility ?? 'personal',
        })
      })
      .catch(() => {})
  }, [skillId])

  // Prefill from a "Create with AI" draft handed off via sessionStorage (one-time consumption).
  // A useEffect (not a lazy useState initializer) so this runs post-hydration and can't cause a
  // server/client render mismatch — same pattern as the edit-mode fetch above.
  useEffect(() => {
    if (skillId) return
    try {
      const raw = sessionStorage.getItem('skill_draft')
      if (!raw) return
      sessionStorage.removeItem('skill_draft')
      const draft = JSON.parse(raw)
      setForm(prev => ({
        ...prev,
        name: draft.name ?? prev.name,
        description: draft.description ?? prev.description,
        instructions: draft.instructions ?? prev.instructions,
      }))
    } catch {
      // Malformed sessionStorage payload — ignore, leave the form blank.
    }
  }, [skillId])

  function setField<K extends keyof SkillFormState>(k: K, v: SkillFormState[K]) {
    setForm(prev => ({ ...prev, [k]: v }))
    if (errors[k]) setErrors(prev => { const n = { ...prev }; delete n[k]; return n })
  }

  function validate() {
    const e: Record<string, string> = {}
    const name = form.name.trim()
    if (!name) e.name = 'Skill name is required'
    else if (!SLUG_RE.test(name)) e.name = 'Use lowercase letters, digits, and hyphens only (e.g. weekly-status-report)'
    if (!form.description.trim()) e.description = 'Description is required — this is how the skill gets triggered'
    if (!form.instructions.trim()) e.instructions = 'Instructions are required'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  async function handleSubmit() {
    if (!validate()) return
    setSubmitting(true)
    const body = {
      name: form.name.trim(),
      description: form.description.slice(0, 1000),
      instructions: form.instructions.slice(0, 8000),
      visibility: form.visibility,
    }
    try {
      const res = isEdit
        ? await fetch(`/api/skills/${skillId}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
        : await fetch('/api/skills', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      if (res.ok) {
        router.push('/skills?scope=mine')
      } else {
        const data = await res.json().catch(() => ({}))
        setErrors({ _global: data.detail ?? 'Something went wrong.' })
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ padding: '28px 32px', maxWidth: 680 }}>
      {/* Breadcrumb */}
      <div style={{ fontSize: 13, color: 'var(--ink-3)', marginBottom: 18, display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ cursor: 'pointer', color: 'var(--accent)' }} onClick={() => router.push('/skills')}>Skills</span>
        <span>•</span>
        <span>{isEdit ? 'Edit skill' : 'Write skill instructions'}</span>
      </div>

      <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink)', margin: '0 0 24px' }}>
        {isEdit ? 'Edit skill' : 'Write skill instructions'}
      </h1>

      {errors._global && (
        <div style={{ padding: '10px 14px', background: '#fff5f5', border: '1px solid #fed7d7', borderRadius: 'var(--r-md)', fontSize: 13, color: '#c53030', marginBottom: 18 }}>
          {errors._global}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        {/* Skill name */}
        <div>
          <Label required>Skill name</Label>
          <input
            value={form.name}
            onChange={e => setField('name', e.target.value)}
            placeholder="weekly-status-report"
            maxLength={64}
            disabled={isEdit}
            style={{ ...inputStyle(Boolean(errors.name)), fontFamily: 'monospace', opacity: isEdit ? 0.7 : 1 }}
          />
          <div style={{ fontSize: 11.5, color: 'var(--ink-4)', marginTop: 3 }}>
            Lowercase, kebab-case — this is also the /{form.name || 'skill-name'} command.
          </div>
          {errors.name && <div style={{ fontSize: 12, color: '#e53e3e', marginTop: 3 }}>{errors.name}</div>}
        </div>

        {/* Description */}
        <div>
          <Label required>Description</Label>
          <textarea
            value={form.description}
            onChange={e => setField('description', e.target.value)}
            placeholder="Generate weekly status reports from recent work. Use when asked for updates or progress summaries."
            maxLength={1000}
            rows={2}
            style={{ ...inputStyle(Boolean(errors.description)), resize: 'vertical', fontFamily: 'inherit' }}
          />
          <div style={{ fontSize: 11.5, color: 'var(--ink-4)', marginTop: 3 }}>
            This is how the skill gets triggered automatically — say what it does and when to use it.
          </div>
          <CharCount value={form.description} max={1000} />
          {errors.description && <div style={{ fontSize: 12, color: '#e53e3e', marginTop: 3 }}>{errors.description}</div>}
        </div>

        {/* Instructions */}
        <div>
          <Label required>Instructions</Label>
          <textarea
            value={form.instructions}
            onChange={e => setField('instructions', e.target.value)}
            placeholder={'Summarize my recent work in three sections: wins, blockers, and next steps. Keep the tone professional but not stiff...'}
            maxLength={8000}
            rows={10}
            style={{ ...inputStyle(Boolean(errors.instructions)), resize: 'vertical', fontFamily: 'inherit' }}
          />
          <CharCount value={form.instructions} max={8000} />
          {errors.instructions && <div style={{ fontSize: 12, color: '#e53e3e', marginTop: 3 }}>{errors.instructions}</div>}
        </div>

        {/* Visibility */}
        <div>
          <Label>Visibility</Label>
          <select
            value={form.visibility}
            onChange={e => setField('visibility', e.target.value)}
            style={{ ...inputStyle(), appearance: 'none', cursor: 'pointer', maxWidth: 220 }}
          >
            <option value="personal">Personal (only me)</option>
            <option value="public">Public (all employees)</option>
          </select>
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', paddingTop: 8 }}>
          <button
            onClick={() => router.back()}
            disabled={submitting}
            style={{ padding: '10px 22px', borderRadius: 'var(--r-md)', border: '1px solid var(--line-2)', background: 'var(--surface)', color: 'var(--ink-2)', fontWeight: 600, fontSize: 14, cursor: 'pointer' }}
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            style={{ padding: '10px 28px', borderRadius: 'var(--r-md)', border: 'none', background: submitting ? 'var(--ink-4)' : 'linear-gradient(135deg, #ff6b9d, #c44dff)', color: '#fff', fontWeight: 700, fontSize: 14, cursor: submitting ? 'not-allowed' : 'pointer' }}
          >
            {submitting ? 'Saving…' : isEdit ? 'Update' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  )
}
