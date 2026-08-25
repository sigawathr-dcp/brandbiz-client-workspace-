'use client'

import { useEffect, useState } from 'react'

interface Invite {
  id: string
  expires_at: string
  redeemed_at: string | null
  contact_name: string | null
  created_at: string
}

interface AgentConfig {
  agent: {
    id: string
    name: string
    description: string | null
    model: string
    capabilities: Record<string, boolean> | null
    creativity_level: number
    status: string
  } | null
  pinned_skills: { id: string; name: string; description: string | null }[]
  knowledge_files: { id: string; filename: string; scope: string; workspace_id: string | null }[]
}

// Client Workspaces admin screen (Phase 5/6, D21/D22) — workspace detail:
// mint invite links, and the read-only "น้อง brandbiz agent" view the design
// calls for. Everything shown here is authored in the existing internal
// Agent/Skills/Knowledge UI — this page adds no new authoring surface, only
// a way to see it scoped to one client and a way to assign an Agent to it.
export default function ClientDetailPage({ workspaceId }: { workspaceId: string }) {
  const [invites, setInvites] = useState<Invite[] | null>(null)
  const [config, setConfig] = useState<AgentConfig | null>(null)
  const [newInviteUrl, setNewInviteUrl] = useState('')
  const [minting, setMinting] = useState(false)
  const [agentIdInput, setAgentIdInput] = useState('')
  const [assigning, setAssigning] = useState(false)

  async function loadInvites() {
    const res = await fetch(`/api/admin/clients/${workspaceId}/invites`, { credentials: 'include', cache: 'no-store' })
    if (res.ok) setInvites(await res.json())
  }
  async function loadAgent() {
    const res = await fetch(`/api/admin/clients/${workspaceId}/agent`, { credentials: 'include', cache: 'no-store' })
    if (res.ok) setConfig(await res.json())
  }

  useEffect(() => {
    loadInvites()
    loadAgent()
  }, [workspaceId])

  async function mintInvite() {
    setMinting(true)
    setNewInviteUrl('')
    try {
      const res = await fetch(`/api/admin/clients/${workspaceId}/invites`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({}),
      })
      if (!res.ok) return
      const data = await res.json()
      setNewInviteUrl(`${window.location.origin}${data.invite_url_path}`)
      await loadInvites()
    } finally {
      setMinting(false)
    }
  }

  async function assignAgent() {
    if (!agentIdInput.trim()) return
    setAssigning(true)
    try {
      const res = await fetch(`/api/admin/clients/${workspaceId}/agent`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ agent_id: agentIdInput.trim() }),
      })
      if (res.ok || res.status === 204) {
        setAgentIdInput('')
        await loadAgent()
      }
    } finally {
      setAssigning(false)
    }
  }

  return (
    <div style={{ padding: 32, maxWidth: 900, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <a href="/clients" style={{ fontSize: 13, color: 'var(--ink-2)', textDecoration: 'none' }}>
        ← Client workspaces
      </a>

      {/* Invites */}
      <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 12, padding: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>Invite links</div>
          <div style={{ flex: 1 }} />
          <button
            onClick={mintInvite}
            disabled={minting}
            style={{ height: 32, padding: '0 13px', borderRadius: 7, border: 'none', background: 'var(--accent)', color: '#fff', fontSize: 12.5, fontWeight: 500, cursor: minting ? 'default' : 'pointer' }}
          >
            {minting ? 'Minting…' : 'Mint invite'}
          </button>
        </div>
        {newInviteUrl && (
          <div style={{ marginBottom: 12, fontSize: 12, fontFamily: 'var(--font-mono)', background: 'var(--surface-2)', borderRadius: 7, padding: '8px 10px', wordBreak: 'break-all' }}>
            {newInviteUrl}
          </div>
        )}
        {invites?.length === 0 && <div style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>No invites minted yet.</div>}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {invites?.map((inv) => (
            <div key={inv.id} style={{ display: 'flex', gap: 10, fontSize: 12.5, color: 'var(--ink-2)', padding: '6px 0', borderTop: '1px solid var(--line)' }}>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--ink-3)' }}>{inv.id.slice(0, 8)}</span>
              <span>{inv.redeemed_at ? 'redeemed' : 'unredeemed'}</span>
              <span style={{ color: 'var(--ink-3)' }}>expires {new Date(inv.expires_at).toLocaleDateString()}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Agent config (read-only) */}
      <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 12, padding: 18 }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink)', marginBottom: 12 }}>น้อง brandbiz agent</div>

        {config?.agent ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--ink)' }}>{config.agent.name}</div>
              <div style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>
                model {config.agent.model} · creativity {config.agent.creativity_level}/100 · {config.agent.status}
              </div>
              {config.agent.description && (
                <div style={{ fontSize: 13, color: 'var(--ink-2)', marginTop: 6 }}>{config.agent.description}</div>
              )}
              <a href={`/agent/${config.agent.id}/edit`} style={{ fontSize: 12, color: 'var(--accent)' }}>
                Edit in the agent authoring UI →
              </a>
            </div>

            {config.agent.capabilities && (
              <div>
                <div style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 6 }}>
                  Capabilities
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {Object.entries(config.agent.capabilities).map(([k, v]) => (
                    <span
                      key={k}
                      style={{
                        fontSize: 11.5,
                        padding: '3px 9px',
                        borderRadius: 99,
                        background: v ? 'var(--t1-bg)' : 'var(--surface-2)',
                        color: v ? 'var(--t1)' : 'var(--ink-3)',
                      }}
                    >
                      {k} {v ? 'on' : 'off'}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div>
              <div style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 6 }}>
                Pinned skills
              </div>
              {config.pinned_skills.length === 0 ? (
                <div style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>None pinned.</div>
              ) : (
                config.pinned_skills.map((s) => (
                  <div key={s.id} style={{ fontSize: 13, color: 'var(--ink-2)', padding: '4px 0' }}>
                    {s.name} — <span style={{ color: 'var(--ink-3)' }}>{s.description}</span>
                  </div>
                ))
              )}
            </div>

            <div>
              <div style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 6 }}>
                Knowledge files
              </div>
              {config.knowledge_files.length === 0 ? (
                <div style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>None attached.</div>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', fontSize: 12.5, borderCollapse: 'collapse' }}>
                    <thead>
                      <tr>
                        <th style={{ textAlign: 'left', color: 'var(--ink-3)', fontWeight: 600, padding: '0 0 6px' }}>File</th>
                        <th style={{ textAlign: 'left', color: 'var(--ink-3)', fontWeight: 600, padding: '0 0 6px' }}>Scope</th>
                      </tr>
                    </thead>
                    <tbody>
                      {config.knowledge_files.map((f) => (
                        <tr key={f.id}>
                          <td style={{ padding: '4px 0', borderTop: '1px solid var(--line)', fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>{f.filename}</td>
                          <td style={{ padding: '4px 0', borderTop: '1px solid var(--line)', whiteSpace: 'nowrap' }}>
                            {f.scope}
                            {f.workspace_id ? ' (this workspace)' : f.scope === 'org' ? ' (internal-shared)' : ''}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>No agent assigned yet.</div>
        )}

        <div style={{ marginTop: 16, borderTop: '1px solid var(--line)', paddingTop: 14, display: 'flex', gap: 8 }}>
          <input
            value={agentIdInput}
            onChange={(e) => setAgentIdInput(e.target.value)}
            placeholder="Agent UUID (from /agent)"
            style={{ flex: 1, height: 32, borderRadius: 7, border: '1px solid var(--line-2)', padding: '0 10px', fontSize: 12.5, fontFamily: 'var(--font-mono)' }}
          />
          <button
            onClick={assignAgent}
            disabled={assigning}
            style={{ height: 32, padding: '0 13px', borderRadius: 7, border: 'none', background: 'var(--accent)', color: '#fff', fontSize: 12.5, fontWeight: 500, cursor: assigning ? 'default' : 'pointer' }}
          >
            {assigning ? 'Assigning…' : 'Assign'}
          </button>
        </div>
      </div>
    </div>
  )
}
