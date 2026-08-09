'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { Ic } from '@/components/ui/Icon'
import { MarkdownContent } from '@/components/ui/Markdown'
import { TASK_STATUS } from '@/lib/domain'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TaskMessage {
  id: string
  role: string
  content: string
  model_used: string | null
  created_at: string
}

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
  // Full turn-by-turn transcript from the task's conversation (Task 3.15 --
  // multi-turn follow-ups). The in-flight turn (if any) is NOT in here yet --
  // call_llm only commits a turn's user+assistant pair once it finishes, so
  // while active the latest prompt is rendered from `prompt` below instead.
  messages: TaskMessage[]
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

// Progress lines are written by the worker as "- <line>" (see
// app/services/agent_tasks.py's _flush_progress); anything after the last
// "- " line is the partial assistant answer streaming in, not a step.
function splitProgress(text: string): { steps: string[]; partial: string } {
  const lines = text.split('\n')
  const steps: string[] = []
  let i = 0
  for (; i < lines.length; i++) {
    if (lines[i].startsWith('- ')) { steps.push(lines[i].slice(2)); continue }
    if (lines[i].trim() === '') continue
    break
  }
  const partial = lines.slice(i).join('\n').trim()
  return { steps, partial }
}

// ---------------------------------------------------------------------------
// ProgressPanel — right-sidebar checklist (replaces the old flat activity log)
// ---------------------------------------------------------------------------

function ProgressPanel({ progressText, active }: { progressText: string | null; active: boolean }) {
  const [expanded, setExpanded] = useState(true)
  if (!progressText) return null
  const { steps } = splitProgress(progressText)
  if (steps.length === 0) return null

  return (
    <div style={{
      border: '1px solid var(--line)', borderRadius: 'var(--r-md)', background: 'var(--surface)',
      padding: '12px 14px',
    }}>
      <div
        onClick={() => setExpanded((v) => !v)}
        style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }}
      >
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '.03em' }}>
          Progress
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {active ? (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--warning)' }}>
              <span style={{
                width: 5, height: 5, borderRadius: '50%', background: 'var(--warning)',
                animation: 'task-pulse 1.4s ease-in-out infinite',
              }} />
              live
            </span>
          ) : (
            <span style={{ fontSize: 11, color: 'var(--ink-4)' }}>{steps.length} step{steps.length === 1 ? '' : 's'}</span>
          )}
          <Ic.chevron
            size={13}
            style={{ color: 'var(--ink-4)', transform: expanded ? undefined : 'rotate(-90deg)', transition: 'transform 0.12s' }}
          />
        </div>
      </div>

      {expanded && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 9, marginTop: 12 }}>
          {steps.map((step, i) => {
            const isCurrent = active && i === steps.length - 1
            return (
              <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                <span style={{
                  flexShrink: 0, width: 15, height: 15, marginTop: 1, borderRadius: '50%',
                  display: 'grid', placeItems: 'center',
                  background: isCurrent ? 'transparent' : 'color-mix(in srgb, var(--success) 16%, transparent)',
                  border: isCurrent ? '2px solid var(--line-2)' : 'none',
                  borderTopColor: isCurrent ? 'var(--accent)' : undefined,
                  animation: isCurrent ? 'task-spin 0.8s linear infinite' : undefined,
                }}>
                  {!isCurrent && <Ic.check size={9} strokeWidth={3} style={{ color: 'var(--success)' }} />}
                </span>
                <span style={{
                  fontSize: 12.5, lineHeight: 1.5,
                  color: isCurrent ? 'var(--ink)' : 'var(--ink-3)',
                  textDecoration: isCurrent ? 'none' : 'line-through',
                }}>
                  {step}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Message bubbles
// ---------------------------------------------------------------------------

function UserBubble({ text, pending }: { text: string; pending?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
      <div style={{
        maxWidth: '78%',
        padding: '10px 15px',
        borderRadius: '16px 16px 4px 16px',
        background: 'var(--accent)',
        color: '#fff',
        fontSize: 13.5,
        lineHeight: 1.6,
        wordBreak: 'break-word',
        whiteSpace: 'pre-wrap',
        opacity: pending ? 0.85 : 1,
      }}>
        {text}
      </div>
    </div>
  )
}

function AssistantBubble({
  text, modelUsed, onCopy, copied,
}: { text: string; modelUsed: string | null; onCopy: () => void; copied: boolean }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', maxWidth: '92%' }}>
      <div style={{ fontSize: 13.5, lineHeight: 1.65, color: 'var(--ink)', wordBreak: 'break-word' }}>
        <MarkdownContent text={text} />
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 4 }}>
        {modelUsed && <span style={{ fontSize: 11, color: 'var(--ink-4)' }}>via {modelUsed}</span>}
        <button
          onClick={onCopy}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px', borderRadius: 'var(--r-sm)',
            border: '1px solid var(--line)', background: 'transparent', color: 'var(--ink-4)',
            fontSize: 11, cursor: 'pointer',
          }}
        >
          <Ic.Copy size={11} /> {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
    </div>
  )
}

