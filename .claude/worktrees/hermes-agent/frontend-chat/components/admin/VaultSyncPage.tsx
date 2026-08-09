'use client'

import { useEffect, useRef, useState } from 'react'
import { Ic } from '@/components/ui/Icon'
import StageStepper from '@/components/ui/StageStepper'
import ConfirmDialog from './ConfirmDialog'
import type { VaultConfig, VaultSyncRun } from '@/lib/admin-api'

const RUN_STAGES = ['cloning', 'pulling', 'reconciling', 'done']
const RUN_STAGE_LABEL: Record<string, string> = {
  cloning: 'Cloning', pulling: 'Pulling', reconciling: 'Reconciling', done: 'Done',
}
const ACTIVE_STATUSES = new Set(['cloning', 'pulling', 'reconciling'])
const POLL_MS = 3000

// Explicit locale AND timeZone — this component is server-rendered for the
// initial HTML. The Docker host runs in UTC while a browser may be in any
// local timezone (e.g. Asia/Bangkok, UTC+7), so without a pinned timeZone
// the same instant renders as two different calendar dates/times server
// vs. client, tripping a hydration mismatch (React error #418). Matches
// fmtDate's explicit-locale approach in app/chat/knowledge/page.tsx, plus
// a fixed UTC zone so the two renders are byte-identical.
function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString('en-GB', {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    timeZone: 'UTC',
  }) + ' UTC'
}

interface Props {
  initialConfig: VaultConfig | null
  initialRun: VaultSyncRun | null
}

