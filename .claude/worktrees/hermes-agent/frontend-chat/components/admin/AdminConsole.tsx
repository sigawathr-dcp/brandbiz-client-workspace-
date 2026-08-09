'use client'

import { useState } from 'react'
import { useSearchParams } from 'next/navigation'
import type { RolePermissionMatrix, DeptPermissionMatrix, ModelInfo, Department, DashboardMetrics, ModelUsageItem, QuotaDefault } from '@/lib/admin-api'
import { Ic } from '@/components/ui/Icon'
import ConfirmDialog from './ConfirmDialog'

const ROLES = ['L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'ADMIN']
const ROLE_LABELS: Record<string, string> = {
  L1: 'Level 1', L2: 'Level 2', L3: 'Level 3', L4: 'Level 4',
  L5: 'Level 5', L6: 'Level 6', ADMIN: 'Admin',
}
const ROLE_TITLES: Record<string, string> = {
  L1: 'Associate', L2: 'Analyst', L3: 'Senior', L4: 'Lead',
  L5: 'Manager', L6: 'Director', ADMIN: 'Admin',
}

const BUDGET_STEPS = [
  { tokens: 0, label: '0k', cost: 0 },
  { tokens: 400_000, label: '400k', cost: 5 },
  { tokens: 800_000, label: '800k', cost: 10 },
  { tokens: 2_000_000, label: '2M', cost: 24 },
  { tokens: 4_000_000, label: '4M', cost: 48 },
  { tokens: 8_000_000, label: '8M', cost: 96 },
]

function tokensToStep(tokens: number): number {
  return BUDGET_STEPS.reduce(
    (best, s, i) => Math.abs(s.tokens - tokens) < Math.abs(BUDGET_STEPS[best].tokens - tokens) ? i : best,
    0,
  )
}

interface Props {
  roleMatrix: RolePermissionMatrix[]
  deptMatrix: DeptPermissionMatrix[]
  models: ModelInfo[]
  departments: Department[]
  metrics: DashboardMetrics | null
  modelUsage: ModelUsageItem[]
  quotaDefaults: QuotaDefault[]
}

export default function AdminConsole({ roleMatrix, deptMatrix, models, departments, metrics, modelUsage, quotaDefaults }: Props) {
  const sp = useSearchParams()
  const [tab, setTab] = useState<'access' | 'quotas'>(sp.get('tab') === 'quotas' ? 'quotas' : 'access')
  return (
    <div>
      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)' }}>
        {([
          { id: 'access', label: 'External model access', Icon: Ic.Globe },
          { id: 'quotas', label: 'Token quotas & cost caps', Icon: Ic.Sliders },
        ] as const).map(({ id, label, Icon }) => (
          <button key={id} onClick={() => setTab(id)} style={{
            background: 'transparent', padding: '11px 20px', fontSize: 13,
            fontWeight: tab === id ? 600 : 400,
            color: tab === id ? 'var(--text)' : 'var(--muted)',
            borderBottom: tab === id ? '2px solid var(--accent)' : '2px solid transparent',
            borderRadius: 0, display: 'flex', alignItems: 'center', gap: 7,
          }}>
            <Icon size={14} />{label}
          </button>
        ))}
      </div>
      <div style={{ paddingTop: 28 }}>
        {tab === 'access' && <AccessTab roleMatrix={roleMatrix} deptMatrix={deptMatrix} models={models} departments={departments} />}
        {tab === 'quotas' && <QuotasTab metrics={metrics} modelUsage={modelUsage} quotaDefaults={quotaDefaults} />}
      </div>
    </div>
  )
}