function ThinkingRow({ partial }: { partial: string }) {
  if (partial) {
    return (
      <div style={{ maxWidth: '92%', fontSize: 13.5, lineHeight: 1.65, color: 'var(--ink)', whiteSpace: 'pre-wrap' }}>
        {partial}
        <span style={{
          display: 'inline-block', width: 2, height: '1em', background: 'var(--accent)',
          verticalAlign: 'text-bottom', animation: 'task-pulse 0.9s step-end infinite', marginLeft: 2,
        }} />
      </div>
    )
  }
  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--ink-3)' }}>
      <span style={{
        width: 14, height: 14, border: '2px solid var(--line-2)', borderTopColor: 'var(--accent)',
        borderRadius: '50%', animation: 'task-spin 0.8s linear infinite',
      }} />
      Hermes is working on this…
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function TaskDetailView({ taskId }: { taskId: string }) {
  const [detail, setDetail] = useState<TaskDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [sending, setSending] = useState(false)
  const [composer, setComposer] = useState('')
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  // Progress is cleared server-side once the task finishes (result/error_text
  // become the durable record) -- keep the last non-null snapshot around so
  // the Progress panel stays visible (collapsed) after completion.
  const [lastProgress, setLastProgress] = useState<string | null>(null)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const composerRef = useRef<HTMLTextAreaElement | null>(null)
  const bottomRef = useRef<HTMLDivElement | null>(null)

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

  // Auto-scroll the transcript to the bottom as new content lands.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'auto' })
  }, [detail?.messages, lastProgress])

  useEffect(() => {
    const active = detail ? ACTIVE_STATUSES.has(detail.status) : false
    if (!active && !sending) composerRef.current?.focus()
  }, [detail, sending])

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

  async function handleCopy(id: string, text: string) {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedId(id)
      setTimeout(() => setCopiedId((cur) => (cur === id ? null : cur)), 1500)
    } catch {
      // Clipboard permission denied or unavailable — non-fatal, just skip.
    }
  }

  async function handleSend() {
    const content = composer.trim()
    if (!content || sending || !detail || ACTIVE_STATUSES.has(detail.status)) return
    setSending(true)
    setActionError(null)
    try {
      const res = await fetch(`/api/tasks/${taskId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: content }),
      })
      const data = await res.json()
      if (!res.ok) {
        const msg = data?.detail?.message ?? data?.detail ?? 'Could not send the message.'
        setActionError(typeof msg === 'string' ? msg : JSON.stringify(msg))
        return
      }
      setComposer('')
      if (composerRef.current) composerRef.current.style.height = 'auto'
      // New turn starting -- clear the prior turn's Progress panel (the
      // server already cleared progress_* when the last turn finished) and
      // reflect the new prompt/status immediately so the pending bubble
      // below shows the right text while polling picks up the real result.
      setLastProgress(null)
      setDetail((d) => (d ? { ...d, status: data.status, finished_at: data.finished_at, prompt: content, progress: null } : d))
    } catch {
      setActionError('Network error — please try again.')
    } finally {
      setSending(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function autoResize() {
    const el = composerRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  }

  const active = detail ? ACTIVE_STATUSES.has(detail.status) : false
  const canCancel = active
  const messages = detail?.messages ?? []
  const { partial } = lastProgress ? splitProgress(lastProgress) : { partial: '' }

  return (
    <div style={{ maxWidth: 1040, margin: '0 auto', padding: '32px 24px 40px' }}>
      <style>{`
        @keyframes task-spin { to { transform: rotate(360deg) } }
        @keyframes task-pulse { 0%, 100% { opacity: 1 } 50% { opacity: 0.35 } }
        .task-detail-grid { display: flex; gap: 24px; align-items: flex-start; }
        .task-detail-sidebar { width: 260px; flex-shrink: 0; position: sticky; top: 20px; }
        @media (max-width: 768px) {
          .task-detail-grid { flex-direction: column; }
          .task-detail-sidebar { width: 100%; position: static; }
        }
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

          {/* Conversation + Progress sidebar */}
          <div className="task-detail-grid" style={{ marginTop: 20 }}>
            <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 18, marginBottom: 16 }}>
                {messages.map((m) =>
                  m.role === 'user' ? (
                    <UserBubble key={m.id} text={m.content} />
                  ) : m.role === 'assistant' ? (
                    <AssistantBubble
                      key={m.id}
                      text={m.content}
                      modelUsed={m.model_used}
                      onCopy={() => handleCopy(m.id, m.content)}
                      copied={copiedId === m.id}
                    />
                  ) : null
                )}

                {/* In-flight turn — its Message pair isn't committed until it
                    finishes, so render it from the live prompt/progress instead. */}
                {active && (
                  <>
                    <UserBubble text={detail.prompt} pending />
                    <ThinkingRow partial={partial} />
                  </>
                )}

                {detail.status === 'failed' && (
                  <div style={{
                    fontSize: 13, color: 'var(--danger)', border: '1px solid var(--danger)',
                    borderRadius: 'var(--r-md)', padding: '10px 12px', background: 'var(--danger-bg)',
                  }}>
                    {detail.error_text || 'The task failed for an unknown reason.'}
                  </div>
                )}

                {detail.status === 'cancelled' && (
                  <div style={{ fontSize: 13, color: 'var(--ink-4)', fontStyle: 'italic' }}>
                    Cancelled before it finished.
                  </div>
                )}

                <div ref={bottomRef} />
              </div>

              {/* Composer */}
              <div style={{
                border: '1px solid var(--line-2)', borderRadius: 'var(--r-md)', background: 'var(--surface)',
                padding: 12, marginTop: 'auto',
              }}>
                <textarea
                  ref={composerRef}
                  value={composer}
                  onChange={(e) => { setComposer(e.target.value); autoResize() }}
                  onKeyDown={handleKeyDown}
                  disabled={active || sending}
                  placeholder={active ? 'Hermes is working — you can send another message once this turn finishes…' : 'Send a follow-up… (Enter to send, Shift+Enter for newline)'}
                  rows={1}
                  style={{
                    width: '100%',
                    padding: '8px 4px',
                    border: 'none',
                    background: 'transparent',
                    color: 'var(--ink)',
                    fontSize: 13.5,
                    resize: 'none',
                    minHeight: 40,
                    maxHeight: 160,
                    fontFamily: 'inherit',
                    boxSizing: 'border-box',
                    outline: 'none',
                  }}
                />
                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <button
                    onClick={handleSend}
                    disabled={active || sending || !composer.trim()}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      padding: '8px 16px',
                      borderRadius: 'var(--r-md)',
                      border: 'none',
                      background: active || sending || !composer.trim() ? 'var(--surface-2)' : 'var(--accent)',
                      color: active || sending || !composer.trim() ? 'var(--ink-4)' : '#fff',
                      fontWeight: 600,
                      fontSize: 13,
                      cursor: active || sending || !composer.trim() ? 'not-allowed' : 'pointer',
                      transition: 'background 0.12s',
                    }}
                  >
                    <Ic.send size={13} />
                    {sending ? 'Sending…' : 'Send'}
                  </button>
                </div>
              </div>

              {(detail.tokens_input != null || detail.tokens_output != null) && (
                <div style={{ fontSize: 11.5, color: 'var(--ink-4)', marginTop: 10 }}>
                  {detail.tokens_input ?? 0} in · {detail.tokens_output ?? 0} out
                  {detail.cost_usd != null && ` · $${Number(detail.cost_usd).toFixed(4)}`}
                </div>
              )}

              <div style={{ fontSize: 11, color: 'var(--ink-4)', display: 'flex', alignItems: 'center', gap: 5, marginTop: 16 }}>
                <Ic.lock size={11} /> Prompt, activity log, and output are stored encrypted · governed by the policy engine
              </div>
            </div>

            <aside className="task-detail-sidebar">
              <ProgressPanel progressText={lastProgress} active={active} />
            </aside>
          </div>
        </>
      )}
    </div>
  )
}
