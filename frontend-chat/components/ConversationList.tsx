'use client'

import { useEffect } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Ic } from './ui/Icon'
import NavSidebar from './NavSidebar'
import { detectTier } from '@/lib/classifier'
import { useConversations } from './ConversationsProvider'

interface Message {
  role: string
  content: string
  tier?: string
}

interface Conversation {
  id: string
  title: string | null
  updated_at: string
  messages?: Message[]
}

interface UserInfo {
  id: string
  email: string
  display_name: string | null
  avatar_url: string | null
  role: string
}

interface ConversationListProps {
  conversations: Conversation[]
  user: UserInfo | null
}

function groupByRecency(convs: Conversation[]) {
  const now = Date.now()
  const DAY = 86_400_000
  const groups: { label: string; items: Conversation[] }[] = [
    { label: 'Today',     items: [] },
    { label: 'Yesterday', items: [] },
    { label: 'This week', items: [] },
    { label: 'Earlier',   items: [] },
  ]
  for (const c of convs) {
    const age = now - new Date(c.updated_at).getTime()
    if (age < DAY)          groups[0].items.push(c)
    else if (age < 2 * DAY) groups[1].items.push(c)
    else if (age < 7 * DAY) groups[2].items.push(c)
    else                    groups[3].items.push(c)
  }
  return groups.filter(g => g.items.length > 0)
}

/** Returns true if conversation has any T3/T4 messages (sensitive) */
function isSensitive(conv: Conversation): boolean {
  if (conv.messages) {
    return conv.messages.some(m => {
      if (m.tier === 'T3' || m.tier === 'T4') return true
      // Fall back to client-side classifier on content
      if (m.role === 'user') {
        const result = detectTier(m.content ?? '')
        return result.tier === 'T3' || result.tier === 'T4'
      }
      return false
    })
  }
  // If no messages loaded, check title as heuristic
  if (conv.title) {
    const result = detectTier(conv.title)
    return result.tier === 'T3' || result.tier === 'T4'
  }
  return false
}

export default function ConversationList({ conversations, user }: ConversationListProps) {
  const pathname = usePathname()
  const { optimistic, removeOptimistic } = useConversations()

  // Once the server list picks up an optimistically-added conversation
  // (with its real generated title), drop it from the optimistic store so
  // the server row becomes the single source of truth.
  useEffect(() => {
    for (const conv of optimistic) {
      if (conversations.some(c => c.id === conv.id)) removeOptimistic(conv.id)
    }
  }, [conversations, optimistic, removeOptimistic])

  const merged = [
    ...optimistic.filter(c => !conversations.some(sc => sc.id === c.id)),
    ...conversations,
  ]
  const groups = groupByRecency(merged)

  return (
    <NavSidebar user={user}>
      {groups.length === 0 && (
        <p style={{ color: 'var(--ink-4)', fontSize: 12.5, textAlign: 'center', marginTop: 28, lineHeight: 1.7 }}>
          No conversations yet.
        </p>
      )}
      {groups.map(group => (
        <div key={group.label} style={{ marginBottom: 10 }}>
          <div style={{
            padding: '8px 8px 4px',
            fontSize: 11,
            fontWeight: 600,
            color: 'var(--ink-4)',
            textTransform: 'uppercase',
            letterSpacing: '.04em',
          }}>
            {group.label}
          </div>
          {group.items.map(conv => {
            const isActive = pathname === `/chat/${conv.id}`
            const sensitive = isSensitive(conv)
            return (
              <Link key={conv.id} href={`/chat/${conv.id}`} style={{ display: 'block', textDecoration: 'none' }}>
                <div
                  style={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '8px 9px',
                    borderRadius: 'var(--r-sm)',
                    marginBottom: 1,
                    background: isActive ? 'var(--accent-weak)' : 'transparent',
                    color: isActive ? 'var(--ink)' : 'var(--ink-2)',
                    fontSize: 13.5,
                    cursor: 'pointer',
                    transition: 'background 0.1s',
                  }}
                  onMouseEnter={e => { if (!isActive) (e.currentTarget as HTMLDivElement).style.background = 'var(--surface-2)' }}
                  onMouseLeave={e => { if (!isActive) (e.currentTarget as HTMLDivElement).style.background = 'transparent' }}
                >
                  <span style={{
                    flex: 1,
                    minWidth: 0,
                    fontSize: 13.5,
                    fontWeight: isActive ? 600 : 500,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}>
                    {conv.title ?? 'New conversation'}
                  </span>
                  {sensitive && (
                    <Ic.lock
                      size={12}
                      strokeWidth={2.2}
                      style={{ color: 'var(--t3)', flexShrink: 0 }}
                    />
                  )}
                </div>
              </Link>
            )
          })}
        </div>
      ))}
    </NavSidebar>
  )
}
