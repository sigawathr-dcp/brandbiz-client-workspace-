import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { fetchUsers, fetchDepartments } from '@/lib/admin-api'
import UsersTable from '@/components/admin/UsersTable'

export const metadata = { title: 'Users — AI Gateway' }

export default async function UsersPage() {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) redirect('/login')

  let data: Awaited<ReturnType<typeof fetchUsers>> = { items: [], total: 0 }
  let departments: Awaited<ReturnType<typeof fetchDepartments>> = []

  try {
    ;[data, departments] = await Promise.all([
      fetchUsers(token, { limit: '50', offset: '0' }),
      fetchDepartments(token),
    ])
  } catch {
    // Show empty state if backend unavailable
  }

  return (
    <div style={{ padding: 32, maxWidth: 1280, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700 }}>Users</h1>
          <p style={{ color: 'var(--muted)', fontSize: 13, marginTop: 4 }}>
            Manage roles, active status, and department memberships.
          </p>
        </div>
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 6, padding: '6px 12px', fontSize: 12, color: 'var(--muted)' }}>
          {data.total.toLocaleString()} total
        </div>
      </div>
      <UsersTable initialItems={data.items} initialTotal={data.total} departments={departments} />
    </div>
  )
}
