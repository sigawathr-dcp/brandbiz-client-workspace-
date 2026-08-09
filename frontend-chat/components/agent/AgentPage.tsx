'use client'

import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Ic } from '@/components/ui/Icon'
import AboutModal from './AboutModal'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AgentItem {
  id: string
  user_id: string
  name: string
  provider: string
  model: string
  description: string | null
  instructions: string | null
  capabilities: {
    web_search?: boolean
    think_longer?: boolean
    image_gen?: boolean
    video_gen?: boolean
  } | null
  creativity_level: number
  visibility: string
  status: string
  avatar_color: string | null
  category: string | null
  created_at: string
  updated_at: string
  creator_name: string | null
}

type AgentTab = 'all' | 'mine'

// ---------------------------------------------------------------------------
// Avatar helpers
// ---------------------------------------------------------------------------

const AVATAR_COLORS = [
  '#6C63FF', '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4',
  '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE',
]

// Per-category pill colours — distinct hue per category
export const CATEGORY_COLORS: Record<string, { color: string; bg: string }> = {
  Sales:     { color: '#1D4ED8', bg: '#DBEAFE' },
  Marketing: { color: '#BE185D', bg: '#FCE7F3' },
  Product:   { color: '#6D28D9', bg: '#EDE9FE' },
  Executive: { color: '#92400E', bg: '#FEF3C7' },
  General:   { color: '#374151', bg: '#E5E7EB' },
  Engineer:  { color: '#065F46', bg: '#D1FAE5' },
  IT:        { color: '#C2410C', bg: '#FFEDD5' },
}
const DEFAULT_CATEGORY_STYLE = { color: '#374151', bg: '#E5E7EB' }

export function getCategoryStyle(category: string | null) {
  if (!category) return DEFAULT_CATEGORY_STYLE
  return CATEGORY_COLORS[category] ?? DEFAULT_CATEGORY_STYLE
}

function getAvatarColor(agent: AgentItem): string {
  if (agent.avatar_color) return agent.avatar_color
  if (agent.category) return getCategoryStyle(agent.category).color
  const idx = agent.id.charCodeAt(0) % AVATAR_COLORS.length
  return AVATAR_COLORS[idx]
}

function AgentAvatar({ agent, size = 56 }: { agent: AgentItem; size?: number }) {
  const color = getAvatarColor(agent)
  const initials = agent.name.trim().slice(0, 1).toUpperCase()
  return (
    <div style={{
      width: size,
      height: size,
      borderRadius: '50%',
      background: color,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      color: '#fff',
      fontWeight: 700,
      fontSize: size * 0.4,
      flexShrink: 0,
    }}>
      {initials}
    </div>
  )
}

// ---------------------------------------------------------------------------
// AgentCard
// ---------------------------------------------------------------------------

function AgentCard({ agent, onAbout }: { agent: AgentItem; onAbout: (a: AgentItem) => void }) {
  return (
    <div
      onClick={() => onAbout(agent)}
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--line)',
        borderRadius: 'var(--r-lg)',
        padding: 16,
        cursor: 'pointer',
        transition: 'box-shadow 0.15s, transform 0.1s',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLDivElement).style.boxShadow = 'var(--shadow-2)'
        ;(e.currentTarget as HTMLDivElement).style.transform = 'translateY(-1px)'
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLDivElement).style.boxShadow = 'none'
        ;(e.currentTarget as HTMLDivElement).style.transform = 'none'
      }}
    >
      <AgentAvatar agent={agent} size={52} />
      <div>
        <div style={{
          fontWeight: 600,
          fontSize: 13,
          color: 'var(--ink)',
          lineHeight: 1.35,
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
        }}>
          {agent.name}
        </div>
        {agent.description && (
          <div style={{
            fontSize: 11.5,
            color: 'var(--ink-3)',
            marginTop: 3,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}>
            {agent.description}
          </div>
        )}
      </div>
      {(agent.category || agent.status === 'draft') && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {agent.category && (() => {
            const cs = getCategoryStyle(agent.category)
            return (
              <span style={{
                fontSize: 10.5,
                fontWeight: 600,
                color: cs.color,
                background: cs.bg,
                padding: '2px 8px',
                borderRadius: 99,
              }}>
                {agent.category}
              </span>
            )
          })()}
          {agent.status === 'draft' && (
            <span style={{
              fontSize: 10.5,
              fontWeight: 600,
              color: 'var(--ink-3)',
              background: 'var(--surface-2)',
              padding: '2px 8px',
              borderRadius: 99,
            }}>
              Draft
            </span>
          )}
        </div>
      )}
      <div style={{ fontSize: 11, color: 'var(--ink-4)', marginTop: 'auto' }}>
        by {agent.creator_name ?? 'Core Admin'}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// EmptyState
// ---------------------------------------------------------------------------

