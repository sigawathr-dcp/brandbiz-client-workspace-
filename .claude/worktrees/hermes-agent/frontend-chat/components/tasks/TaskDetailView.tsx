'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Ic } from '@/components/ui/Icon'
import { MarkdownContent } from '@/components/ui/Markdown'
import { TASK_STATUS } from '@/lib/domain'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TaskDetail {
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
  prompt: string
  result: string | null
  progress: string | null
}

const ACTIVE_STATUSES = new Set(['queued', 'running'])
const POLL_INTERVAL_MS = 2000

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

// Log lines are written by the worker as "- <line>" (app/services/agent_tasks.py
// _flush_progress); count them for the collapsed-state summary.
function countSteps(progressText: string): number {
  return progressText.split('\n').filter((l) => l.startsWith('- ')).length
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function TaskDetailView({ taskId }: { taskId: string }) {
  const router = useRouter()
  const [detail, setDetail] = useState<TaskDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [reRunning, setReRunning] = useState(false)
  const [copied, setCopied] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  // Progress is cleared server-side once the task finishes (result/error_text
  // become the durable record) -- keep the last non-null snapshot around so
  // the activity log stays visible (collapsed) after completion.
  const [lastProgress, setLastProgress] = useState<string | null>(null)
  const [logExpanded, setLogExpanded] = useState(true)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const logRef = useRef<HTMLDivElement | null>(null)

  const load = useCallback(async () => {
    try {
      const res = await fetch(`/api/tasks/${taskId}`, { cache: 'no-store' })
      if (res.status === 404) { setNotFound(true); return }
      if (res.ok) {
        const data = (await res.json()) as TaskDetail
        setDetail(data)
        if (data.progress) setLastProgress(data.progress)
      }
    } finally {
      setLoading(false)
    }
  }, [taskId])

  useEffect(() => { load() }, [load])

  // Poll every 2s while active; stop once terminal.
  useEffect(() => {
    const active = detail ? ACTIVE_STATUSES.has(detail.status) : false
    if (!active) {
      if (pollTimerRef.current) { clearInterval(pollTimerRef.current); pollTimerRef.current = null }
      return
    }
    if (pollTimerRef.current) return
    pollTimerRef.current = setInterval(load, POLL_INTERVAL_MS)
    return () => {
      if (pollTimerRef.current) { clearInterval(pollTimerRef.current); pollTimerRef.current = null }
    }
  }, [detail, load])

  // Auto-scroll the log to the bottom while it's live and expanded.
  useEffect(() => {
    if (!logRef.current) return
    const active = detail ? ACTIVE_STATUSES.has(detail.status) : false
    if (active && logExpanded) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [lastProgress, logExpanded, detail])

  async function handleCancel() {
    setCancelling(true)
    setActionError(null)
    try {
      const res = await fetch(`/api/tasks/${taskId}/cancel`, { method: 'POST' })
      const data = await res.json()
      if (!res.ok) {
        setActionError(typeof data?.detail === 'string' ? data.detail : 'Cancel failed.')
        return
      }
      setDetail((d) => (d ? { ...d, status: data.status, finished_at: data.finished_at } : d))
    } catch {
      setActionError('Network error — please try again.')
    } finally {
      setCancelling(false)
    }
  }

  async function handleCopy() {
    if (!detail?.result) return
    try {
      await navigator.clipboard.writeText(detail.result)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard permission denied or unavailable — non-fatal, just skip.
    }
  }

  async function handleReRun() {
    if (!detail) return
    setReRunning(true)
    setActionError(null)
    try {
      const res = await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: detail.prompt }),
      })
      const data = await res.json()
      if (!res.ok) {
        const msg = data?.detail?.message ?? data?.detail ?? 'Could not re-run the task.'
        setActionError(typeof msg === 'string' ? msg : JSON.stringify(msg))
        return
      }
      router.push(`/tasks/${data.id}`)
    } catch {
      setActionError('Network error — please try again.')
    } finally {
      setReRunning(false)
    }
  }

  const active = detail ? ACTIVE_STATUSES.has(detail.status) : false
  const canCancel = active
  const stepCount = lastProgress ? countSteps(lastProgress) : 0

  return (
    <div style={{ maxWidth: 760, margin: '0 auto', padding: '32px 24px 60px' }}>
      <style>{`
        @keyframes task-spin { to { transform: rotate(360deg) } }
        @keyframes task-pulse { 0%, 100% { opacity: 1 } 50% { opacity: 0.35 } }
      `}</style>

      <Link href="/tasks" style={{
        display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--ink-3)',
        textDecoration: 'none', marginBottom: 18,
      }}>
        <Ic.back size={14} /> Back to tasks
      </Link>

      {loading ? (
        <div style={{ color: 'var(--ink-4)', fontSize: 14 }}>Loading…</div>
      ) : notFound || !detail ? (
        <div style={{ color: 'var(--ink-4)', fontSize: 14 }}>Task not found.</div>
      ) : (
        <>
          {/* Header */}
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, marginBottom: 8 }}>
            <div>
              <h1 style={{ margin: '0 0 8px', fontSize: 20, fontWeight: 700, color: 'var(--ink)', letterSpacing: '-.02em' }}>
                {detail.title?.trim() || '(empty task)'}
              </h1>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <StatusBadge status={detail.status} />
                {detail.model_used && <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>via {detail.model_used}</span>}
                <span style={{ fontSize: 11.5, color: 'var(--ink-4)' }}>
                  started {new Date(detail.created_at).toLocaleString()}
                  {detail.finished_at && ` · finished ${new Date(detail.finished_at).toLocaleString()}`}
                </span>
              </div>
            </div>
            {canCancel && (
              <button
                onClick={handleCancel}
                disabled={cancelling}
                style={{
                  padding: '7px 14px', borderRadius: 'var(--r-md)', border: '1px solid var(--danger)',
                  background: 'transparent', color: 'var(--danger)', fontSize: 12.5, fontWeight: 600,
                  cursor: cancelling ? 'default' : 'pointer', opacity: cancelling ? 0.6 : 1, flexShrink: 0,
                }}
              >
                {cancelling ? 'Cancelling…' : 'Cancel task'}
              </button>
            )}
          </div>

          {detail.downgrade_to_local && (
            <div style={{
              background: 'var(--surface-2)', border: '1px solid var(--line)', borderRadius: 'var(--r-md)',
              padding: '8px 12px', fontSize: 12.5, color: 'var(--ink-3)', margin: '12px 0',
            }}>
              This prompt contained sensitive data, so it was routed to the local model instead of Hermes.
            </div>
          )}

          {actionError && (
            <div style={{
              fontSize: 12.5, color: 'var(--danger)', background: 'var(--danger-bg)',
              border: '1px solid var(--danger)', borderRadius: 'var(--r-md)', padding: '8px 12px', margin: '12px 0',
            }}>
              {actionError}
            </div>
          )}

          {/* Task */}
          <div style={{ margin: '20px 0' }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink-3)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '.03em' }}>
              Task
            </div>
            <div style={{
              fontSize: 13.5, color: 'var(--ink)', whiteSpace: 'pre-wrap', lineHeight: 1.5,
              background: 'var(--surface-2)', borderRadius: 'var(--r-md)', padding: '10px 12px',
            }}>
              {detail.prompt}
            </div>
          </div>

          {/* Activity log */}
          {lastProgress && (
            <div style={{ margin: '20px 0' }}>
              <div
                onClick={() => setLogExpanded((v) => !v)}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer',
                  marginBottom: 6,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '.03em' }}>
                    Activity log
                  </span>
                  {active ? (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--warning)' }}>
                      <span style={{
                        width: 5, height: 5, borderRadius: '50%', background: 'var(--warning)',
                        animation: 'task-pulse 1.4s ease-in-out infinite',
                      }} />
                      live
                    </span>
                  ) : (
                    <span style={{ fontSize: 11, color: 'var(--ink-4)' }}>{stepCount} step{stepCount === 1 ? '' : 's'}</span>
                  )}
                </div>
                <Ic.chevron
                  size={14}
                  style={{ color: 'var(--ink-4)', transform: logExpanded ? undefined : 'rotate(-90deg)', transition: 'transform 0.12s' }}
                />
              </div>
              {logExpanded && (
                <div
                  ref={logRef}
                  style={{
                    fontFamily: 'var(--font-mono)', fontSize: 12, lineHeight: 1.7, color: 'var(--ink-2)',
                    background: 'var(--surface-sunk, var(--surface-2))', border: '1px solid var(--line)',
                    borderRadius: 'var(--r-md)', padding: '10px 12px', maxHeight: 280, overflowY: 'auto',
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {lastProgress}
                </div>
              )}
            </div>
          )}

          {/* Output */}
          <div style={{ margin: '20px 0' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '.03em' }}>
                Output
              </span>
              {detail.status === 'succeeded' && detail.result && (
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    onClick={handleCopy}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 5, padding: '4px 10px', borderRadius: 'var(--r-sm)',
                      border: '1px solid var(--line)', background: 'transparent', color: 'var(--ink-3)',
                      fontSize: 11.5, cursor: 'pointer',
                    }}
                  >
                    <Ic.Copy size={12} /> {copied ? 'Copied' : 'Copy'}
                  </button>
                  <button
                    onClick={handleReRun}
                    disabled={reRunning}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 5, padding: '4px 10px', borderRadius: 'var(--r-sm)',
                      border: '1px solid var(--line)', background: 'transparent', color: 'var(--ink-3)',
                      fontSize: 11.5, cursor: reRunning ? 'default' : 'pointer', opacity: reRunning ? 0.6 : 1,
                    }}
                  >
                    <Ic.RefreshCw size={12} /> {reRunning ? 'Re-running…' : 'Re-run'}
                  </button>
                </div>
              )}
            </div>

            {detail.status === 'succeeded' && detail.result ? (
              <div style={{
                fontSize: 13.5, color: 'var(--ink)', lineHeight: 1.6,
                border: '1px solid var(--line)', borderRadius: 'var(--r-md)', padding: '12px 14px',
              }}>
                <MarkdownContent text={detail.result} />
              </div>
            ) : detail.status === 'failed' ? (
              <div style={{
                fontSize: 13, color: 'var(--danger)', border: '1px solid var(--danger)',
                borderRadius: 'var(--r-md)', padding: '10px 12px', background: 'var(--danger-bg)',
              }}>
                {detail.error_text || 'The task failed for an unknown reason.'}
              </div>
            ) : detail.status === 'cancelled' ? (
              <div style={{ fontSize: 13, color: 'var(--ink-4)', fontStyle: 'italic' }}>Cancelled before it finished.</div>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--ink-3)' }}>
                <span style={{
                  width: 14, height: 14, border: '2px solid var(--line-2)', borderTopColor: 'var(--accent)',
                  borderRadius: '50%', animation: 'task-spin 0.8s linear infinite',
                }} />
                Hermes is still working on this — check back shortly.
              </div>
            )}
          </div>

          {(detail.tokens_input != null || detail.tokens_output != null) && (
            <div style={{ fontSize: 11.5, color: 'var(--ink-4)', marginBottom: 12 }}>
              {detail.tokens_input ?? 0} in · {detail.tokens_output ?? 0} out
              {detail.cost_usd != null && ` · $${Number(detail.cost_usd).toFixed(4)}`}
            </div>
          )}

          <div style={{ fontSize: 11, color: 'var(--ink-4)', display: 'flex', alignItems: 'center', gap: 5, marginTop: 24 }}>
            <Ic.lock size={11} /> Prompt, activity log, and output are stored encrypted · governed by the policy engine
          </div>
        </>
      )}
    </div>
  )
}