function AccessTab({ roleMatrix, deptMatrix, models, departments }: { roleMatrix: RolePermissionMatrix[]; deptMatrix: DeptPermissionMatrix[]; models: ModelInfo[]; departments: Department[] }) {
  const externalModels = models.filter(m => !m.is_local && m.is_active)

  // ---- Role state ----
  const initRolePerms = () => {
    const map: Record<string, Set<string>> = {}
    ROLES.forEach(r => { map[r] = new Set() })
    roleMatrix.forEach(row => { map[row.role] = new Set(row.model_codes) })
    return map
  }
  const [rolePerms, setRolePerms] = useState<Record<string, Set<string>>>(initRolePerms)
  const [roleDirty, setRoleDirty] = useState(false)
  const [rolePending, setRolePending] = useState<{ role: string; codes: string[] } | null>(null)
  const [roleSaving, setRoleSaving] = useState(false)
  const [roleError, setRoleError] = useState('')

  function toggleRole(role: string, code: string) {
    setRolePerms(prev => {
      const next = { ...prev, [role]: new Set(prev[role]) }
      if (next[role].has(code)) next[role].delete(code); else next[role].add(code)
      return next
    })
    setRoleDirty(true)
  }

  async function doSaveRole() {
    if (!rolePending) return
    setRoleSaving(true); setRoleError('')
    try {
      const res = await fetch('/api/admin/permissions/role', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: rolePending.role, model_codes: rolePending.codes }),
      })
      if (!res.ok) throw new Error(await res.text())
    } catch (e: unknown) {
      setRoleError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setRoleSaving(false); setRolePending(null)
    }
  }

  // ---- Department state ----
  const initDeptPerms = () => {
    const map: Record<number, Set<string>> = {}
    departments.forEach(d => { map[d.id] = new Set() })
    deptMatrix.forEach(row => { map[row.department_id] = new Set(row.model_codes) })
    return map
  }
  const [deptPerms, setDeptPerms] = useState<Record<number, Set<string>>>(initDeptPerms)
  const [deptDirty, setDeptDirty] = useState(false)
  const [deptPending, setDeptPending] = useState<{ dept: Department; codes: string[] } | null>(null)
  const [deptSaving, setDeptSaving] = useState(false)
  const [deptError, setDeptError] = useState('')

  function toggleDept(deptId: number, code: string) {
    setDeptPerms(prev => {
      const next = { ...prev, [deptId]: new Set(prev[deptId] ?? []) }
      if (next[deptId].has(code)) next[deptId].delete(code); else next[deptId].add(code)
      return next
    })
    setDeptDirty(true)
  }

  async function doSaveDept() {
    if (!deptPending) return
    setDeptSaving(true); setDeptError('')
    try {
      const res = await fetch('/api/admin/permissions/department', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ department_id: deptPending.dept.id, model_codes: deptPending.codes }),
      })
      if (!res.ok) throw new Error(await res.text())
    } catch (e: unknown) {
      setDeptError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setDeptSaving(false); setDeptPending(null)
    }
  }

  const totalEnabled = ROLES.reduce((n, r) => n + (rolePerms[r]?.size ?? 0), 0)

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, padding: '14px 20px', marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 36, height: 20, borderRadius: 10, background: totalEnabled > 0 ? 'var(--accent)' : 'var(--border)', position: 'relative', flexShrink: 0 }}>
            <div style={{ position: 'absolute', top: 2, left: totalEnabled > 0 ? 18 : 2, width: 16, height: 16, borderRadius: '50%', background: '#fff', boxShadow: '0 1px 2px rgba(0,0,0,.2)', transition: 'left 0.2s' }} />
          </div>
          <div>
            <div style={{ fontWeight: 500, fontSize: 13 }}>External AI providers</div>
            <div style={{ color: 'var(--muted)', fontSize: 12 }}>
              {totalEnabled > 0 ? `${totalEnabled} role-model access grant${totalEnabled !== 1 ? 's' : ''} active` : 'No external model access — all traffic stays local'}
            </div>
          </div>
        </div>
        <div style={{ fontSize: 11, color: 'var(--info)', background: 'var(--info-bg)', border: '1px solid var(--info)', borderRadius: 4, padding: '3px 8px' }}>
          read-only — no master-switch endpoint
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, background: 'var(--warning-bg)', border: '1px solid var(--warning)', borderRadius: 8, padding: '12px 16px', marginBottom: 24, fontSize: 12, color: 'var(--text-2)' }}>
        <Ic.Lock size={14} style={{ color: 'var(--warning)', marginTop: 1, flexShrink: 0 }} />
        <span><strong style={{ color: 'var(--warning)' }}>Tier 3 &amp; Tier 4</strong> messages are always processed locally — the policy engine enforces this before routing.</span>
      </div>

      {externalModels.length === 0 ? (
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, padding: 40, textAlign: 'center', color: 'var(--muted)', fontSize: 13 }}>
          No external models found. Add models in the Models catalog first.
        </div>
      ) : (
        <>
          {/* ---- Role × Model matrix ---- */}
          {roleError && <div style={{ background: 'var(--danger-bg)', border: '1px solid var(--danger)', color: 'var(--danger)', borderRadius: 6, padding: '8px 12px', fontSize: 13, marginBottom: 16 }}>{roleError}</div>}
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden', marginBottom: 28 }}>
            <div style={{ padding: '12px 20px', borderBottom: '1px solid var(--border)' }}>
              <div style={{ fontWeight: 600, fontSize: 13 }}>Role × Model access matrix</div>
              <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 2 }}>Check a cell to allow that role to route to the external model. Save per row.</div>
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table>
                <thead>
                  <tr>
                    <th style={{ width: 110 }}>Role</th>
                    {externalModels.map(m => (
                      <th key={m.code} style={{ minWidth: 110, textAlign: 'center' }}>
                        <div style={{ fontWeight: 500 }}>{m.display_name}</div>
                        <div style={{ color: 'var(--muted)', fontWeight: 400, fontSize: 10 }}>{m.provider}</div>
                      </th>
                    ))}
                    <th style={{ width: 80 }}></th>
                  </tr>
                </thead>
                <tbody>
                  {ROLES.map(role => (
                    <tr key={role}>
                      <td><div style={{ fontWeight: 500, fontSize: 12 }}>{role}</div><div style={{ color: 'var(--muted)', fontSize: 11 }}>{ROLE_LABELS[role]}</div></td>
                      {externalModels.map(m => (
                        <td key={m.code} style={{ textAlign: 'center' }}>
                          <input type="checkbox" checked={rolePerms[role]?.has(m.code) ?? false} onChange={() => toggleRole(role, m.code)} style={{ width: 15, height: 15, cursor: 'pointer', accentColor: 'var(--accent)' }} />
                        </td>
                      ))}
                      <td>
                        <button className="primary" onClick={() => setRolePending({ role, codes: [...rolePerms[role]] })} style={{ fontSize: 12, padding: '4px 12px' }}>Save</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {roleDirty && (
              <div style={{ padding: '10px 20px', borderTop: '1px solid var(--border)', background: 'var(--accent-subtle)', display: 'flex', alignItems: 'center', gap: 10, fontSize: 12, color: 'var(--accent)' }}>
                <Ic.AlertCircle size={13} />
                Unsaved changes — click Save on any modified row to persist.
              </div>
            )}
          </div>

          {/* ---- Department × Model matrix ---- */}
          {departments.length > 0 && (
            <>
              {deptError && <div style={{ background: 'var(--danger-bg)', border: '1px solid var(--danger)', color: 'var(--danger)', borderRadius: 6, padding: '8px 12px', fontSize: 13, marginBottom: 16 }}>{deptError}</div>}
              <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden' }}>
                <div style={{ padding: '12px 20px', borderBottom: '1px solid var(--border)' }}>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>Department × Model access matrix</div>
                  <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 2 }}>
                    Department grants are additive to role grants — a user in a department gains access to any model checked here regardless of role.
                  </div>
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <table>
                    <thead>
                      <tr>
                        <th style={{ width: 160 }}>Department</th>
                        {externalModels.map(m => (
                          <th key={m.code} style={{ minWidth: 110, textAlign: 'center' }}>
                            <div style={{ fontWeight: 500 }}>{m.display_name}</div>
                            <div style={{ color: 'var(--muted)', fontWeight: 400, fontSize: 10 }}>{m.provider}</div>
                          </th>
                        ))}
                        <th style={{ width: 80 }}></th>
                      </tr>
                    </thead>
                    <tbody>
                      {departments.map(dept => (
                        <tr key={dept.id}>
                          <td>
                            <div style={{ fontWeight: 500, fontSize: 12 }}>{dept.code}</div>
                            <div style={{ color: 'var(--muted)', fontSize: 11 }}>{dept.name}</div>
                          </td>
                          {externalModels.map(m => (
                            <td key={m.code} style={{ textAlign: 'center' }}>
                              <input
                                type="checkbox"
                                checked={deptPerms[dept.id]?.has(m.code) ?? false}
                                onChange={() => toggleDept(dept.id, m.code)}
                                style={{ width: 15, height: 15, cursor: 'pointer', accentColor: 'var(--accent)' }}
                              />
                            </td>
                          ))}
                          <td>
                            <button
                              className="primary"
                              onClick={() => setDeptPending({ dept, codes: [...(deptPerms[dept.id] ?? [])] })}
                              style={{ fontSize: 12, padding: '4px 12px' }}
                            >
                              Save
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {deptDirty && (
                  <div style={{ padding: '10px 20px', borderTop: '1px solid var(--border)', background: 'var(--accent-subtle)', display: 'flex', alignItems: 'center', gap: 10, fontSize: 12, color: 'var(--accent)' }}>
                    <Ic.AlertCircle size={13} />
                    Unsaved changes — click Save on any modified row to persist.
                  </div>
                )}
              </div>
            </>
          )}
        </>
      )}

      {rolePending && (
        <ConfirmDialog
          title={`Update ${rolePending.role} permissions`}
          description={rolePending.codes.length === 0 ? `Remove all external model access for ${rolePending.role}.` : `Grant ${rolePending.role} access to:\n${rolePending.codes.join(', ')}`}
          onConfirm={doSaveRole}
          onCancel={() => setRolePending(null)}
          confirmLabel={roleSaving ? 'Saving…' : 'Apply'}
        />
      )}

      {deptPending && (
        <ConfirmDialog
          title={`Update ${deptPending.dept.code} permissions`}
          description={deptPending.codes.length === 0 ? `Remove all external model access for ${deptPending.dept.name}.` : `Grant ${deptPending.dept.name} access to:\n${deptPending.codes.join(', ')}`}
          onConfirm={doSaveDept}
          onCancel={() => setDeptPending(null)}
          confirmLabel={deptSaving ? 'Saving…' : 'Apply'}
        />
      )}
    </div>
  )
}

