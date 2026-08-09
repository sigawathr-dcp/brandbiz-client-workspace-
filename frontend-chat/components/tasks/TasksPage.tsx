'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Ic } from '@/components/ui/Icon'
import { TASK_STATUS } from '@/lib/domain'
import HermesStatusBanner from '@/components/tasks/HermesStatusBanner'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TaskSummary {
  id: string
  title: string | null
  status: string
  downgrade_to_local: boolean
  model_used: string | null
  tokens_input: number | null
  tokens_output: number | null
  cost_usd: number | null
  error_text: string | null
  created_at: string
  updated_at: string
  finished_at: string | null
  // Cheap presence flag (no decrypt) -- true once the worker has flushed at
  // least one progress snapshot. Full activity log is only fetched on the
  // detail page.
  has_progress: boolean
}

const ACTIVE_STATUSES = new Set(['queued', 'running'])

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const TONE_COLOR: Record<string, string> = {
  pending: 'var(--ink-3)',
  active: 'var(--warning)',
  success: 'var(--success)',
  danger: 'var(--danger)',
  muted: 'var(--ink-4)',
}

function StatusBadge({ status }: { status: string }) {
  const meta = TASK_STATUS[status] ?? { label: status, tone: 'muted' as const }
  const color = TONE_COLOR[meta.tone] ?? 'var(--ink-3)'
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 5,
      fontSize: 11,
      fontWeight: 600,
      padding: '2px 9px',
      borderRadius: 999,
      background: `color-mix(in srgb, ${color} 14%, transparent)`,
      color,
    }}>
      {status === 'running' && (
        <span style={{
          width: 6, height: 6, borderRadius: '50%', background: color,
          animation: 'task-pulse 1.4s ease-in-out infinite',
        }} />
      )}
      {meta.label}
    </span>
  )
}

function EmptyState({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '50%',
      minHeight: 200,
      color: 'var(--ink-4)',
      gap: 10,
    }}>
      {icon}
      <span style={{ fontSize: 14 }}>{text}</span>
    </div>
  )
}

