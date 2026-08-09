'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import TierBadge from './TierBadge'
import ModelPicker from './ModelPicker'
import ResponseModePicker, { type ResponseMode } from './ResponseModePicker'
import ReasoningLevelPicker, { type ReasoningLevel } from './ReasoningLevelPicker'
import { Ic } from './ui/Icon'
import UiTierBadge from './ui/TierBadge'
import { MarkdownContent } from './ui/Markdown'
import { detectTier } from '@/lib/classifier'
import { TIERS } from '@/lib/domain'
import type { TierKey } from '@/lib/domain'
import { useConversations } from './ConversationsProvider'
import { useIsMobile } from '@/lib/useIsMobile'
import { readSSE } from '@/lib/sse'

const OPTIMISTIC_TITLE_MAX = 40

function truncateTitle(content: string): string {
  const trimmed = content.trim()
  return trimmed.length > OPTIMISTIC_TITLE_MAX
    ? trimmed.slice(0, OPTIMISTIC_TITLE_MAX).trimEnd() + '…'
    : trimmed
}

// ---------------------------------------------------------------------------
// ThinkingDots
// ---------------------------------------------------------------------------

function ThinkingDots() {
  return (
    <div style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      fontSize: 12,
      color: 'var(--ink-3)',
    }}>
      {[0, 1, 2].map(n => (
        <span
          key={n}
          style={{
            display: 'inline-block',
            width: 5,
            height: 5,
            borderRadius: '50%',
            background: 'var(--ink-3)',
            animation: 'blink 1.2s step-end infinite',
            animationDelay: `${n * 0.25}s`,
          }}
        />
      ))}
      <span style={{ marginLeft: 2, fontStyle: 'italic' }}>routing through the policy engine…</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// PolicyHint — appears above composer when tier ≥ T2
// ---------------------------------------------------------------------------

