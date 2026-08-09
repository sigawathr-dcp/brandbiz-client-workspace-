'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

// Client Workspaces (Phase 5, D21/D22) — the /try/<token> landing page.
// Redeeming an invite IS the login (see app/routers/client_public.py); this
// component just fires that call on mount and forwards into the workspace.
// No form, no typing — the whole point is a one-tap entry at a booth.
export default function RedeemInvite({ token }: { token: string }) {
  const router = useRouter()
  const [status, setStatus] = useState<'redeeming' | 'error'>('redeeming')
  const [message, setMessage] = useState('')

  useEffect(() => {
    let cancelled = false
    async function redeem() {
      try {
        const res = await fetch('/api/public/redeem', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ token }),
        })
        if (!res.ok) {
          const data = await res.json().catch(() => ({}))
          if (cancelled) return
          setStatus('error')
          setMessage(
            res.status === 410
              ? (data.detail as string) || 'This link has already been used or has expired.'
              : res.status === 503
                ? 'This experience is not available right now.'
                : (data.detail as string) || 'This link is not valid.'
          )
          return
        }
        if (!cancelled) router.replace('/w')
      } catch {
        if (!cancelled) {
          setStatus('error')
          setMessage('Network error — please try again in a moment.')
        }
      }
    }
    redeem()
    return () => {
      cancelled = true
    }
  }, [token, router])

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        background: 'var(--bg)',
        padding: '2rem',
      }}
    >
      <div
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--line)',
          borderRadius: 'var(--r-xl)',
          padding: '44px 38px',
          maxWidth: 420,
          width: '100%',
          boxShadow: 'var(--shadow-3)',
          textAlign: 'center',
        }}
      >
        <div
          style={{
            width: 44,
            height: 44,
            margin: '0 auto 20px',
            borderRadius: 'var(--r-lg)',
            background: 'var(--accent)',
            color: '#fff',
            display: 'grid',
            placeItems: 'center',
            fontSize: 18,
            fontWeight: 700,
          }}
        >
          B
        </div>

        {status === 'redeeming' && (
          <>
            <div
              style={{
                width: 22,
                height: 22,
                margin: '0 auto 16px',
                borderRadius: '50%',
                border: '2.5px solid var(--line-2)',
                borderTopColor: 'var(--accent)',
                animation: 'spin 0.8s linear infinite',
              }}
            />
            <h1 style={{ fontSize: 16, fontWeight: 600, color: 'var(--ink)', margin: '0 0 6px' }}>
              Setting up your workspace…
            </h1>
            <p style={{ fontSize: 13, color: 'var(--ink-3)', margin: 0, lineHeight: 1.6 }}>
              One moment — น้องภูมิ is getting ready.
            </p>
          </>
        )}

        {status === 'error' && (
          <>
            <h1 style={{ fontSize: 16, fontWeight: 600, color: 'var(--ink)', margin: '0 0 8px' }}>
              Couldn&apos;t open this link
            </h1>
            <p style={{ fontSize: 13, color: 'var(--ink-3)', margin: 0, lineHeight: 1.6 }}>
              {message}
            </p>
          </>
        )}
      </div>
    </div>
  )
}
