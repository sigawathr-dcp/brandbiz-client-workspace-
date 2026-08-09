'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Ic } from '@/components/ui/Icon'
import type { AgentItem } from './AgentPage'
import { getCategoryStyle } from './AgentPage'

interface Props {
  agent: AgentItem
  onClose: () => void
}

const CREATIVITY_LABELS: Record<number, string> = {}
function creativityLabel(level: number): string {
  if (level < 34) return 'Focused'
  if (level < 67) return 'Balanced'
  return 'Creative'
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function AvatarCircle({ agent }: { agent: AgentItem }) {
  const COLORS = ['#6C63FF', '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#DDA0DD', '#98D8C8']
  const color = agent.avatar_color
    ?? (agent.category ? getCategoryStyle(agent.category).color : null)
    ?? COLORS[agent.id.charCodeAt(0) % COLORS.length]
  return (
    <div style={{
      width: 72,
      height: 72,
      borderRadius: '50%',
      background: color,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      color: '#fff',
      fontWeight: 700,
      fontSize: 28,
      margin: '0 auto 12px',
    }}>
      {agent.name.trim().slice(0, 1).toUpperCase()}
    </div>
  )
}

export default function AboutModal({ agent, onClose }: Props) {
  const router = useRouter()

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  const caps = agent.capabilities ?? {}
  const enabledCaps: string[] = []
  if (caps.web_search) enabledCaps.push('Web Search')
  if (caps.image_gen) enabledCaps.push('Image Generator')
  if (caps.video_gen) enabledCaps.push('Video Generator')
  if (caps.think_longer) enabledCaps.push('Think Longer')

  function handleChatWithAgent() {
    onClose()
    router.push(`/chat?agent=${agent.id}`)
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0,0,0,0.45)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: 16,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--surface)',
          borderRadius: 'var(--r-xl)',
          width: '100%',
          maxWidth: 440,
          maxHeight: '90vh',
          overflowY: 'auto',
          padding: 28,
          position: 'relative',
          boxShadow: 'var(--shadow-3)',
        }}
      >
        {/* Close */}
        <button
          onClick={onClose}
          style={{
            position: 'absolute', top: 16, right: 16,
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--ink-3)', padding: 4,
          }}
        >
          <Ic.x size={18} strokeWidth={2} />
        </button>

        <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 16 }}>About</div>

        <AvatarCircle agent={agent} />

        {/* Name */}
        <div style={{ textAlign: 'center', fontWeight: 700, fontSize: 16, color: 'var(--ink)', marginBottom: 8 }}>
          {agent.name}
        </div>

        {/* Visibility badge + category pill */}
        <div style={{ textAlign: 'center', marginBottom: 10, display: 'flex', gap: 6, justifyContent: 'center', flexWrap: 'wrap' }}>
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 5,
            border: '1px solid var(--line-2)',
            borderRadius: 99,
            padding: '2px 12px',
            fontSize: 12,
            fontWeight: 600,
            color: 'var(--ink-2)',
          }}>
            <Ic.globe size={11} strokeWidth={2} />
            {agent.visibility === 'public' ? 'Public' : 'Personal'}
          </span>
          {agent.category && (() => {
            const cs = getCategoryStyle(agent.category)
            return (
              <span style={{
                display: 'inline-flex', alignItems: 'center',
                borderRadius: 99,
                padding: '2px 12px',
                fontSize: 12,
                fontWeight: 600,
                color: cs.color,
                background: cs.bg,
              }}>
                {agent.category}
              </span>
            )
          })()}
        </div>

        {/* Description */}
        {agent.description && (
          <div style={{ textAlign: 'center', fontSize: 13, color: 'var(--ink-3)', marginBottom: 16, lineHeight: 1.5 }}>
            {agent.description}
          </div>
        )}

        <hr style={{ border: 'none', borderTop: '1px solid var(--line)', margin: '16px 0' }} />

        {/* Meta row */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 16, textAlign: 'center' }}>
          <div>
            <div style={{ fontSize: 11, color: 'var(--ink-4)', marginBottom: 3 }}>AI Model</div>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink-2)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
              <Ic.globe size={11} strokeWidth={2} />
              {agent.model}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: 'var(--ink-4)', marginBottom: 3 }}>Creativity Level</div>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink-2)' }}>
              {creativityLabel(agent.creativity_level)}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: 'var(--ink-4)', marginBottom: 3 }}>Updated</div>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink-2)' }}>
              {fmtDate(agent.updated_at)}
            </div>
          </div>
        </div>

        {/* Instructions */}
        {agent.instructions && (
          <>
            <div style={{ fontSize: 12, color: 'var(--ink-4)', fontWeight: 600, marginBottom: 6 }}>Instructions</div>
            <div style={{
              fontSize: 12.5,
              color: 'var(--ink-2)',
              lineHeight: 1.6,
              marginBottom: 16,
              background: 'var(--surface-2)',
              padding: 12,
              borderRadius: 'var(--r-md)',
            }}>
              {agent.instructions}
            </div>
          </>
        )}

        {/* Capabilities */}
        {enabledCaps.length > 0 && (
          <div style={{
            background: 'var(--accent-weak)',
            borderRadius: 'var(--r-md)',
            padding: '12px 14px',
            marginBottom: 16,
          }}>
            <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 8, color: 'var(--ink)' }}>Capabilities</div>
            {enabledCaps.map(cap => (
              <div key={cap} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--ink-2)', marginBottom: 4 }}>
                <Ic.check size={14} strokeWidth={2.5} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                {cap}
              </div>
            ))}
          </div>
        )}

        {/* Creator */}
        <div style={{ textAlign: 'center', fontSize: 12, color: 'var(--ink-4)', marginBottom: 20 }}>
          Created by {agent.creator_name ?? 'Core Admin'}
        </div>

        {/* CTA */}
        <button
          onClick={handleChatWithAgent}
          style={{
            width: '100%',
            padding: '13px',
            borderRadius: 'var(--r-lg)',
            border: 'none',
            background: 'linear-gradient(135deg, #ff6b9d, #c44dff)',
            color: '#fff',
            fontWeight: 700,
            fontSize: 14,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
          }}
        >
          <Ic.cpu size={16} strokeWidth={2.2} />
          Chat with Agent
        </button>
      </div>
    </div>
  )
}
