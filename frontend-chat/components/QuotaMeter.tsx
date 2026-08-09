'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Ic } from './ui/Icon'

interface QuotaStatus {
  tokens_used: number
  tokens_limit: number
  cost_used_usd: string
  period_start: string
}

interface QuotaMeterProps {
  /** Increment to force a refresh (pass from ChatPane after each turn). */
  refreshKey?: number
  /** Auto-poll interval in ms. 0 = no polling. */
  pollInterval?: number
  /** Admins click through to Admin Console quota tab; non-admins expand inline. */
  isAdmin?: boolean
}

// int64-max sentinel (9223372036854775807) is rounded in JS float to ~9.223e18.
// Anything above 1e15 is effectively "unlimited" — no real budget is that large.
const UNLIMITED_THRESHOLD = 1e15

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function fmt(n: number) {
  return n >= 1_000_000
    ? (n / 1_000_000).toFixed(2) + 'M'
    : Math.round(n / 1000) + 'k'
}

/** Derive the next reset date from period_start ("YYYY-MM-DD") without Date() UTC shift. */
function nextReset(periodStart: string): string {
  const [, m] = periodStart.split('-').map(Number)
  const nextMonth = m === 12 ? 1 : m + 1
  return `1 ${MONTHS[nextMonth - 1]}`
}

function formatCost(usd: string): string {
  const n = parseFloat(usd)
  return isNaN(n) ? '$0.00' : `$${n.toFixed(2)}`
}

export default function QuotaMeter({ refreshKey = 0, pollInterval = 0, isAdmin = false }: QuotaMeterProps) {
  const router = useRouter()
  const [quota, setQuota] = useState<QuotaStatus | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [hovered, setHovered] = useState(false)

  function load() {
    fetch('/api/quota')
      .then(r => r.ok ? r.json() : null)
      .then((d: QuotaStatus | null) => setQuota(d))
      .catch(() => {})
  }

  useEffect(() => { load() }, [refreshKey])

  useEffect(() => {
    if (!pollInterval) return
    const id = setInterval(load, pollInterval)
    return () => clearInterval(id)
  }, [pollInterval])

  if (!quota || quota.tokens_limit === 0) return null

  const isUnlimited = quota.tokens_limit > UNLIMITED_THRESHOLD
  const pct = isUnlimited ? 0 : Math.min(100, (quota.tokens_used / quota.tokens_limit) * 100)
  const warn = pct > 80
  const barColor = pct >= 90 ? 'var(--t4)' : pct >= 70 ? 'var(--t3)' : 'var(--accent)'
  const resetLabel = nextReset(quota.period_start)

  function handleClick() {
    if (isAdmin) {
      router.push('/admin-console?tab=quotas')
    } else {
      setExpanded(e => !e)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      handleClick()
    }
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: '12px 14px',
        border: `1px solid ${hovered ? 'var(--accent)' : 'var(--line)'}`,
        borderRadius: 'var(--r-md)',
        background: hovered ? 'var(--surface-2)' : 'var(--surface)',
        cursor: 'pointer',
        transition: 'border-color 0.15s, background 0.15s',
        outline: 'none',
        userSelect: 'none',
      }}
    >
      {/* Header row: label + tokens summary */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        marginBottom: isUnlimited ? 0 : 8,
      }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink-2)' }}>External token budget</span>
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11.5,
          color: warn ? 'var(--t3)' : 'var(--ink-3)',
          display: 'flex',
          alignItems: 'center',
          gap: 4,
        }}>
          {isUnlimited
            ? <><span>{fmt(quota.tokens_used)}</span><span style={{ color: 'var(--ink-4)' }}> · Unlimited</span></>
            : <>{fmt(quota.tokens_used)}<span style={{ color: 'var(--ink-4)' }}> / {fmt(quota.tokens_limit)}</span></>
          }
        </span>
      </div>

      {/* Progress bar — limited roles only */}
      {!isUnlimited && (
        <div style={{
          height: 6,
          borderRadius: 99,
          background: 'var(--surface-sunk)',
          overflow: 'hidden',
        }}>
          <div style={{
            width: pct + '%',
            height: '100%',
            borderRadius: 99,
            background: barColor,
            transition: 'width .5s cubic-bezier(.2,.8,.2,1)',
          }} />
        </div>
      )}

      {/* Footer row: reset date + local-free + affordance */}
      <div style={{
        fontSize: 11,
        color: 'var(--ink-4)',
        marginTop: isUnlimited ? 6 : 7,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <span>Resets {resetLabel} · local model is free</span>
        {isAdmin
          ? <span style={{ fontSize: 10.5, color: 'var(--accent)', fontWeight: 500 }}>Manage →</span>
          : <Ic.ChevronDown
              size={12}
              strokeWidth={2}
              style={{
                color: 'var(--ink-4)',
                transform: expanded ? 'rotate(180deg)' : 'none',
                transition: 'transform 0.2s',
              }}
            />
        }
      </div>

      {/* Expanded detail — non-admin only */}
      {!isAdmin && expanded && (
        <div style={{
          marginTop: 10,
          paddingTop: 10,
          borderTop: '1px solid var(--line)',
          display: 'flex',
          flexDirection: 'column',
          gap: 5,
          fontSize: 11.5,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--ink-3)' }}>Tokens used</span>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--ink-2)' }}>
              {quota.tokens_used.toLocaleString()}
            </span>
          </div>
          {!isUnlimited && (
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--ink-3)' }}>Token limit</span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--ink-2)' }}>
                {quota.tokens_limit.toLocaleString()}
              </span>
            </div>
          )}
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--ink-3)' }}>Cost this period</span>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--ink-2)' }}>
              {formatCost(quota.cost_used_usd)}
            </span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--ink-3)' }}>Resets</span>
            <span style={{ color: 'var(--ink-2)' }}>{resetLabel}</span>
          </div>
        </div>
      )}
    </div>
  )
}