function TaskCard({ task, onOpen }: { task: TaskSummary; onOpen: (t: TaskSummary) => void }) {
  const label = task.title?.trim() || '(empty task)'
  return (
    <div
      onClick={() => onOpen(task)}
      style={{
        border: '1px solid var(--line)',
        borderRadius: 'var(--r-md)',
        background: 'var(--surface)',
        padding: '14px 16px',
        cursor: 'pointer',
        transition: 'box-shadow 0.12s',
      }}
      onMouseEnter={(e) => (e.currentTarget.style.boxShadow = 'var(--shadow-2)')}
      onMouseLeave={(e) => (e.currentTarget.style.boxShadow = 'none')}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: 14,
            fontWeight: 600,
            color: 'var(--ink)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            marginBottom: 6,
          }}>
            {label}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <StatusBadge status={task.status} />
            {task.status === 'running' && task.has_progress && (
              <span style={{ fontSize: 11, color: 'var(--ink-4)', fontStyle: 'italic' }}>
                Hermes is working…
              </span>
            )}
            {task.downgrade_to_local && (
              <span
                title="This prompt contained sensitive data, so it ran on the local model — Hermes never saw it."
                style={{ fontSize: 11, color: 'var(--ink-4)', fontStyle: 'italic' }}
              >
                ran on local model
              </span>
            )}
            <span style={{ fontSize: 11.5, color: 'var(--ink-4)' }}>
              {new Date(task.created_at).toLocaleString()}
            </span>
          </div>
        </div>
        <Ic.chevron size={14} style={{ color: 'var(--ink-4)', flexShrink: 0, transform: 'rotate(-90deg)', marginTop: 2 }} />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function TasksPage() {
  const router = useRouter()
  const [prompt, setPrompt] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tasks, setTasks] = useState<TaskSummary[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const promptRef = useRef<HTMLTextAreaElement | null>(null)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const loadTasks = useCallback(async () => {
    setIsLoading(true)
    try {
      const res = await fetch('/api/tasks', { cache: 'no-store' })
      if (res.ok) setTasks(await res.json())
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => { loadTasks() }, [loadTasks])

  // Poll queued/running tasks every 5s until all reach a terminal state.
  useEffect(() => {
    const activeIds = tasks.filter((t) => ACTIVE_STATUSES.has(t.status)).map((t) => t.id)

    if (activeIds.length === 0) {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current)
        pollTimerRef.current = null
      }
      return
    }

    if (pollTimerRef.current) return  // already polling

    pollTimerRef.current = setInterval(async () => {
      const current = activeIds.slice()  // snapshot
      const updates = await Promise.all(
        current.map(async (id) => {
          try {
            const res = await fetch(`/api/tasks/${id}`, { cache: 'no-store' })
            if (res.ok) return (await res.json()) as TaskSummary
          } catch { /* network blip — retry next tick */ }
          return null
        })
      )
      updates.forEach((updated) => {
        if (!updated) return
        setTasks((prev) => prev.map((t) => (t.id === updated.id ? updated : t)))
      })
    }, 5000)

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current)
        pollTimerRef.current = null
      }
    }
  }, [tasks])

  async function handleSubmit() {
    if (!prompt.trim() || submitting) return
    setError(null)
    setSubmitting(true)
    try {
      const res = await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: prompt.trim() }),
      })
      const data = await res.json()
      if (!res.ok) {
        const msg = data?.detail?.message ?? data?.detail ?? 'Could not submit the task.'
        setError(typeof msg === 'string' ? msg : JSON.stringify(msg))
        return
      }
      setTasks((prev) => [data as TaskSummary, ...prev])
      setPrompt('')
    } catch {
      setError('Network error — please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ maxWidth: 760, margin: '0 auto', padding: '32px 24px 60px' }}>
      <style>{`
        @keyframes task-spin { to { transform: rotate(360deg) } }
        @keyframes task-pulse { 0%, 100% { opacity: 1 } 50% { opacity: 0.35 } }
      `}</style>

      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: 'var(--ink)', letterSpacing: '-.02em' }}>
          Tasks
        </h1>
        <p style={{ margin: '4px 0 0', fontSize: 13.5, color: 'var(--ink-3)' }}>
          Assign Hermes an outcome and close the tab — it keeps working, and you come back to a finished result.
        </p>
      </div>

      <HermesStatusBanner />

      <div style={{
        border: '1px solid var(--line-2)', borderRadius: 'var(--r-md)', background: 'var(--surface)',
        padding: 16, marginBottom: 28,
      }}>
        <textarea
          ref={promptRef}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Tell Hermes what you need, not how — e.g. “Research our top 3 competitors’ pricing and summarize the differences.”"
          rows={4}
          style={{
            width: '100%',
            padding: '10px 12px',
            borderRadius: 'var(--r-md)',
            border: '1px solid var(--line-2)',
            background: 'var(--surface)',
            color: 'var(--ink)',
            fontSize: 13.5,
            resize: 'vertical',
            minHeight: 90,
            fontFamily: 'inherit',
            boxSizing: 'border-box',
            marginBottom: 12,
          }}
        />
        {error && (
          <div style={{
            fontSize: 13, color: 'var(--danger)', background: 'var(--danger-bg)',
            border: '1px solid var(--danger)', borderRadius: 'var(--r-md)', padding: '8px 12px', marginBottom: 12,
          }}>
            <Ic.alert size={13} style={{ marginRight: 6, verticalAlign: 'text-bottom' }} />
            {error}
          </div>
        )}
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button
            onClick={handleSubmit}
            disabled={submitting || !prompt.trim()}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '9px 18px',
              borderRadius: 'var(--r-md)',
              border: 'none',
              background: submitting || !prompt.trim() ? 'var(--surface-2)' : 'var(--accent)',
              color: submitting || !prompt.trim() ? 'var(--ink-4)' : '#fff',
              fontWeight: 600,
              fontSize: 13.5,
              cursor: submitting || !prompt.trim() ? 'not-allowed' : 'pointer',
              transition: 'background 0.12s',
            }}
          >
            <Ic.send size={14} />
            {submitting ? 'Assigning…' : 'Assign to Hermes'}
          </button>
        </div>
      </div>

      {isLoading ? (
        <EmptyState icon={<Ic.clock size={28} />} text="Loading…" />
      ) : tasks.length === 0 ? (
        <EmptyState icon={<Ic.clock size={28} />} text="No tasks yet — assign one above." />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {tasks.map((t) => (
            <TaskCard key={t.id} task={t} onOpen={(task) => router.push(`/tasks/${task.id}`)} />
          ))}
        </div>
      )}
    </div>
  )
}