function EmptyState({ tab }: { tab: AgentTab }) {
  const router = useRouter()
  if (tab === 'mine') {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: 320,
        gap: 12,
        color: 'var(--ink-3)',
      }}>
        <div style={{
          width: 56,
          height: 56,
          borderRadius: '50%',
          border: '2px dashed var(--line-2)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--ink-4)',
        }}>
          <Ic.cpu size={22} strokeWidth={1.5} />
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontWeight: 600, fontSize: 15, color: 'var(--ink-2)' }}>No Agent</div>
          <div style={{ fontSize: 13, color: 'var(--ink-4)', marginTop: 4 }}>
            You haven&apos;t created any agents yet.
          </div>
        </div>
        <button
          onClick={() => router.push('/agent/create')}
          style={{
            padding: '9px 20px',
            borderRadius: 'var(--r-md)',
            border: 'none',
            background: 'var(--accent)',
            color: '#fff',
            fontWeight: 600,
            fontSize: 13,
            cursor: 'pointer',
          }}
        >
          Create your first agent
        </button>
      </div>
    )
  }
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: 320,
      gap: 8,
      color: 'var(--ink-3)',
    }}>
      <Ic.cpu size={32} strokeWidth={1.4} />
      <div style={{ fontWeight: 600, fontSize: 15, color: 'var(--ink-2)' }}>No agents found</div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// AgentPage (main)
// ---------------------------------------------------------------------------

export default function AgentPage() {
  const router = useRouter()
  const [tab, setTab] = useState<AgentTab>('all')
  const [agents, setAgents] = useState<AgentItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [q, setQ] = useState('')
  const [aboutAgent, setAboutAgent] = useState<AgentItem | null>(null)

  const loadAgents = useCallback(async () => {
    setLoading(true)
    try {
      const scope = tab === 'mine' ? 'mine' : 'all'
      const qs = new URLSearchParams({ scope, limit: '200' })
      if (q.trim()) qs.set('q', q.trim())
      const res = await fetch(`/api/agent?${qs}`, { cache: 'no-store' })
      if (res.ok) {
        const data = await res.json()
        setAgents(data.items ?? [])
        setTotal(data.total ?? 0)
      }
    } finally {
      setLoading(false)
    }
  }, [tab, q])

  useEffect(() => {
    const timer = setTimeout(loadAgents, q ? 300 : 0)
    return () => clearTimeout(timer)
  }, [loadAgents, q])

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1200, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink)', margin: 0 }}>
          {tab === 'all' ? 'All AI Agent' : 'My Agent'}
        </h1>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <button
            onClick={() => setTab(tab === 'all' ? 'mine' : 'all')}
            style={{
              padding: '7px 16px',
              borderRadius: 'var(--r-md)',
              border: '1px solid var(--line-2)',
              background: 'var(--surface)',
              color: 'var(--ink-2)',
              fontWeight: 600,
              fontSize: 13,
              cursor: 'pointer',
            }}
          >
            {tab === 'all' ? 'My Agent' : 'All AI Agent'}
          </button>
          <button
            onClick={() => router.push('/agent/create')}
            style={{
              padding: '7px 16px',
              borderRadius: 'var(--r-md)',
              border: 'none',
              background: 'linear-gradient(135deg, #ff6b9d, #c44dff)',
              color: '#fff',
              fontWeight: 700,
              fontSize: 13,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <Ic.plus size={14} strokeWidth={2.5} />
            Create Agent
          </button>
        </div>
      </div>

      {/* Tab indicator */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 18, fontSize: 13.5, color: 'var(--ink-3)' }}>
        <button
          onClick={() => setTab('all')}
          style={{
            background: 'none', border: 'none', padding: 0, cursor: 'pointer',
            fontWeight: tab === 'all' ? 700 : 500,
            color: tab === 'all' ? 'var(--ink)' : 'var(--ink-3)',
            borderBottom: tab === 'all' ? '2px solid var(--accent)' : '2px solid transparent',
            paddingBottom: 4,
          }}
        >
          All AI Agent
        </button>
        <span style={{ color: 'var(--line-2)' }}>•</span>
        <button
          onClick={() => setTab('mine')}
          style={{
            background: 'none', border: 'none', padding: 0, cursor: 'pointer',
            fontWeight: tab === 'mine' ? 700 : 500,
            color: tab === 'mine' ? 'var(--ink)' : 'var(--ink-3)',
            borderBottom: tab === 'mine' ? '2px solid var(--accent)' : '2px solid transparent',
            paddingBottom: 4,
          }}
        >
          My Agent
        </button>
      </div>

      {/* Search */}
      <div style={{ position: 'relative', marginBottom: 16, maxWidth: 380 }}>
        <Ic.search size={14} strokeWidth={2} style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', color: 'var(--ink-4)' }} />
        <input
          value={q}
          onChange={e => setQ(e.target.value)}
          placeholder="Search agents..."
          style={{
            width: '100%',
            padding: '8px 12px 8px 34px',
            borderRadius: 'var(--r-md)',
            border: '1px solid var(--line)',
            background: 'var(--surface)',
            fontSize: 13.5,
            color: 'var(--ink)',
            outline: 'none',
            boxSizing: 'border-box',
          }}
        />
      </div>

      {/* Count */}
      {!loading && (
        <div style={{ fontSize: 13, color: 'var(--ink-3)', marginBottom: 16 }}>
          {total} agent{total !== 1 ? 's' : ''} available
        </div>
      )}

      {/* Grid */}
      {loading ? (
        <div style={{ color: 'var(--ink-3)', fontSize: 13 }}>Loading…</div>
      ) : agents.length === 0 ? (
        <EmptyState tab={tab} />
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
          gap: 14,
        }}>
          {agents.map(agent => (
            <AgentCard key={agent.id} agent={agent} onAbout={setAboutAgent} />
          ))}
        </div>
      )}

      {/* About modal */}
      {aboutAgent && (
        <AboutModal
          agent={aboutAgent}
          onClose={() => setAboutAgent(null)}
        />
      )}
    </div>
  )
}
