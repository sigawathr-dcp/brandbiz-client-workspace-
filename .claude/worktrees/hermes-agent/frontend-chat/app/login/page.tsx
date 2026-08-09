'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Ic } from '@/components/ui/Icon'

export default function LoginPage() {
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const router = useRouter()
  async function handleLogin(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ identifier, password }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError(data.detail || 'Login failed')
        return
      }
      router.push('/chat')
    } catch {
      setError('Network error — is the backend running?')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '100vh',
      background: 'var(--bg)',
      padding: '2rem',
    }}>
      <div style={{
        background: 'var(--surface)',
        border: '1px solid var(--line)',
        borderRadius: 'var(--r-xl)',
        padding: '44px 38px',
        maxWidth: 420,
        width: '100%',
        boxShadow: 'var(--shadow-3)',
        textAlign: 'center',
        animation: 'popIn 0.2s ease',
      }}>
        {/* Shield logo */}
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 14,
          marginBottom: 28,
        }}>
          <div style={{
            width: 52,
            height: 52,
            borderRadius: 'var(--r-lg)',
            background: 'var(--accent)',
            color: '#fff',
            display: 'grid',
            placeItems: 'center',
            boxShadow: '0 4px 16px rgba(79,70,229,.28)',
          }}>
            <Ic.shield size={28} strokeWidth={2} />
          </div>
          <div>
            <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--ink)', letterSpacing: '-.01em', lineHeight: 1.2 }}>
              Decomplica AI
            </div>
            <div style={{ fontSize: 12, color: 'var(--ink-3)', letterSpacing: '0.04em', textTransform: 'uppercase', marginTop: 2 }}>
              Gateway
            </div>
          </div>
        </div>

        <h1 style={{ fontSize: 18, fontWeight: 600, color: 'var(--ink)', margin: '0 0 6px' }}>
          Sign in to the demo
        </h1>
        <p style={{ fontSize: 13, color: 'var(--ink-3)', margin: '0 0 28px', lineHeight: 1.6 }}>
          Enter your username or email and password.
        </p>

        <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <input
            type="text"
            value={identifier}
            onChange={e => setIdentifier(e.target.value)}
            placeholder="username or you@company.com"
            required
            autoComplete="username"
            style={{
              width: '100%',
              padding: '10px 14px',
              borderRadius: 'var(--r-md)',
              border: '1px solid var(--line-2)',
              background: 'var(--surface-sunk)',
              color: 'var(--ink)',
              fontSize: 14,
              boxSizing: 'border-box',
              outline: 'none',
            }}
          />
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            placeholder="Password"
            required
            autoComplete="current-password"
            style={{
              width: '100%',
              padding: '10px 14px',
              borderRadius: 'var(--r-md)',
              border: '1px solid var(--line-2)',
              background: 'var(--surface-sunk)',
              color: 'var(--ink)',
              fontSize: 14,
              boxSizing: 'border-box',
              outline: 'none',
            }}
          />
          <button
            type="submit"
            disabled={loading}
            style={{
              width: '100%',
              padding: '12px 20px',
              borderRadius: 'var(--r-md)',
              background: loading ? 'var(--accent-weak)' : 'var(--accent)',
              color: loading ? 'var(--accent)' : '#fff',
              border: 'none',
              fontSize: 14,
              fontWeight: 600,
              cursor: loading ? 'not-allowed' : 'pointer',
              transition: 'background 0.15s, color 0.15s',
              boxShadow: loading ? 'none' : '0 2px 8px rgba(79,70,229,.3)',
            }}
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
          {error && (
            <p style={{ margin: 0, fontSize: 12, color: '#e53e3e' }}>{error}</p>
          )}
        </form>

        <p style={{ marginTop: 22, fontSize: 11, color: 'var(--ink-4)', lineHeight: 1.5 }}>
          Internal demo only. All sessions are logged per company policy.
        </p>
      </div>
    </div>
  )
}
