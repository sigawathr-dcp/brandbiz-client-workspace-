/**
 * Server-side admin API client — called from Next.js server components only.
 * Forwards requests to FastAPI backend via BACKEND_URL with Bearer auth.
 */

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000'

export interface UserSummary {
  id: string
  google_email: string
  display_name: string | null
  role: string
  is_active: boolean
  department_ids: number[]
  created_at: string
  last_login_at: string | null
}

export interface UserListResponse {
  items: UserSummary[]
  total: number
}

export interface PatchUserBody {
  role?: string
  is_active?: boolean
  department_ids?: number[]
}

export interface RolePermissionMatrix {
  role: string
  model_codes: string[]
}

export interface DeptPermissionMatrix {
  department_id: number
  model_codes: string[]
}

export interface ModelInfo {
  id: number
  code: string
  display_name: string
  provider: string
  is_local: boolean
  is_active: boolean
}

export interface Department {
  id: number
  code: string
  name: string
}

export interface DashboardMetrics {
  active_users: number
  total_messages_month: number
  external_cost_month_usd: number
  pii_blocks_month: number
  pending_reveals: number
  period_start: string
}

export interface ModelUsageItem {
  model_code: string
  tokens_input: number
  tokens_output: number
  cost_usd: number
  message_count: number
}

export interface TopUserItem {
  user_id: string
  email: string
  display_name: string | null
  cost_usd: number
  message_count: number
}

export interface AuditLogEntry {
  id: number
  created_at: string
  user_id: string | null
  actor_id: string | null
  action: string
  resource_type: string | null
  resource_id: string | null
  details: Record<string, unknown> | null
  ip_address: string | null
  user_agent: string | null
}

export interface AuditLogListResponse {
  items: AuditLogEntry[]
  total: number
}

export interface RevealRequestSummary {
  id: string
  requester_id: string
  target_user_id: string | null
  target_message_id: string
  reason: string
  status: string
  approver_id: string | null
  approved_at: string | null
  expires_at: string | null
  viewed_at: string | null
  created_at: string
}

function authHeader(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
}

