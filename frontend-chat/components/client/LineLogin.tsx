'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'

// Client Workspaces — the /try landing page since migration 0063.
//
// Replaces RedeemInvite (the /try/<token> single-use invite flow). The
// difference that matters is not the SDK: it is that a client who closes
// this webview and comes back lands in the same seat instead of being
// locked out by a spent token. See app/routers/client_public.py::line_login.
//
// LIFF, not the OAuth redirect flow: the entry point is a LINE OA rich menu
// or message, so the page already opens inside LINE's in-app browser, where
// liff.getIDToken() hands us a verified token with no redirect, no state
// and no nonce to carry. Opened OUTSIDE LINE, liff.init() still succeeds but
// isLoggedIn() is false — we call liff.login(), which bounces through LINE
// and returns here logged in.
//
// The SDK is loaded from LINE's CDN rather than bundled: LINE ships breaking
// fixes to the edge build, and pinning a copy in node_modules means shipping
// a stale LIFF runtime to a webview we do not control.
const LIFF_SDK_URL = 'https://static.line-scdn.net/liff/edge/2/sdk.js'

type Liff = {
  init: (config: { liffId: string }) => Promise<void>
  isLoggedIn: () => boolean
  login: (config?: { redirectUri?: string }) => void
  getIDToken: () => string | null
}

declare global {
  interface Window {
    liff?: Liff
  }
}

function loadLiffSdk(): Promise<Liff> {
  return new Promise((resolve, reject) => {
    if (window.liff) {
      resolve(window.liff)
      return
    }
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${LIFF_SDK_URL}"]`)
    if (existing) {
      existing.addEventListener('load', () =>
        window.liff ? resolve(window.liff) : reject(new Error('LIFF SDK loaded without window.liff'))
      )
      existing.addEventListener('error', () => reject(new Error('LIFF SDK failed to load')))
      return
    }
    const script = document.createElement('script')
    script.src = LIFF_SDK_URL
    script.async = true
    script.onload = () =>
      window.liff ? resolve(window.liff) : reject(new Error('LIFF SDK loaded without window.liff'))
    script.onerror = () => reject(new Error('LIFF SDK failed to load'))
    document.head.appendChild(script)
  })
}

type Status = 'booting' | 'consent' | 'signing-in' | 'error'

export default function LineLogin({ liffId }: { liffId: string }) {
  const router = useRouter()
  const [status, setStatus] = useState<Status>('booting')
  const [consent, setConsent] = useState(false)
  const [message, setMessage] = useState('')
  const liffRef = useRef<Liff | null>(null)

  // Init only — deliberately does NOT log in. Consent has to be collected
  // before an account exists, and liff.login() on a fresh browser navigates
  // away immediately, which would put the privacy notice after the fact.
  useEffect(() => {
    let cancelled = false
    if (!liffId) {
      setStatus('error')
      setMessage('LINE sign-in is not configured for this site.')
      return
    }
    loadLiffSdk()
      .then(async (liff) => {
        await liff.init({ liffId })
        if (cancelled) return
        liffRef.current = liff
        setStatus('consent')
      })
      .catch(() => {
        if (cancelled) return
        setStatus('error')
        setMessage('Could not start LINE sign-in. Please reopen this page from LINE.')
      })
    return () => {
      cancelled = true
    }
  }, [liffId])

  const signIn = useCallback(async () => {
    const liff = liffRef.current
    if (!liff || !consent) return
    setStatus('signing-in')

    try {
      if (!liff.isLoggedIn()) {
        // Opened outside the LINE app. This navigates away and returns to
        // this same URL logged in; the consent tick is lost across that
        // bounce, so the client re-ticks it once on return. Deliberate —
        // persisting consent through a redirect means storing it before it
        // was given.
        liff.login({ redirectUri: window.location.href })
        return
      }

      const idToken = liff.getIDToken()
      if (!idToken) {
        setStatus('error')
        setMessage('LINE did not return a sign-in token. Please try again.')
        return
      }

      const res = await fetch('/api/public/line/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ id_token: idToken, consent: true }),
      })

      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setStatus('error')
        setMessage(
          res.status === 503
            ? 'LINE sign-in is not available right now.'
            : res.status === 403
              ? 'We need your consent before we can continue.'
              : res.status === 401
                ? 'Your LINE sign-in could not be verified. Please try again.'
                : res.status === 429
                  ? 'Too many attempts — please wait a moment and try again.'
                  : ((data.detail as string) ?? 'Something went wrong. Please try again.')
        )
        return
      }

      router.replace('/w')
    } catch {
      setStatus('error')
      setMessage('Network error — please try again in a moment.')
    }
  }, [consent, router])

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

        {(status === 'booting' || status === 'signing-in') && (
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
              {status === 'booting' ? 'Connecting to LINE…' : 'Setting up your workspace…'}
            </h1>
            <p style={{ fontSize: 13, color: 'var(--ink-3)', margin: 0, lineHeight: 1.6 }}>
              One moment — น้องภูมิ is getting ready.
            </p>
          </>
        )}

        {status === 'consent' && (
          <>
            <h1 style={{ fontSize: 16, fontWeight: 600, color: 'var(--ink)', margin: '0 0 8px' }}>
              เริ่มต้นด้วยบัญชี LINE
            </h1>
            <p
              style={{
                fontSize: 13,
                color: 'var(--ink-3)',
                margin: '0 0 20px',
                lineHeight: 1.6,
              }}
            >
              Sign in with LINE to build your brand plan. One plan per LINE account.
            </p>

            <label
              style={{
                display: 'flex',
                gap: 10,
                alignItems: 'flex-start',
                textAlign: 'left',
                fontSize: 12.5,
                color: 'var(--ink-2)',
                lineHeight: 1.6,
                marginBottom: 20,
                cursor: 'pointer',
              }}
            >
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
                style={{ marginTop: 3, flexShrink: 0 }}
              />
              <span>
                ยินยอมให้ Brandbiz เก็บและใช้ชื่อโปรไฟล์ LINE และข้อมูลธุรกิจที่กรอก
                เพื่อจัดทำแผนแบรนด์ให้ท่าน ตาม พ.ร.บ. คุ้มครองข้อมูลส่วนบุคคล (PDPA)
              </span>
            </label>

            <button
              type="button"
              onClick={signIn}
              disabled={!consent}
              style={{
                width: '100%',
                padding: '12px 16px',
                borderRadius: 'var(--r-lg)',
                border: 'none',
                background: consent ? '#06C755' : 'var(--line-2)',
                color: consent ? '#fff' : 'var(--ink-3)',
                fontSize: 14,
                fontWeight: 600,
                cursor: consent ? 'pointer' : 'not-allowed',
              }}
            >
              Continue with LINE
            </button>
          </>
        )}

        {status === 'error' && (
          <>
            <h1 style={{ fontSize: 16, fontWeight: 600, color: 'var(--ink)', margin: '0 0 8px' }}>
              Couldn&apos;t sign you in
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