function QuotasTab({
  metrics,
  modelUsage,
  quotaDefaults,
}: {
  metrics: DashboardMetrics | null
  modelUsage: ModelUsageItem[]
  quotaDefaults: QuotaDefault[]
}) {
  const maxCost = Math.max(...modelUsage.map(i => i.cost_usd), 0.0001)

  type QuotaEditState = { limit: number; is_unlimited: boolean }
  const initState = (): Record<string, QuotaEditState> => {
    const map: Record<string, QuotaEditState> = {}
    quotaDefaults.forEach(q => {
      map[q.role] = {
        limit: q.is_unlimited ? BUDGET_STEPS[BUDGET_STEPS.length - 1].tokens : q.monthly_token_limit,
        is_unlimited: q.is_unlimited,
      }
    })
    return map
  }
  const [quotaState, setQuotaState] = useState<Record<string, QuotaEditState>>(initState)
  const [pending, setPending] = useState<{ role: string; limit: number; is_unlimited: boolean } | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')

  const quotaMap: Record<string, QuotaDefault> = Object.fromEntries(quotaDefaults.map(q => [q.role, q]))

  function setStepForRole(role: string, stepIdx: number) {
    setQuotaState(prev => ({
      ...prev,
      [role]: { limit: BUDGET_STEPS[stepIdx].tokens, is_unlimited: false },
    }))
  }

  async function doSave() {
    if (!pending) return
    setSaving(true); setSaveError('')
    try {
      const res = await fetch('/api/admin/quota-defaults', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          role: pending.role,
          monthly_token_limit: pending.is_unlimited ? 0 : pending.limit,
          is_unlimited: pending.is_unlimited,
        }),
      })
      if (!res.ok) throw new Error(await res.text())
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : 'Save failed')
      const live = quotaMap[pending.role]
      if (live) setQuotaState(prev => ({ ...prev, [pending.role]: { limit: live.monthly_token_limit, is_unlimited: live.is_unlimited } }))
    } finally {
      setSaving(false); setPending(null)
    }
  }

  function handleCancelSave() {
    if (!pending) return
    const live = quotaMap[pending.role]
    if (live) setQuotaState(prev => ({ ...prev, [pending.role]: { limit: live.monthly_token_limit, is_unlimited: live.is_unlimited } }))
    setPending(null)
  }

  return (
    <div>

      {/* Metric cards */}
      {metrics && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 14, marginBottom: 28 }}>
          {[
            { label: 'Active users', value: metrics.active_users.toLocaleString(), Icon: Ic.Users, accent: false },
            { label: 'Messages (month)', value: metrics.total_messages_month.toLocaleString(), Icon: Ic.MessageSquare, accent: false },
            { label: 'External cost', value: `$${metrics.external_cost_month_usd.toFixed(2)}`, Icon: Ic.TrendingUp, accent: metrics.external_cost_month_usd > 0 },
            { label: 'PII blocks', value: metrics.pii_blocks_month.toLocaleString(), Icon: Ic.Shield, accent: metrics.pii_blocks_month > 0 },
            { label: 'Pending reveals', value: metrics.pending_reveals.toLocaleString(), Icon: Ic.Eye, accent: metrics.pending_reveals > 0 },
          ].map(({ label, value, Icon, accent }) => (
            <div key={label} style={{ background: 'var(--surface)', border: `1px solid ${accent ? 'var(--warning)' : 'var(--border)'}`, borderRadius: 8, padding: '16px 18px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <span style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--muted)' }}>{label}</span>
                <Icon size={14} style={{ color: accent ? 'var(--warning)' : 'var(--muted)', flexShrink: 0 }} />
              </div>
              <div style={{ fontSize: 26, fontWeight: 700, marginTop: 8, color: accent ? 'var(--warning)' : 'var(--text)' }}>{value}</div>
            </div>
          ))}
        </div>
      )}

      {/* External model usage bar chart */}
      {modelUsage.length > 0 && (
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, padding: '20px 24px', marginBottom: 28 }}>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 16 }}>External model usage — this month</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {modelUsage.map(item => (
              <div key={item.model_code}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: 12 }}>
                  <span style={{ fontWeight: 500 }}>{item.model_code}</span>
                  <span style={{ color: 'var(--muted)' }}>
                    {item.message_count.toLocaleString()} msgs &nbsp;·&nbsp;
                    {(item.tokens_input + item.tokens_output).toLocaleString()} tokens &nbsp;·&nbsp;
                    <span style={{ color: item.cost_usd > 0 ? 'var(--warning)' : 'var(--muted)' }}>${item.cost_usd.toFixed(4)}</span>
                  </span>
                </div>
                <div style={{ background: 'var(--border)', borderRadius: 4, height: 6 }}>
                  <div style={{ background: 'var(--accent)', height: 6, borderRadius: 4, width: `${Math.max((item.cost_usd / maxCost) * 100, item.cost_usd > 0 ? 2 : 0)}%`, transition: 'width 0.3s' }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Per-role budget table */}
      {saveError && (
        <div style={{ background: 'var(--danger-bg)', border: '1px solid var(--danger)', color: 'var(--danger)', borderRadius: 6, padding: '8px 12px', fontSize: 13, marginBottom: 16 }}>
          {saveError}
        </div>
      )}

      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden' }}>
        <div style={{ padding: '14px 24px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
          <Ic.Users size={14} style={{ color: 'var(--muted)' }} />
          <span style={{ fontWeight: 600, fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text)' }}>Budget Per Role</span>
        </div>

        <table>
          <thead>
            <tr>
              <th style={{ width: 155 }}>Role</th>
              <th>Monthly External Token Budget</th>
              <th style={{ width: 105, textAlign: 'right' }}>Cost Cap</th>
              <th style={{ width: 145, textAlign: 'right' }}>Usage</th>
            </tr>
          </thead>
          <tbody>
            {ROLES.filter(r => r !== 'ADMIN').map(role => {
              const st = quotaState[role] ?? { limit: 0, is_unlimited: false }
              const stepIdx = tokensToStep(st.limit)
              const step = BUDGET_STEPS[stepIdx]
              // p ∈ [0,1]: fraction along the slider
              const p = BUDGET_STEPS.length > 1 ? stepIdx / (BUDGET_STEPS.length - 1) : 0
              const live = quotaMap[role]
              const totalCap = live && !live.is_unlimited && live.user_count > 0
                ? live.monthly_token_limit * live.user_count : 0
              const usagePct = totalCap > 0 ? Math.min((live!.tokens_used_month / totalCap) * 100, 100) : 0

              return (
                <tr key={role}>
                  <td>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>{role} · {ROLE_TITLES[role]}</div>
                    <div style={{ color: 'var(--muted)', fontSize: 11 }}>{live?.user_count ?? 0} people</div>
                  </td>
                  <td style={{ paddingRight: 20 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                      {/*
                        Custom slider: transparent range input sits on top (z-index 2) for
                        all pointer events; visual track + fill + thumb are pure divs beneath.
                        Thumb size = 16px (T). Container width = C.
                          Thumb left  = p*(C-T)       → left: calc(p*100% - p*T px)
                          Fill width inside track      → p*100% of track (track inset T/2 each side)
                        This makes fill-right-edge equal thumb-center at every p value.
                      */}
                      <div style={{ position: 'relative', flex: 1, height: 20, display: 'flex', alignItems: 'center' }}>
                        {/* Gray track */}
                        <div style={{ position: 'absolute', left: 8, right: 8, height: 4, borderRadius: 2, background: 'var(--border)', overflow: 'hidden' }}>
                          {/* Purple fill — p*100% of the track width aligns with thumb center */}
                          <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${p * 100}%`, background: 'var(--accent)', borderRadius: 2 }} />
                        </div>
                        {/* Thumb dot — left: p*(100% - 16px) */}
                        <div style={{
                          position: 'absolute',
                          left: `calc(${p * 100}% - ${p * 16}px)`,
                          width: 16, height: 16, borderRadius: '50%',
                          background: 'var(--accent)',
                          boxShadow: '0 1px 4px rgba(0,0,0,.25)',
                          pointerEvents: 'none',
                          zIndex: 1,
                        }} />
                        {/* Transparent range input — handles all interaction */}
                        <input
                          type="range"
                          min={0}
                          max={BUDGET_STEPS.length - 1}
                          value={stepIdx}
                          step={1}
                          onChange={e => setStepForRole(role, parseInt(e.target.value))}
                          onMouseUp={e => {
                            const newIdx = parseInt((e.target as HTMLInputElement).value)
                            const savedStep = live ? tokensToStep(live.monthly_token_limit) : 0
                            if (newIdx !== savedStep) {
                              setPending({ role, limit: BUDGET_STEPS[newIdx].tokens, is_unlimited: false })
                            }
                          }}
                          style={{
                            position: 'absolute', left: 0, top: 0, width: '100%', height: '100%',
                            opacity: 0, cursor: 'pointer', margin: 0, zIndex: 2,
                          }}
                        />
                      </div>
                      <span style={{ fontWeight: 700, fontSize: 14, minWidth: 44, textAlign: 'right' }}>{step.label}</span>
                    </div>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <span style={{ fontWeight: 600, fontSize: 13 }}>${step.cost}</span>
                    <span style={{ color: 'var(--muted)', fontSize: 12 }}>/mo</span>
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, justifyContent: 'flex-end' }}>
                      <div style={{ width: 80, background: 'var(--border)', borderRadius: 3, height: 4, flexShrink: 0 }}>
                        <div style={{
                          background: usagePct > 80 ? 'var(--warning)' : 'var(--accent)',
                          height: 4, borderRadius: 3,
                          width: `${usagePct}%`,
                          transition: 'width 0.3s',
                        }} />
                      </div>
                      <span style={{ fontSize: 12, fontWeight: 600, minWidth: 32, textAlign: 'right' }}>
                        {Math.round(usagePct)}%
                      </span>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {pending && (
        <ConfirmDialog
          title={`Update ${pending.role} token budget`}
          description={`Set ${pending.role} (${ROLE_TITLES[pending.role]}) monthly token limit to ${BUDGET_STEPS[tokensToStep(pending.limit)].label} tokens ($${BUDGET_STEPS[tokensToStep(pending.limit)].cost}/mo). Changes apply immediately.`}
          onConfirm={doSave}
          onCancel={handleCancelSave}
          confirmLabel={saving ? 'Saving…' : 'Apply'}
        />
      )}
    </div>
  )
}