async function apiGet<T>(path: string, token: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(`${BACKEND}${path}`)
  if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
  const res = await fetch(url.toString(), { headers: authHeader(token), cache: 'no-store' })
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

async function apiPatch<T>(path: string, token: string, body: unknown): Promise<T> {
  const res = await fetch(`${BACKEND}${path}`, {
    method: 'PATCH',
    headers: authHeader(token),
    body: JSON.stringify(body),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error((await res.text()) || `PATCH ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

async function apiPut<T>(path: string, token: string, body: unknown): Promise<T> {
  const res = await fetch(`${BACKEND}${path}`, {
    method: 'PUT',
    headers: authHeader(token),
    body: JSON.stringify(body),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error((await res.text()) || `PUT ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

export async function fetchUsers(token: string, params?: Record<string, string>): Promise<UserListResponse> {
  return apiGet('/admin/users', token, params)
}

export async function patchUser(token: string, userId: string, body: PatchUserBody): Promise<UserSummary> {
  return apiPatch(`/admin/users/${userId}`, token, body)
}

export async function fetchRolePermissions(token: string): Promise<RolePermissionMatrix[]> {
  return apiGet('/admin/permissions/role', token)
}

export async function putRolePermissions(token: string, body: RolePermissionMatrix): Promise<RolePermissionMatrix> {
  return apiPut('/admin/permissions/role', token, body)
}

export async function fetchDeptPermissions(token: string): Promise<DeptPermissionMatrix[]> {
  return apiGet('/admin/permissions/department', token)
}

export async function putDeptPermissions(token: string, body: DeptPermissionMatrix): Promise<DeptPermissionMatrix> {
  return apiPut('/admin/permissions/department', token, body)
}

export async function fetchModels(token: string): Promise<ModelInfo[]> {
  const res = await fetch(`${BACKEND}/admin/models`, { headers: authHeader(token), cache: 'no-store' })
  if (!res.ok) return []
  return res.json()
}

export async function fetchDepartments(token: string): Promise<Department[]> {
  const res = await fetch(`${BACKEND}/admin/departments`, { headers: authHeader(token), cache: 'no-store' })
  if (!res.ok) return []
  return res.json()
}

export async function fetchMetrics(token: string, refresh = false): Promise<DashboardMetrics> {
  return apiGet('/admin/metrics', token, refresh ? { refresh: 'true' } : undefined)
}

export async function fetchModelUsage(token: string): Promise<ModelUsageItem[]> {
  return apiGet('/admin/metrics/model-usage', token)
}

export async function fetchTopUsers(token: string): Promise<TopUserItem[]> {
  return apiGet('/admin/metrics/top-users', token)
}

export async function fetchAuditLog(
  token: string,
  params?: Record<string, string>
): Promise<AuditLogListResponse> {
  return apiGet('/admin/audit', token, params)
}

export async function fetchReveals(
  token: string,
  params?: Record<string, string>
): Promise<RevealRequestSummary[]> {
  return apiGet('/admin/reveals', token, params)
}

export async function approveReveal(token: string, id: string): Promise<RevealRequestSummary> {
  const res = await fetch(`${BACKEND}/reveal/${id}/approve`, {
    method: 'POST',
    headers: authHeader(token),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error(`approve ${id} → ${res.status}`)
  return res.json()
}

export async function denyReveal(token: string, id: string): Promise<RevealRequestSummary> {
  const res = await fetch(`${BACKEND}/reveal/${id}/deny`, {
    method: 'POST',
    headers: authHeader(token),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error(`deny ${id} → ${res.status}`)
  return res.json()
}

export interface QuotaDefault {
  role: string
  monthly_token_limit: number
  is_unlimited: boolean
  tokens_used_month: number
  user_count: number
}

export async function fetchQuotaDefaults(token: string): Promise<QuotaDefault[]> {
  return apiGet('/admin/quota-defaults', token)
}

export async function putQuotaDefault(
  token: string,
  body: { role: string; monthly_token_limit: number; is_unlimited: boolean },
): Promise<QuotaDefault> {
  return apiPut('/admin/quota-defaults', token, body)
}

// ---------------------------------------------------------------------------
// Obsidian vault connection + sync
// ---------------------------------------------------------------------------

export interface VaultConfig {
  git_url: string | null
  branch: string
  bot_email: string
  templates_dirname: string
  token_set: boolean
  updated_at: string | null
}

export interface VaultConfigUpdate {
  git_url: string
  branch: string
  /** Omit to leave any existing token untouched; "" clears it. */
  token?: string
  bot_email?: string
  templates_dirname?: string
}

export interface VaultSyncRun {
  id: string
  status: 'cloning' | 'pulling' | 'reconciling' | 'done' | 'failed'
  added: number
  updated: number
  deleted: number
  quarantined: number
  skipped: number
  failed_count: number
  error_text: string | null
  dry_run: boolean
  started_at: string
  finished_at: string | null
}

export async function fetchVaultConfig(token: string): Promise<VaultConfig> {
  return apiGet('/admin/vault/config', token)
}

export async function putVaultConfig(token: string, body: VaultConfigUpdate): Promise<VaultConfig> {
  return apiPut('/admin/vault/config', token, body)
}

export async function triggerVaultSync(token: string, dryRun = false): Promise<VaultSyncRun> {
  const res = await fetch(`${BACKEND}/admin/vault/sync`, {
    method: 'POST',
    headers: authHeader(token),
    body: JSON.stringify({ dry_run: dryRun }),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error((await res.text()) || `POST /admin/vault/sync → ${res.status}`)
  return res.json()
}

export async function fetchVaultSyncRun(token: string, runId: string): Promise<VaultSyncRun> {
  return apiGet(`/admin/vault/sync/${runId}`, token)
}

export async function fetchLatestVaultSyncRun(token: string): Promise<VaultSyncRun | null> {
  const res = await fetch(`${BACKEND}/admin/vault/sync/latest`, { headers: authHeader(token), cache: 'no-store' })
  if (!res.ok) return null
  const text = await res.text()
  return text ? JSON.parse(text) : null
}
