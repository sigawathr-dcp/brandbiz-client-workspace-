'use client'

import ProviderMark from './ui/ProviderMark'
import UiTierBadge from './ui/TierBadge'
import { modelInfo } from '@/lib/domain'
import { Ic } from './ui/Icon'
import type { TierKey } from '@/lib/domain'

interface TierBadgeProps {
  model?: string
  downgraded?: boolean
  reason?: string
  tier?: TierKey
  tokensIn?: number
  tokensOut?: number
}

const REASON_COPY: Record<string, string> = {
  tier_blocks_external: 'Using the local model — your message contains sensitive data that may not leave our servers.',
  tier_blocked:         'Using the local model — your message contains sensitive data.',
  role_not_allowed:     "You're not entitled to the requested model (needs a higher role). Falling back to the local model.",
}

export default function TierBadge({ model, downgraded, reason, tier, tokensIn, tokensOut }: TierBadgeProps) {
  if (!model) return null

  const info = modelInfo(model)
  const reasonCopy = reason ? (REASON_COPY[reason] ?? 'Routed to local model.') : null
  const showTokens = (tokensIn !== undefined && tokensIn > 0) || (tokensOut !== undefined && tokensOut > 0)
  const isFree = info.isLocal || info.free

  return (
    <div style={{ marginTop: 9 }}>
      {/* Meta row: provider mark + model name + "kept local" pill + tier badge */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 9,
        marginBottom: 9,
        flexWrap: 'wrap',
      }}>
        <span style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 7,
          fontSize: 12.5,
          fontWeight: 600,
          color: 'var(--ink-2)',
        }}>
          <ProviderMark provider={info.provider} isLocal={info.isLocal} size={20} />
          {info.label}
        </span>
        {downgraded && (
          <span style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 5,
            fontSize: 11.5,
            fontWeight: 600,
            color: 'var(--t3)',
            background: 'var(--t3-bg)',
            padding: '2px 9px',
            borderRadius: 99,
          }}>
            <Ic.lock size={12} strokeWidth={2.2} /> kept local
          </span>
        )}
        {tier && <UiTierBadge tier={tier} mode="sm" />}
      </div>

      {/* Downgrade explainer */}
      {downgraded && reasonCopy && (
        <div style={{
          display: 'flex',
          gap: 9,
          alignItems: 'flex-start',
          padding: '10px 12px',
          marginBottom: 11,
          background: 'var(--t3-bg)',
          borderRadius: 'var(--r-md)',
          fontSize: 12.5,
          color: 'var(--ink-2)',
          lineHeight: 1.45,
        }}>
          <Ic.info size={15} style={{ color: 'var(--t3)', flexShrink: 0, marginTop: 1 }} />
          <span>{reasonCopy}</span>
        </div>
      )}

      {/* Token / audit footer */}
      {showTokens && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 14,
          marginTop: 12,
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          color: 'var(--ink-4)',
        }}>
          <span>{tokensIn ?? 0}↑ {tokensOut ?? 0}↓ tok</span>
          <span style={{ color: isFree ? 'var(--t1)' : 'var(--ink-4)' }}>
            {isFree ? '$0.00 · free' : 'logged'}
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <Ic.check size={12} strokeWidth={2.4} style={{ color: 'var(--t1)' }} /> logged
          </span>
        </div>
      )}
      {!showTokens && (
        <div style={{ fontSize: 11, color: 'var(--ink-4)', marginTop: 4, fontFamily: 'var(--font-mono)' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <Ic.check size={11} strokeWidth={2.4} style={{ color: 'var(--t1)' }} /> Logged · encrypted · 30-day retention
          </span>
        </div>
      )}
    </div>
  )
}
