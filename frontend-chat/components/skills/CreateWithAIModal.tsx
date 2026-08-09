'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Ic } from '@/components/ui/Icon'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ChatTurn {
  role: 'user' | 'assistant'
  content: string
}

interface SkillDraft {
  name: string
  description: string
  instructions: string
}

const GREETING = "Tell me what you'd like this skill to do — I'll ask a few questions and draft it for you."

// ---------------------------------------------------------------------------
// CreateWithAIModal — chat-driven skill authoring
// ---------------------------------------------------------------------------

export default function CreateWithAIModal({ onClose }: { onClose: () => void }) {
  const router = useRouter()
  const [messages, setMessages] = useState<ChatTurn[]>([{ role: 'assistant', content: GREETING }])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [draft, setDraft] = useState<SkillDraft | null>(null)
  const [error, setError] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, draft])

  async function handleSend() {
    const content = input.trim()
    if (!content || sending) return
    const next: ChatTurn[] = [...messages, { role: 'user', content }]
    setMessages(next)
    setInput('')
    setSending(true)
    setError('')
    try {
      const res = await fetch('/api/skills/draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: next }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError(data.detail ?? 'Something went wrong.')
        return
      }
      const data = await res.json()
      if (data.done && data.draft) {
        setDraft(data.draft)
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: data.message || "Could you tell me more?" }])
      }
    } catch {
      setError('Backend unavailable.')
    } finally {
      setSending(false)
    }
  }

  function handleKeepRefining() {
    setDraft(null)
  }

  function handleReviewAndEdit() {
    if (!draft) return
    sessionStorage.setItem('skill_draft', JSON.stringify(draft))
    onClose()
    router.push('/skills/create')
  }

  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 16 }}>
      <div
        onClick={e => e.stopPropagation()}
        style={{ background: 'var(--surface)', borderRadius: 'var(--r-xl)', width: '100%', maxWidth: 560, height: 560, display: 'flex', flexDirection: 'column', boxShadow: 'var(--shadow-3)', overflow: 'hidden' }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '16px 20px', borderBottom: '1px solid var(--line)', flexShrink: 0 }}>
          <div style={{ width: 32, height: 32, borderRadius: 8, background: 'linear-gradient(135deg, #ff6b9d, #c44dff)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', flexShrink: 0 }}>
            <Ic.spark size={16} strokeWidth={2} />
          </div>
          <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--ink)', flex: 1 }}>Create with AI</div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-3)', padding: 4 }}>
            <Ic.x size={18} strokeWidth={2} />
          </button>
        </div>

        {!draft ? (
          <>
            {/* Chat transcript */}
            <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
              {messages.map((m, i) => (
                <div
                  key={i}
                  style={{
                    alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                    maxWidth: '85%',
                    padding: '9px 13px',
                    borderRadius: 'var(--r-lg)',
                    fontSize: 13.5,
                    lineHeight: 1.5,
                    whiteSpace: 'pre-wrap',
                    background: m.role === 'user' ? 'var(--accent)' : 'var(--surface-2)',
                    color: m.role === 'user' ? '#fff' : 'var(--ink)',
                  }}
                >
                  {m.content}
                </div>
              ))}
              {sending && (
                <div style={{ alignSelf: 'flex-start', fontSize: 12.5, color: 'var(--ink-4)', padding: '4px 13px' }}>
                  Thinking…
                </div>
              )}
            </div>

            {error && (
              <div style={{ padding: '0 20px 8px', fontSize: 12, color: '#e53e3e' }}>{error}</div>
            )}

            {/* Composer */}
            <div style={{ display: 'flex', gap: 8, padding: '14px 20px', borderTop: '1px solid var(--line)', flexShrink: 0 }}>
              <input
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
                placeholder="Describe the skill you want..."
                disabled={sending}
                style={{ flex: 1, padding: '9px 12px', borderRadius: 'var(--r-md)', border: '1px solid var(--line)', background: 'var(--surface)', fontSize: 13.5, color: 'var(--ink)', outline: 'none', boxSizing: 'border-box' }}
              />
              <button
                onClick={handleSend}
                disabled={sending || !input.trim()}
                style={{ padding: '9px 16px', borderRadius: 'var(--r-md)', border: 'none', background: sending || !input.trim() ? 'var(--ink-4)' : 'linear-gradient(135deg, #ff6b9d, #c44dff)', color: '#fff', fontWeight: 700, fontSize: 13, cursor: sending || !input.trim() ? 'not-allowed' : 'pointer' }}
              >
                Send
              </button>
            </div>
          </>
        ) : (
          <div style={{ flex: 1, overflowY: 'auto', padding: '20px', display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink-3)' }}>Here&apos;s what I drafted</div>
            <div style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', padding: 16, background: 'var(--surface-2)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, fontSize: 14.5, color: 'var(--ink)', marginBottom: 6 }}>
                <Ic.layers size={14} strokeWidth={2} style={{ color: 'var(--ink-4)' }} />
                {draft.name}
              </div>
              <div style={{ fontSize: 13, color: 'var(--ink-3)', lineHeight: 1.5, marginBottom: 12 }}>
                {draft.description}
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--ink-4)', fontWeight: 600, marginBottom: 4 }}>Instructions</div>
              <div style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.6, whiteSpace: 'pre-wrap', maxHeight: 160, overflowY: 'auto' }}>
                {draft.instructions}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button
                onClick={handleKeepRefining}
                style={{ padding: '9px 18px', borderRadius: 'var(--r-md)', border: '1px solid var(--line-2)', background: 'var(--surface)', color: 'var(--ink-2)', fontWeight: 600, fontSize: 13, cursor: 'pointer' }}
              >
                Keep refining
              </button>
              <button
                onClick={handleReviewAndEdit}
                style={{ padding: '9px 22px', borderRadius: 'var(--r-md)', border: 'none', background: 'linear-gradient(135deg, #ff6b9d, #c44dff)', color: '#fff', fontWeight: 700, fontSize: 13, cursor: 'pointer' }}
              >
                Review & edit
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
