import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { fetchRolePermissions, fetchDeptPermissions, fetchModels, fetchDepartments, fetchMetrics, fetchModelUsage, fetchQuotaDefaults } from '@/lib/admin-api'
import AdminConsole from '@/components/admin/AdminConsole'

export const metadata = { title: 'Admin Console — AI Gateway' }

export default async function AdminConsolePage() {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) redirect('/login')

  const [roleMatrix, deptMatrix, models, departments, metricsResult, modelUsage, quotaDefaultsResult] =
    await Promise.allSettled([
      fetchRolePermissions(token),
      fetchDeptPermissions(token),
      fetchModels(token),
      fetchDepartments(token),
      fetchMetrics(token),
      fetchModelUsage(token),
      fetchQuotaDefaults(token),
    ])

  return (
    <div style={{ padding: 32, maxWidth: 1280, margin: '0 auto' }}>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700 }}>Admin Console</h1>
        <p style={{ color: 'var(--muted)', fontSize: 13, marginTop: 4 }}>
          Manage external model access by role and review token quota usage.
          All permission changes are atomic and logged.
        </p>
      </div>
      <AdminConsole
        roleMatrix={roleMatrix.status === 'fulfilled' ? roleMatrix.value : []}
        deptMatrix={deptMatrix.status === 'fulfilled' ? deptMatrix.value : []}
        models={models.status === 'fulfilled' ? models.value : []}
        departments={departments.status === 'fulfilled' ? departments.value : []}
        metrics={metricsResult.status === 'fulfilled' ? metricsResult.value : null}
        modelUsage={modelUsage.status === 'fulfilled' ? modelUsage.value : []}
        quotaDefaults={quotaDefaultsResult.status === 'fulfilled' ? quotaDefaultsResult.value : []}
      />
    </div>
  )
}
