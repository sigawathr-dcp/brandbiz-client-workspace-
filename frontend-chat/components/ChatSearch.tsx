'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { Ic } from './ui/Icon'
import { fetchConversations, type Conversation } from '@/lib/api'
import { formatRelativeDate } from '@/lib/dates'

export default function ChatSearch() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Conversation[]>([])
  const [focused, setFocused] = useState(false)
  const hasLoadedOnce = useRef(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    const trimmed = query.trim()
    const timer = setTimeout(async () => {
      try {
        const convs = await fetchConversations({
          q: trimmed || undefined,
          limit: 100,
          signal: controller.signal,
        })
        hasLoadedOnce.current = true
        setResults(convs)
      } catch (err) {
        if ((err as Error).name !== 'AbortError') throw err
      }
    }, trimmed ? 300 : 0)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [query])

  const trimmed = query.trim()

  return (
    <div style={{ height: '100%', overflowY: 'auto', background: 'var(--surface)' }}>
      <div style={{ maxWidth: 640, margin: '0 auto', padding: '72px 24px 40px' }}>
        {/* Search box */}
        <div style={{ position: 'relative' }}>
          <Ic.search
            size={18}
            style={{
              position: 'absolute',
              left: 16,
              top: '50%',
              transform: 'translateY(-50%)',
              color: 'var(--ink-3)',
              pointerEvents: 'none',
            }}
          />
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => { if (e.key === 'Escape') setQuery('') }}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            placeholder="Search chats…"
            style={{
              width: '100%',
              padding: '14px 44px 14px 46px',
              fontSize: 16,
              borderRadius: 'var(--r-lg)',
              border: `1px solid ${focused ? 'var(--accent)' : 'var(--line-2)'}`,
              background: 'var(--surface)',
              color: 'var(--ink)',
              boxShadow: 'var(--shadow-1)',
              outline: 'none',
              transition: 'border-color 0.15s',
            }}
          />
          {query !== '' && (
            <button
              onClick={() => { setQuery(''); inputRef.current?.focus() }}
              aria-label="Clear search"
              style={{
                position: 'absolute',
                right: 12,
                top: '50%',
                transform: 'translateY(-50%)',
                display: 'grid',
                placeItems: 'center',
                padding: 6,
                border: 'none',
                background: 'transparent',
                color: 'var(--ink-3)',
                cursor: 'pointer',
              }}
            >
              <Ic.x size={16} strokeWidth={2} />
            </button>
          )}
        </div>

        {/* Section heading */}
        {trimmed === '' && results.length > 0 && (
          <div style={{
            padding: '24px 10px 8px',
            fontSize: 11,
            fontWeight: 600,
            color: 'var(--ink-4)',
            textTransform: 'uppercase',
            letterSpacing: '.04em',
          }}>
            Recent
          </div>
        )}
        {trimmed !== '' && <div style={{ height: 20 }} />}

        {/* Results */}
        {results.map(conv => (
          <Link key={conv.id} href={`/chat/${conv.id}`} style={{ display: 'block', textDecoration: 'none' }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '10px 12px',
                borderRadius: 'var(--r-md)',
                cursor: 'pointer',
                transition: 'background 0.1s',
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.background = 'var(--surface-2)' }}
              onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.background = 'transparent' }}
            >
              <Ic.message size={15} style={{ color: 'var(--ink-3)', flexShrink: 0 }} />
              <span style={{
                flex: 1,
                minWidth: 0,
                fontSize: 14,
                fontWeight: 500,
                color: 'var(--ink)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}>
                {conv.title ?? 'New conversation'}
              </span>
              <span style={{ fontSize: 12.5, color: 'var(--ink-4)', flexShrink: 0 }}>
                {formatRelativeDate(conv.updated_at)}
              </span>
            </div>
          </Link>
        ))}

        {/* Empty states */}
        {hasLoadedOnce.current && results.length === 0 && (
          <p style={{ color: 'var(--ink-4)', fontSize: 13.5, textAlign: 'center', marginTop: 40 }}>
            {trimmed !== '' ? 'No chats found' : 'No conversations yet.'}
          </p>
        )}
      </div>
    </div>
  )
}