export default function VaultSyncPage({ initialConfig, initialRun }: Props) {
  const [config, setConfig] = useState<VaultConfig | null>(initialConfig)
  const [gitUrl, setGitUrl] = useState(initialConfig?.git_url ?? '')
  const [branch, setBranch] = useState(initialConfig?.branch ?? 'main')
  const [botEmail, setBotEmail] = useState(initialConfig?.bot_email ?? '')
  const [templatesDirname, setTemplatesDirname] = useState(initialConfig?.templates_dirname ?? 'templates')
  const [token, setToken] = useState('')
  const [clearToken, setClearToken] = useState(false)
  const [saving, setSaving] = useState(false)
  const [configError, setConfigError] = useState('')
  const [showConfirm, setShowConfirm] = useState(false)

  const [run, setRun] = useState<VaultSyncRun | null>(initialRun)
  const [dryRun, setDryRun] = useState(false)
  const [triggering, setTriggering] = useState(false)
  const [syncError, setSyncError] = useState('')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (initialRun && ACTIVE_STATUSES.has(initialRun.status)) startPolling(initialRun.id)
    return () => stopPolling()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function stopPolling() {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }

  function startPolling(runId: string) {
    stopPolling()
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/admin/vault/sync/${runId}`)
        if (!res.ok) return
        const data: VaultSyncRun = await res.json()
        setRun(data)
        if (!ACTIVE_STATUSES.has(data.status)) stopPolling()
      } catch {
        // keep polling — transient network errors shouldn't stop it
      }
    }, POLL_MS)
  }

  const hasChanges =
    gitUrl !== (config?.git_url ?? '') ||
    branch !== (config?.branch ?? 'main') ||
    botEmail !== (config?.bot_email ?? '') ||
    templatesDirname !== (config?.templates_dirname ?? 'templates') ||
    token.trim().length > 0 ||
    clearToken

  const changeSummary = [
    gitUrl !== (config?.git_url ?? '') ? `Git URL → ${gitUrl}` : null,
    branch !== (config?.branch ?? 'main') ? `Branch → ${branch}` : null,
    botEmail !== (config?.bot_email ?? '') ? `Bot email → ${botEmail}` : null,
    templatesDirname !== (config?.templates_dirname ?? 'templates') ? `Templates dir → ${templatesDirname}` : null,
    clearToken ? 'Access token → cleared' : token.trim() ? 'Access token → replaced' : null,
  ].filter(Boolean).join('\n')

  async function handleSaveConfig() {
    setSaving(true); setConfigError('')
    try {
      const body: Record<string, unknown> = { git_url: gitUrl.trim(), branch: branch.trim() || 'main' }
      if (botEmail.trim()) body.bot_email = botEmail.trim()
      if (templatesDirname.trim()) body.templates_dirname = templatesDirname.trim()
      if (clearToken) body.token = ''
      else if (token.trim()) body.token = token.trim()

      const res = await fetch('/api/admin/vault/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error((await res.text()) || `Save failed (${res.status})`)
      const updated: VaultConfig = await res.json()
      setConfig(updated)
      setGitUrl(updated.git_url ?? '')
      setBranch(updated.branch)
      setBotEmail(updated.bot_email)
      setTemplatesDirname(updated.templates_dirname)
      setToken('')
      setClearToken(false)
      setShowConfirm(false)
    } catch (e: unknown) {
      setConfigError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setSaving(false)
    }
  }

  async function handleSync() {
    setSyncError(''); setTriggering(true)
    try {
      const res = await fetch('/api/admin/vault/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dry_run: dryRun }),
      })
      if (res.status === 409) {
        // Another sync is already running (e.g. another admin, or cron) — pick it up instead of erroring out.
        const latest = await fetch('/api/admin/vault/sync/latest')
        if (latest.ok) {
          const data: VaultSyncRun = await latest.json()
          setRun(data)
          if (ACTIVE_STATUSES.has(data.status)) startPolling(data.id)
        }
        setSyncError('A sync is already in progress — showing its live status below.')
        return
      }
      if (!res.ok) throw new Error((await res.text()) || `Sync failed to start (${res.status})`)
      const data: VaultSyncRun = await res.json()
      setRun(data)
      startPolling(data.id)
    } catch (e: unknown) {
      setSyncError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setTriggering(false)
    }
  }

  const syncActive = run !== null && ACTIVE_STATUSES.has(run.status)
  // Based on the *saved* connection, not the live form fields — a sync
  // always runs against what's persisted, not whatever is mid-edit.
  const canConnect = Boolean(config?.git_url)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>

      {/* ── Connection ── */}
      <section style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-md)', padding: 20, background: 'var(--surface)' }}>
        <h2 style={{ fontSize: 15, fontWeight: 700, margin: '0 0 4px' }}>Connection</h2>
        <p style={{ fontSize: 12, color: 'var(--ink-4)', margin: '0 0 16px' }}>
          The access token is write-only — it is never sent back to the browser once saved.
        </p>

        {configError && (
          <div style={{ background: 'var(--danger-bg)', border: '1px solid var(--danger)', borderRadius: 6, padding: '8px 12px', marginBottom: 16, color: 'var(--danger)', fontSize: 13 }}>
            {configError}
          </div>
        )}

        <label style={{ display: 'block', marginBottom: 14 }}>
          <span style={{ color: 'var(--muted)', fontSize: 12, display: 'block', marginBottom: 4 }}>Git URL</span>
          <input
            type="text" value={gitUrl} onChange={e => setGitUrl(e.target.value)}
            placeholder="https://github.com/org/vault.git"
            style={{ width: '100%' }}
          />
        </label>

        <div style={{ display: 'flex', gap: 14, marginBottom: 14 }}>
          <label style={{ flex: 1 }}>
            <span style={{ color: 'var(--muted)', fontSize: 12, display: 'block', marginBottom: 4 }}>Branch</span>
            <input type="text" value={branch} onChange={e => setBranch(e.target.value)} placeholder="main" style={{ width: '100%' }} />
          </label>
          <label style={{ flex: 1 }}>
            <span style={{ color: 'var(--muted)', fontSize: 12, display: 'block', marginBottom: 4 }}>Bot email</span>
            <input type="text" value={botEmail} onChange={e => setBotEmail(e.target.value)} placeholder="obsidian-bot@service.local" style={{ width: '100%' }} />
          </label>
        </div>

        <label style={{ display: 'block', marginBottom: 10 }}>
          <span style={{ color: 'var(--muted)', fontSize: 12, display: 'block', marginBottom: 4 }}>Access token</span>
          <input
            type="password"
            value={token}
            onChange={e => { setToken(e.target.value); if (e.target.value) setClearToken(false) }}
            disabled={clearToken}
            placeholder={config?.token_set ? '••••••• (set — leave blank to keep)' : 'Paste a repo-scoped access token'}
            style={{ width: '100%' }}
          />
        </label>
        {config?.token_set && (
          <label style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 16, cursor: 'pointer' }}>
            <input
              type="checkbox" checked={clearToken}
              onChange={e => { setClearToken(e.target.checked); if (e.target.checked) setToken('') }}
              style={{ width: 14, height: 14 }}
            />
            <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>Clear stored token</span>
          </label>
        )}

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 11.5, color: 'var(--ink-4)' }}>
            {config?.token_set ? 'Token is set' : 'No token stored yet'}
            {config?.updated_at && <> · last saved {fmtDateTime(config.updated_at)}</>}
          </span>
          <button className="primary" disabled={!hasChanges || saving} onClick={() => setShowConfirm(true)}>
            {saving ? 'Saving…' : 'Save connection'}
          </button>
        </div>
      </section>

      {/* ── Sync ── */}
      <section style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-md)', padding: 20, background: 'var(--surface)' }}>
        <h2 style={{ fontSize: 15, fontWeight: 700, margin: '0 0 4px' }}>Sync</h2>
        <p style={{ fontSize: 12, color: 'var(--ink-4)', margin: '0 0 16px' }}>
          Full reconcile every run: new/changed notes are ingested, deleted notes are removed, confidential notes are quarantined.
        </p>

        {syncError && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '10px 14px', marginBottom: 16, background: 'var(--t3-bg)', border: '1px solid var(--t3)', borderRadius: 'var(--r-md)', fontSize: 12.5, color: 'var(--ink-2)' }}>
            <Ic.AlertTriangle size={14} style={{ color: 'var(--t3)', flexShrink: 0 }} />
            <span>{syncError}</span>
          </div>
        )}

        {!canConnect && (
          <div style={{ padding: '16px', textAlign: 'center', color: 'var(--ink-4)', fontSize: 13, border: '1px dashed var(--line)', borderRadius: 'var(--r-md)', marginBottom: 16 }}>
            Save a connection above before running a sync.
          </div>
        )}

        {run && (
          <div style={{ marginBottom: 16 }}>
            {run.status === 'failed' ? (
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 9, padding: '10px 14px', background: 'var(--t4-bg)', border: '1px solid var(--t4)', borderRadius: 'var(--r-md)', fontSize: 12.5, color: 'var(--ink-2)' }}>
                <Ic.AlertTriangle size={14} style={{ color: 'var(--t4)', flexShrink: 0, marginTop: 1 }} />
                <div>
                  <div style={{ fontWeight: 600, color: 'var(--t4)' }}>Sync failed</div>
                  <div style={{ marginTop: 2 }}>{run.error_text ?? 'No further detail was recorded.'}</div>
                </div>
              </div>
            ) : (
              <StageStepper stages={RUN_STAGES} labels={RUN_STAGE_LABEL} current={run.status} />
            )}

            {run.status === 'done' && (
              <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 14, fontSize: 12.5 }}>
                {[
                  ['Added', run.added], ['Updated', run.updated], ['Deleted', run.deleted],
                  ['Quarantined', run.quarantined], ['Skipped', run.skipped], ['Failed', run.failed_count],
                ].map(([label, value]) => (
                  <div key={label as string}>
                    <span style={{ fontWeight: 700, color: 'var(--ink)' }}>{value}</span>{' '}
                    <span style={{ color: 'var(--ink-4)' }}>{label}</span>
                  </div>
                ))}
              </div>
            )}
            {run.error_text && run.status === 'done' && (
              <div style={{ marginTop: 10, fontSize: 12, color: 'var(--t3)' }}>{run.error_text}</div>
            )}
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 7, cursor: 'pointer' }}>
            <input type="checkbox" checked={dryRun} onChange={e => setDryRun(e.target.checked)} disabled={syncActive} style={{ width: 14, height: 14 }} />
            <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>Dry run (preview only)</span>
          </label>
          <button className="primary" disabled={!canConnect || syncActive || triggering} onClick={handleSync}>
            {syncActive ? 'Syncing…' : triggering ? 'Starting…' : 'Sync now'}
          </button>
        </div>
      </section>

      {showConfirm && (
        <ConfirmDialog
          title="Confirm connection changes"
          description={`This updates how the gateway connects to your Obsidian vault:\n\n${changeSummary || '(no field changes detected)'}`}
          onConfirm={handleSaveConfig}
          onCancel={() => setShowConfirm(false)}
        />
      )}
    </div>
  )
}
