'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { Ic } from '@/components/ui/Icon'

interface HermesStatus {
  configured: boolean
  reachable: boolean
  helper_online: boolean
}

interface HostJob {
  id: string
  kind: string
  status: string   // queued | running | succeeded | failed
  log_text: string | null
  created_at: string
  finished_at: string | null
}

const STATUS_POLL_MS = 10_000
const JOB_POLL_MS = 2_000
const ACTIVE_JOB = new Set(['queued', 'running'])
// Survives a page reload (not just a re-render) so "waiting for the helper"
// doesn't silently revert to the download button if the admin switches back
// to this tab after running the installer.
const HELPER_DOWNLOADED_KEY = 'hermes-helper-downloaded'

/**
 * Online/offline banner for the Hermes Agent (which runs natively on the
 * Docker host, so the backend can't start it itself).
 *
 * While Hermes is offline an ADMIN gets, in order of convenience:
 *   - helper installed  → a one-click "Set up Hermes now" button; the host
 *     helper picks the job up, installs/starts Hermes, and its progress
 *     lines stream into the banner until it flips green.
 *   - no helper yet     → a one-time "Download helper installer" (plus the
 *     manual setup script as a fallback link).
 */
export default function HermesStatusBanner() {
  const [status, setStatus] = useState<HermesStatus | null>(null)
  const [isAdmin, setIsAdmin] = useState(false)
  const [job, setJob] = useState<HostJob | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [helperDownloaded, setHelperDownloaded] = useState(false)
  // Only show the green "back online" state if the user actually saw it
  // offline this session — a healthy Hermes renders no banner at all.
  const wasOffline = useRef(false)

  useEffect(() => {
    fetch('/api/me')
      .then((r) => (r.ok ? r.json() : null))
      .then((d: { role?: string } | null) => setIsAdmin(d?.role === 'ADMIN'))
      .catch(() => {})
  }, [])

  // Read after mount (not as lazy useState init) so server-rendered and
  // first-client-render markup match — sessionStorage doesn't exist during SSR.
  useEffect(() => {
    if (sessionStorage.getItem(HELPER_DOWNLOADED_KEY) === '1') setHelperDownloaded(true)
  }, [])

  // Reachability + helper liveness poll (10s while offline, stops when green).
  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setInterval> | null = null

    async function check() {
      try {
        const res = await fetch('/api/hermes/status', { cache: 'no-store' })
        if (!res.ok) return
        const s = (await res.json()) as HermesStatus
        if (cancelled) return
        if (!s.reachable) wasOffline.current = true
        setStatus(s)
        if (s.reachable && timer) {
          clearInterval(timer)
          timer = null
        }
      } catch { /* network blip — retry next tick */ }
    }

    check()
    timer = setInterval(check, STATUS_POLL_MS)
    return () => {
      cancelled = true
      if (timer) clearInterval(timer)
    }
  }, [])

  const refreshJob = useCallback(async () => {
    try {
      const res = await fetch('/api/hermes/host-jobs/latest', { cache: 'no-store' })
      if (!res.ok) return
      const j = (await res.json()) as HostJob | null
      setJob(j)
    } catch { /* retry next tick */ }
  }, [])

  // Pick up an in-flight job on mount (e.g. after a page reload), then poll
  // fast while one is active.
  useEffect(() => { refreshJob() }, [refreshJob])
  useEffect(() => {
    if (!job || !ACTIVE_JOB.has(job.status)) return
    const timer = setInterval(refreshJob, JOB_POLL_MS)
    return () => clearInterval(timer)
  }, [job, refreshJob])

  async function handleOneClickSetup() {
    setError(null)
    setBusy(true)
    try {
      const res = await fetch('/api/hermes/host-jobs', { method: 'POST' })
      const data = await res.json().catch(() => null)
      if (!res.ok) {
        const msg = data?.detail ?? 'Could not start the setup job.'
        setError(typeof msg === 'string' ? msg : JSON.stringify(msg))
        return
      }
      setJob(data as HostJob)
    } catch {
      setError('Network error — please try again.')
    } finally {
      setBusy(false)
    }
  }

  async function handleDownload(path: string, filename: string, onSuccess?: () => void) {
    setError(null)
    setBusy(true)
    try {
      const res = await fetch(path)
      if (!res.ok) {
        const data = await res.json().catch(() => null)
        const msg = data?.detail ?? 'Could not generate the script.'
        setError(typeof msg === 'string' ? msg : JSON.stringify(msg))
        return
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
      onSuccess?.()
    } catch {
      setError('Network error — please try again.')
    } finally {
      setBusy(false)
    }
  }

  function handleDownloadHelper() {
    handleDownload('/api/hermes/helper-script', 'install-helper.cmd', () => {
      sessionStorage.setItem(HELPER_DOWNLOADED_KEY, '1')
      setHelperDownloaded(true)
    })
  }

  if (!status) return null
  if (status.reachable && !wasOffline.current) return null

  const banner = (tone: string, children: React.ReactNode) => (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
      border: `1px solid color-mix(in srgb, ${tone} 45%, transparent)`,
      background: `color-mix(in srgb, ${tone} 10%, transparent)`,
      borderRadius: 'var(--r-md)',
      padding: '12px 14px',
      marginBottom: 16,
      fontSize: 13,
      color: 'var(--ink)',
    }}>
      {children}
    </div>
  )

  const buttonStyle = (disabled: boolean): React.CSSProperties => ({
    display: 'flex', alignItems: 'center', gap: 7,
    padding: '7px 14px',
    borderRadius: 'var(--r-md)',
    border: 'none',
    background: disabled ? 'var(--surface-2)' : 'var(--accent)',
    color: disabled ? 'var(--ink-4)' : '#fff',
    fontWeight: 600,
    fontSize: 12.5,
    cursor: disabled ? 'not-allowed' : 'pointer',
  })

  if (status.reachable) {
    return banner('var(--success)', (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Ic.check size={14} style={{ color: 'var(--success)', flexShrink: 0 }} />
        <span>Hermes Agent is online — tasks will run normally.</span>
      </div>
    ))
  }

  if (!status.configured) {
    return banner('var(--warning)', (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Ic.alert size={14} style={{ color: 'var(--warning)', flexShrink: 0 }} />
        <span>
          Hermes is not configured on this gateway (HERMES_API_KEY is blank), so tasks can’t run.
        </span>
      </div>
    ))
  }

  const jobActive = !!job && ACTIVE_JOB.has(job.status)
  const jobFailed = !!job && job.status === 'failed'

  return banner('var(--warning)', (
    <>
      <style>{`@keyframes hermes-banner-pulse { 0%, 100% { opacity: 1 } 50% { opacity: 0.35 } }`}</style>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Ic.alert size={14} style={{ color: 'var(--warning)', flexShrink: 0 }} />
        <span style={{ fontWeight: 600 }}>Hermes Agent is offline — tasks can’t run right now.</span>
      </div>

      {isAdmin && !jobActive && (
        status.helper_online ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <button onClick={handleOneClickSetup} disabled={busy} style={buttonStyle(busy)}>
              <Ic.play size={13} />
              {busy ? 'Starting…' : jobFailed ? 'Retry setup' : 'Set up Hermes now'}
            </button>
            <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>
              One click — the helper on the host installs and starts Hermes automatically.
            </span>
          </div>
        ) : helperDownloaded ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <span style={{
              width: 7, height: 7, borderRadius: '50%', background: 'var(--warning)', flexShrink: 0,
              animation: 'hermes-banner-pulse 1.4s ease-in-out infinite',
            }} />
            <span>
              Downloaded <strong>install-helper.cmd</strong> — open your Downloads folder and
              double-click it to run the installer. Waiting for the helper to connect…
            </span>
          </div>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <button onClick={handleDownloadHelper} disabled={busy} style={buttonStyle(busy)}>
              <Ic.download size={13} />
              {busy ? 'Generating…' : 'Download helper installer'}
            </button>
            <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>
              One-time: after downloading, double-click <strong>install-helper.cmd</strong> in your
              Downloads folder — after that, Hermes setup is a single click here (and auto-restarts
              after reboots).{' '}
              <a
                onClick={(e) => { e.preventDefault(); handleDownload('/api/hermes/setup-script', 'install-hermes.ps1') }}
                href="/api/hermes/setup-script"
                style={{ color: 'var(--accent)', cursor: 'pointer' }}
              >
                Prefer the manual setup script?
              </a>
            </span>
          </div>
        )
      )}

      {isAdmin && (jobActive || jobFailed) && job?.log_text && (
        <pre style={{
          margin: 0,
          padding: '8px 10px',
          borderRadius: 'var(--r-md)',
          background: 'color-mix(in srgb, var(--ink) 6%, transparent)',
          fontFamily: 'var(--font-mono)',
          fontSize: 11.5,
          lineHeight: 1.6,
          color: 'var(--ink-2)',
          maxHeight: 140,
          overflowY: 'auto',
          whiteSpace: 'pre-wrap',
        }}>
          {job.log_text}
        </pre>
      )}
      {isAdmin && jobActive && (
        <span style={{ fontSize: 12, color: 'var(--ink-3)', fontStyle: 'italic' }}>
          Setting up Hermes on the host… this banner turns green when it’s done.
        </span>
      )}

      {!isAdmin && (
        <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>
          Ask an administrator to start it — you can still submit tasks, but they’ll fail until it’s back.
        </span>
      )}
      {error && (
        <span style={{ fontSize: 12, color: 'var(--danger)' }}>{error}</span>
      )}
    </>
  ))
}