function PolicyHint({ tier, mode }: { tier: TierKey; mode: 'banner' | 'badge' | 'subtle' }) {
  if (tier === 'T1') return null
  const t = TIERS[tier]
  if (mode === 'subtle') return null
  if (mode === 'badge') {
    return (
      <div style={{ padding: '0 0 8px' }}>
        <UiTierBadge tier={tier} mode="subtle" />
      </div>
    )
  }
  // banner (default)
  return (
    <div style={{
      display: 'flex',
      alignItems: 'flex-start',
      gap: 9,
      padding: '10px 14px',
      marginBottom: 10,
      background: t.bg,
      borderRadius: 'var(--r-md)',
      fontSize: 12.5,
      color: 'var(--ink-2)',
      lineHeight: 1.4,
      border: `1px solid ${t.color}30`,
    }}>
      <Ic.info size={14} style={{ color: t.color, flexShrink: 0, marginTop: 1 }} />
      <span>
        <strong style={{ color: t.color }}>Classified as {tier}</strong>
        {' · '}{t.description}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Welcome / empty-state
// ---------------------------------------------------------------------------

const SUGGESTIONS = [
  { icon: 'message' as const, label: 'Draft an email',         prompt: 'Write a professional email to ' },
  { icon: 'search' as const,  label: 'Summarise a document',   prompt: 'Summarise the following document:\n\n' },
  { icon: 'cpu' as const,     label: 'Generate code',          prompt: 'Write a function in Python that ' },
  { icon: 'dollar' as const,  label: 'Analyse an expense',     prompt: 'Analyse this expense report:\n\n' },
]

function Welcome({ firstName, onSelect }: { firstName: string; onSelect: (text: string) => void }) {
  const isMobile = useIsMobile()
  return (
    <div style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '40px 24px',
      animation: 'fadeIn 0.3s ease',
    }}>
      {/* Shield tile */}
      <div style={{
        width: 52,
        height: 52,
        borderRadius: 'var(--r-lg)',
        background: 'var(--accent)',
        color: '#fff',
        display: 'grid',
        placeItems: 'center',
        marginBottom: 20,
        boxShadow: '0 4px 16px rgba(79,70,229,.28)',
      }}>
        <Ic.shield size={28} strokeWidth={2} />
      </div>

      {/* Thai greeting */}
      <h2 style={{ fontSize: 21, fontWeight: 700, color: 'var(--ink)', margin: '0 0 6px', letterSpacing: '-.01em' }}>
        สวัสดี{firstName ? `, ${firstName}` : ''} 👋
      </h2>
      <p style={{ fontSize: 13, color: 'var(--ink-3)', margin: '0 0 28px', textAlign: 'center', maxWidth: 340, lineHeight: 1.6 }}>
        Every message is classified, routed through the policy engine, and end-to-end encrypted before storage.
      </p>

      {/* 2×2 suggestion grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, 1fr)',
        gap: 10,
        width: '100%',
        maxWidth: 500,
      }}>
        {SUGGESTIONS.map(s => {
          const IconComp = Ic[s.icon]
          return (
            <button
              key={s.label}
              type="button"
              onClick={() => onSelect(s.prompt)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '13px 15px',
                background: 'var(--surface)',
                border: '1px solid var(--line)',
                borderRadius: 'var(--r-md)',
                color: 'var(--ink-2)',
                fontSize: 13,
                fontWeight: 500,
                cursor: 'pointer',
                textAlign: 'left',
                boxShadow: 'var(--shadow-1)',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.borderColor = 'var(--accent)'
                e.currentTarget.style.background = 'var(--accent-weak)'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.borderColor = 'var(--line)'
                e.currentTarget.style.background = 'var(--surface)'
              }}
            >
              {IconComp && <IconComp size={16} style={{ color: 'var(--accent)', flexShrink: 0 }} />}
              {s.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// SourcesPanel — collapsible RAG citations footer
// ---------------------------------------------------------------------------

function SourcesPanel({ sources }: { sources: { file_id: string; filename: string; chunk_index: number; score: number }[] }) {
  if (!sources.length) return null
  return (
    <details style={{ marginTop: 6 }}>
      <summary style={{
        fontSize: 11,
        color: 'var(--ink-muted, #888)',
        cursor: 'pointer',
        userSelect: 'none',
        listStyle: 'none',
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
      }}>
        <span style={{ fontSize: 9, opacity: 0.7 }}>▶</span>
        {`Sources (${sources.length})`}
      </summary>
      <div style={{ marginTop: 4, paddingLeft: 4, borderLeft: '2px solid var(--border, #e0e0e0)' }}>
        {sources.map((s) => (
          <div key={`${s.file_id}:${s.chunk_index}`} style={{
            fontSize: 11,
            color: 'var(--ink-muted, #888)',
            padding: '2px 0',
            display: 'flex',
            gap: 6,
            alignItems: 'baseline',
          }}>
            <span style={{ fontWeight: 500, color: 'var(--ink, #333)' }}>{s.filename}</span>
            <span>{`· chunk #${s.chunk_index}`}</span>
            <span>{`· score ${s.score.toFixed(2)}`}</span>
          </div>
        ))}
      </div>
    </details>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface Source {
  file_id: string
  filename: string
  chunk_index: number
  score: number
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  imageUrl?: string
  sources?: Source[]
  model?: string
  downgraded?: boolean
  reason?: string
  tier?: TierKey
  tokensIn?: number
  tokensOut?: number
  // G-A2: only meaningful for the turn that just streamed — not persisted,
  // same "live only" treatment as downgraded/reason above.
  thinkingShown?: boolean
  reasoningNote?: string
}

interface ChatSSEEvent {
  type: string
  conversation_id?: string
  model?: string
  event?: string
  reason?: string
  delta?: string
  message?: string
  tokens_input?: number
  tokens_output?: number
  url?: string
  sources?: Source[]
  requested?: string
}

interface ChatPaneProps {
  conversationId: string | null
  initialMessages: Message[]
  initialAgentId?: string | null
}

interface AgentChip {
  id: string
  name: string
  model: string
  avatar_color: string | null
}

export default function ChatPane({ conversationId, initialMessages, initialAgentId }: ChatPaneProps) {
  const [messages, setMessages]               = useState<Message[]>(initialMessages)
  const [streamingContent, setStreamingContent] = useState('')
  const [pendingModel, setPendingModel]       = useState<string | undefined>()
  const [pendingDowngraded, setPendingDowngraded] = useState(false)
  const [pendingReason, setPendingReason]     = useState<string | undefined>()
  const [pendingTier, setPendingTier]         = useState<TierKey | undefined>()
  const [input, setInput]                     = useState('')
  const [isStreaming, setIsStreaming]         = useState(false)
  const [currentConvId, setCurrentConvId]     = useState<string | null>(conversationId)
  const [selectedModel, setSelectedModel]     = useState('auto')
  const [mode, setMode]                       = useState<ResponseMode>('instant')
  const [reasoningLevel, setReasoningLevel]   = useState<ReasoningLevel | null>(null)
  const [pendingThinking, setPendingThinking] = useState(false)
  const [pendingReasoningNote, setPendingReasoningNote] = useState<string | undefined>()
  const [firstName, setFirstName]             = useState('')
  const [tierComms, setTierComms]             = useState<'banner' | 'badge' | 'subtle'>('banner')
  const [agentChip, setAgentChip]             = useState<AgentChip | null>(null)
  const router = useRouter()
  const { addOptimistic } = useConversations()
  const bottomRef   = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  // Persist agent_id across turns in the same conversation
  const agentIdRef = useRef<string | null>(initialAgentId ?? null)
  // Coalesce per-token streaming updates into one React render per animation frame
  const rafRef = useRef<number | null>(null)
  const pendingContentRef = useRef('')
  // Guards the preferences-PATCH effect from firing (with defaults) before
  // the /api/me seed below has had a chance to run.
  const prefsLoadedRef = useRef(false)
  const prefsPatchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const scheduleStreamingContent = useCallback((value: string) => {
    pendingContentRef.current = value
    if (rafRef.current === null) {
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = null
        setStreamingContent(pendingContentRef.current)
      })
    }
  }, [])

  // Cancel any in-flight coalesced streaming update on unmount
  useEffect(() => {
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    }
  }, [])

  // Load agent chip info if an agent is associated with this conversation
  useEffect(() => {
    const aid = agentIdRef.current
    if (!aid) return
    fetch(`/api/agent/${aid}`, { cache: 'no-store' })
      .then(r => r.ok ? r.json() : null)
      .then((data: { id: string; name: string; model: string; avatar_color: string | null } | null) => {
        if (!data) return
        setAgentChip({ id: data.id, name: data.name, model: data.model, avatar_color: data.avatar_color })
      })
      .catch(() => {})
  }, [])

  // Fetch user first name for welcome greeting, and seed the model/mode/
  // reasoning-level composer selections from the server-persisted blob
  // (Commit 2 — replaces the localStorage draft of this that never shipped).
  useEffect(() => {
    fetch('/api/me')
      .then(r => r.ok ? r.json() : null)
      .then((d: {
        display_name?: string
        email?: string
        preferences?: { model?: string; mode?: ResponseMode; reasoning_level?: ReasoningLevel }
      } | null) => {
        if (!d) return
        const name = d.display_name ?? d.email ?? ''
        setFirstName(name.split(/[\s@]/)[0])

        const prefs = d.preferences
        if (prefs?.model) setSelectedModel(prefs.model)
        if (prefs?.mode) setMode(prefs.mode)
        if (prefs?.reasoning_level) setReasoningLevel(prefs.reasoning_level)
      })
      .catch(() => {})
      .finally(() => { prefsLoadedRef.current = true })
  }, [])

  // Debounced PATCH of the composer selections so they survive a reload and
  // follow the user across devices/browsers.
  useEffect(() => {
    if (!prefsLoadedRef.current) return
    if (prefsPatchTimerRef.current) clearTimeout(prefsPatchTimerRef.current)
    prefsPatchTimerRef.current = setTimeout(() => {
      fetch('/api/me/preferences', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: selectedModel,
          mode,
          ...(reasoningLevel ? { reasoning_level: reasoningLevel } : {}),
        }),
      }).catch(() => {})
    }, 500)
    return () => {
      if (prefsPatchTimerRef.current) clearTimeout(prefsPatchTimerRef.current)
    }
  }, [selectedModel, mode, reasoningLevel])

  useEffect(() => {
    const container = scrollContainerRef.current
    // Only auto-scroll if the user is already near the bottom, so we don't
    // yank them back down while they're reading earlier messages, and use
    // instant scrolling so per-token updates don't queue smooth-scroll animations.
    if (container) {
      const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 120
      if (!nearBottom) return
    }
    bottomRef.current?.scrollIntoView({ behavior: 'auto' })
  }, [messages, streamingContent])

  useEffect(() => {
    if (!isStreaming) textareaRef.current?.focus()
  }, [isStreaming])

  const autoResize = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 180) + 'px'
  }, [])

  // Live tier classification of composer input (display-only)
  const liveTier = input.trim().length > 2 ? detectTier(input) : null

  async function sendMessage() {
    const content = input.trim()
    if (!content || isStreaming) return

    setInput('')
    if (textareaRef.current) { textareaRef.current.style.height = 'auto' }
    setIsStreaming(true)
    setMessages(prev => [...prev, { role: 'user', content }])
    if (rafRef.current !== null) { cancelAnimationFrame(rafRef.current); rafRef.current = null }
    pendingContentRef.current = ''
    setStreamingContent('')
    setPendingModel(undefined)
    setPendingDowngraded(false)
    setPendingReason(undefined)
    setPendingTier(undefined)
    setPendingThinking(false)
    setPendingReasoningNote(undefined)

    let turnModel: string | undefined
    let turnDowngraded = false
    let turnReason: string | undefined
    let turnTier: TierKey | undefined
    let turnTokensIn: number | undefined
    let turnTokensOut: number | undefined
    let turnImageUrl: string | undefined
    let turnSources: Source[] | undefined
    let turnThinking = false
    let turnReasoningNote: string | undefined
    let isNewConversation = false

    try {
      const chatBody: Record<string, unknown> = {
        conversation_id: currentConvId,
        content,
        model: agentIdRef.current ? 'auto' : selectedModel,
        mode,
      }
      if (agentIdRef.current) chatBody.agent_id = agentIdRef.current
      if (mode !== 'instant' && reasoningLevel) chatBody.reasoning_level = reasoningLevel

      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(chatBody),
      })

      if (!res.ok) {
        const text = await res.text()
        setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${text}` }])
        return
      }

      let fullResponse = ''

      for await (const event of readSSE(res) as AsyncGenerator<ChatSSEEvent>) {
        if (event.type === 'start') {
          if (event.conversation_id && !currentConvId) {
            setCurrentConvId(event.conversation_id)
            window.history.replaceState({}, '', `/chat/${event.conversation_id}`)
            isNewConversation = true
            addOptimistic({
              id: event.conversation_id,
              title: truncateTitle(content),
              updated_at: new Date().toISOString(),
            })
          }
          if (event.model) {
            turnModel = event.model
            setPendingModel(event.model)
            turnTier = 'T1'
            setPendingTier('T1')
          }
        } else if (event.type === 'notice' && event.event === 'downgrade_to_local') {
          turnDowngraded = true
          setPendingDowngraded(true)
          if (event.reason) { turnReason = event.reason; setPendingReason(event.reason) }
          if (event.model)  { turnModel = event.model;   setPendingModel(event.model) }
          if (event.reason === 'tier_blocks_external') {
            turnTier = 'T3'
            setPendingTier('T3')
          } else {
            turnTier = undefined
            setPendingTier(undefined)
          }
        } else if (event.type === 'notice' && event.event === 'reasoning_unavailable') {
          turnReasoningNote = `Thinking isn't available on ${event.model} — answered normally.`
          setPendingReasoningNote(turnReasoningNote)
        } else if (event.type === 'notice' && event.event === 'reasoning_started') {
          turnThinking = true
          setPendingThinking(true)
        } else if (event.type === 'image' && event.url) {
          turnImageUrl = event.url
        } else if (event.type === 'sources' && event.sources?.length) {
          turnSources = event.sources
        } else if (event.type === 'content' && event.delta) {
          // Real text has started — the "Thinking…" pill has done its job.
          if (turnThinking) { turnThinking = false; setPendingThinking(false) }
          fullResponse += event.delta
          scheduleStreamingContent(fullResponse)
        } else if (event.type === 'done') {
          if (event.tokens_input !== undefined) turnTokensIn = event.tokens_input
          if (event.tokens_output !== undefined) turnTokensOut = event.tokens_output
          if (rafRef.current !== null) { cancelAnimationFrame(rafRef.current); rafRef.current = null }
          setMessages(prev => [
            ...prev,
            {
              role: 'assistant',
              content: fullResponse,
              imageUrl: turnImageUrl,
              sources: turnSources,
              model: turnModel,
              downgraded: turnDowngraded || undefined,
              reason: turnReason,
              tier: turnTier,
              tokensIn: turnTokensIn,
              tokensOut: turnTokensOut,
              thinkingShown: turnThinking || undefined,
              reasoningNote: turnReasoningNote,
            },
          ])
          pendingContentRef.current = ''
          setStreamingContent('')
          setPendingThinking(false)
          setPendingReasoningNote(undefined)
        } else if (event.type === 'error') {
          if (rafRef.current !== null) { cancelAnimationFrame(rafRef.current); rafRef.current = null }
          setMessages(prev => [
            ...prev,
            { role: 'assistant', content: `Error: ${event.message ?? 'Unknown error'}` },
          ])
          pendingContentRef.current = ''
          setStreamingContent('')
          setPendingThinking(false)
          setPendingReasoningNote(undefined)
        }
      }
    } catch {
      if (rafRef.current !== null) { cancelAnimationFrame(rafRef.current); rafRef.current = null }
      setMessages(prev => [...prev, { role: 'assistant', content: 'Network error. Please try again.' }])
      pendingContentRef.current = ''
      setStreamingContent('')
    } finally {
      setIsStreaming(false)
      // Refetch server-rendered state once the turn settles, for a brand-new
      // conversation (so the sidebar/title picks it up) — regardless of
      // whether the turn ended in `done`, `error`, or a network failure. The
      // conversation row is committed before the SSE stream starts, so it's
      // safe to refresh as soon as we know one was created.
      if (isNewConversation) router.refresh()
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const isEmpty = messages.length === 0 && !isStreaming

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      overflow: 'hidden',
      background: 'var(--bg)',
    }}>

      {/* Header bar */}
      <div style={{
        flexShrink: 0,
        height: 48,
        borderBottom: '1px solid var(--line)',
        background: 'var(--surface)',
        display: 'flex',
        alignItems: 'center',
        padding: '0 20px',
        gap: 10,
      }}>
        {agentChip ? (
          <span style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            fontSize: 13,
            fontWeight: 600,
            color: 'var(--ink)',
          }}>
            {/* Agent avatar dot */}
            <span style={{
              width: 22,
              height: 22,
              borderRadius: '50%',
              background: agentChip.avatar_color ?? '#6C63FF',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#fff',
              fontWeight: 700,
              fontSize: 10,
              flexShrink: 0,
            }}>
              {agentChip.name.trim().slice(0, 1).toUpperCase()}
            </span>
            {agentChip.name}
            <span style={{ fontWeight: 400, color: 'var(--ink-3)', fontSize: 12 }}>
              ({agentChip.model})
            </span>
            <button
              onClick={() => router.push('/agent')}
              style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'var(--ink-4)', display: 'flex' }}
            >
              <Ic.info size={13} strokeWidth={2} />
            </button>
          </span>
        ) : (
          <span style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 7,
            fontSize: 12.5,
            fontWeight: 600,
            color: 'var(--t1)',
          }}>
            <Ic.shield size={15} strokeWidth={2.1} />
            Policy gateway active
            <span style={{ fontWeight: 400, color: 'var(--ink-3)', fontSize: 12 }}>
              · every message is classified before it routes
            </span>
          </span>
        )}
      </div>

      {/* Message list */}
      <div ref={scrollContainerRef} style={{
        flex: 1,
        overflowY: 'auto',
        padding: isEmpty ? 0 : '24px 0',
        display: 'flex',
        flexDirection: 'column',
      }}>
        {isEmpty
          ? <Welcome firstName={firstName} onSelect={t => { setInput(t); setTimeout(() => { textareaRef.current?.focus(); autoResize() }, 0) }} />
          : (
            <div style={{ maxWidth: 760, width: '100%', margin: '0 auto', padding: '0 20px', display: 'flex', flexDirection: 'column', gap: 20 }}>
              {messages.map((msg, i) => (
                msg.role === 'user'
                  ? (
                    /* User bubble — right-aligned, accent */
                    <div key={i} style={{ display: 'flex', justifyContent: 'flex-end', animation: 'fadeUp 0.2s ease' }}>
                      <div style={{
                        maxWidth: '72%',
                        padding: '11px 16px',
                        borderRadius: '16px 16px 4px 16px',
                        background: 'var(--accent)',
                        color: '#fff',
                        fontSize: 14,
                        lineHeight: 1.6,
                        wordBreak: 'break-word',
                        whiteSpace: 'pre-wrap',
                      }}>
                        {msg.content}
                      </div>
                    </div>
                  )
                  : (
                    /* Assistant — body text + meta footer */
                    <div key={i} style={{ display: 'flex', flexDirection: 'column', animation: 'fadeUp 0.2s ease', maxWidth: '88%' }}>
                      <div style={{
                        fontSize: 14,
                        lineHeight: 1.7,
                        color: 'var(--ink)',
                        wordBreak: 'break-word',
                        paddingBottom: 2,
                      }}>
                        {msg.imageUrl
                          ? <img src={msg.imageUrl} alt="Generated image" style={{ maxWidth: '100%', borderRadius: 8, display: 'block' }} />
                          : <MarkdownContent text={msg.content} />
                        }
                      </div>
                      {msg.model && (
                        <TierBadge
                          model={msg.model}
                          downgraded={msg.downgraded}
                          reason={msg.reason}
                          tier={msg.tier}
                          tokensIn={msg.tokensIn}
                          tokensOut={msg.tokensOut}
                        />
                      )}
                      {msg.sources && msg.sources.length > 0 && (
                        <SourcesPanel sources={msg.sources} />
                      )}
                      {msg.reasoningNote && (
                        <span style={{ fontSize: 11, color: 'var(--ink-4)', marginTop: 2 }}>
                          {msg.reasoningNote}
                        </span>
                      )}
                    </div>
                  )
              ))}

              {/* Streaming assistant message */}
              {(streamingContent || (isStreaming && !streamingContent)) && (
                <div style={{ display: 'flex', flexDirection: 'column', animation: 'fadeUp 0.15s ease', maxWidth: '88%' }}>
                  {pendingThinking && !streamingContent && (
                    <span style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 5,
                      fontSize: 11,
                      fontWeight: 600,
                      color: 'var(--accent)',
                      background: 'var(--accent-weak)',
                      padding: '3px 9px',
                      borderRadius: 99,
                      marginBottom: 6,
                      alignSelf: 'flex-start',
                    }}>
                      <Ic.sliders size={11} strokeWidth={2.2} />
                      Thinking…
                    </span>
                  )}
                  <div style={{
                    fontSize: 14,
                    lineHeight: 1.7,
                    color: 'var(--ink)',
                    wordBreak: 'break-word',
                    paddingBottom: 2,
                    minHeight: 28,
                  }}>
                    {streamingContent
                      ? (
                        <>
                          {/* Plain text while streaming — avoids re-parsing markdown on
                              every token. Full markdown rendering kicks in once the
                              message is committed to `messages` after `done`. */}
                          <span style={{ whiteSpace: 'pre-wrap' }}>{streamingContent}</span>
                          <span style={{
                            display: 'inline-block',
                            width: 2,
                            height: '1em',
                            background: 'var(--accent)',
                            verticalAlign: 'text-bottom',
                            animation: 'blink 0.8s step-end infinite',
                            marginLeft: 2,
                          }} />
                        </>
                      )
                      : <ThinkingDots />
                    }
                  </div>
                  {pendingModel && (
                    <TierBadge
                      model={pendingModel}
                      downgraded={pendingDowngraded || undefined}
                      reason={pendingReason}
                      tier={pendingTier}
                    />
                  )}
                  {pendingReasoningNote && (
                    <span style={{ fontSize: 11, color: 'var(--ink-4)', marginTop: 2 }}>
                      {pendingReasoningNote}
                    </span>
                  )}
                </div>
              )}

              <div ref={bottomRef} />
            </div>
          )
        }
      </div>

      {/* Composer area */}
      <div style={{
        flexShrink: 0,
        padding: '10px 20px 16px',
        background: 'var(--bg)',
      }}>
        <div style={{ maxWidth: 760, margin: '0 auto' }}>

          {/* Policy hint (above composer) */}
          {liveTier && liveTier.tier !== 'T1' && (
            <PolicyHint tier={liveTier.tier} mode={tierComms} />
          )}

          {/* Composer card */}
          <div style={{
            background: 'var(--surface)',
            border: '1px solid var(--line)',
            borderRadius: 'var(--r-xl)',
            boxShadow: 'var(--shadow-2)',
          }}>
            {/* Textarea */}
            <textarea
              ref={textareaRef}
              value={input}
              onChange={e => { setInput(e.target.value); autoResize() }}
              onKeyDown={handleKeyDown}
              placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
              disabled={isStreaming}
              rows={1}
              style={{
                display: 'block',
                width: '100%',
                padding: '14px 16px 6px',
                background: 'transparent',
                border: 'none',
                color: 'var(--ink)',
                fontSize: 14,
                lineHeight: 1.6,
                resize: 'none',
                outline: 'none',
                minHeight: 46,
                maxHeight: 180,
                overflowY: 'auto',
                fontFamily: 'inherit',
                boxSizing: 'border-box',
              }}
            />

            {/* Composer bottom bar */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '6px 10px 10px',
            }}>
              {/* Live tier chip (left side) */}
              {liveTier && liveTier.tier !== 'T1' ? (
                <span style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 5,
                  fontSize: 11.5,
                  fontWeight: 600,
                  color: TIERS[liveTier.tier].color,
                  background: TIERS[liveTier.tier].bg,
                  padding: '3px 10px',
                  borderRadius: 99,
                  transition: 'all 0.2s',
                  userSelect: 'none',
                }}>
                  <Ic.shield size={11} strokeWidth={2.2} />
                  classified as {liveTier.tier}
                </span>
              ) : (
                <span style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 5,
                  fontSize: 11.5,
                  color: 'var(--ink-4)',
                  userSelect: 'none',
                }}>
                  <Ic.shield size={11} strokeWidth={1.8} />
                  T1 · General
                </span>
              )}

              <div style={{ flex: 1 }} />

              <ResponseModePicker value={mode} onChange={setMode} />
              {mode !== 'instant' && (
                <ReasoningLevelPicker
                  value={reasoningLevel}
                  onChange={setReasoningLevel}
                  disabled={isStreaming}
                />
              )}

              <ModelPicker value={selectedModel} onChange={setSelectedModel} />

              {/* Send button — 40×40 rounded */}
              <button
                type="button"
                onClick={sendMessage}
                disabled={isStreaming || !input.trim()}
                title="Send"
                style={{
                  width: 40,
                  height: 40,
                  flexShrink: 0,
                  display: 'grid',
                  placeItems: 'center',
                  borderRadius: 'var(--r-md)',
                  background: isStreaming || !input.trim() ? 'var(--surface-2)' : 'var(--accent)',
                  color: isStreaming || !input.trim() ? 'var(--ink-4)' : '#fff',
                  border: 'none',
                  cursor: isStreaming || !input.trim() ? 'default' : 'pointer',
                  transition: 'background 0.15s, color 0.15s',
                  boxShadow: isStreaming || !input.trim() ? 'none' : '0 2px 8px rgba(79,70,229,.35)',
                }}
              >
                {isStreaming
                  ? <Ic.RefreshCw size={17} style={{ animation: 'spin 1s linear infinite' }} />
                  : <Ic.send size={17} strokeWidth={2} />
                }
              </button>
            </div>
          </div>

          {/* Retention footnote */}
          <p style={{
            marginTop: 8,
            fontSize: 10.5,
            color: 'var(--ink-4)',
            textAlign: 'center',
            lineHeight: 1.5,
          }}>
            All messages are logged, AES-256 encrypted, and auto-deleted after 30 days.
            Tier 3/4 data stays on the local model. Decryption requires 4-eyes admin approval.
          </p>
        </div>
      </div>
    </div>
  )
}
