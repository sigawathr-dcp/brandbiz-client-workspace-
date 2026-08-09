import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { fetchAuditLog, type AuditLogListResponse } from '@/lib/admin-api'
import AuditTable from '@/components/admin/AuditTable'

export const metadata = { title: 'Audit Log — AI Gateway' }

export default async function AuditPage() {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) redirect('/login')

  let data: AuditLogListResponse = { items: [], total: 0 }
  try {
    data = await fetchAuditLog(token, { limit: '50', offset: '0' })
  } catch {
    // Show empty state if backend unavailable
  }

  return (
    <div style={{ padding: 32, maxWidth: 1280, margin: '0 auto' }}>
      <div style={{ marginBottom: 28 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700 }}>Audit Log</h1>
            <p style={{ color: 'var(--muted)', fontSize: 13, marginTop: 4 }}>
              Append-only record of all system events.
            </p>
          </div>
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 6, padding: '6px 12px', fontSize: 12, color: 'var(--muted)' }}>
            {data.total.toLocaleString()} entries
          </div>
        </div>
      </div>
      <AuditTable initialData={data} />
    </div>
  )
}
