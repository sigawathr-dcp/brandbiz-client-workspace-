import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { fetchVaultConfig, fetchLatestVaultSyncRun } from '@/lib/admin-api'
import VaultSyncPage from '@/components/admin/VaultSyncPage'

export const metadata = { title: 'Vault Sync — AI Gateway' }

export default async function VaultSyncRoute() {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) redirect('/login')

  const [configResult, latestRunResult] = await Promise.allSettled([
    fetchVaultConfig(token),
    fetchLatestVaultSyncRun(token),
  ])

  return (
    <div style={{ padding: 32, maxWidth: 760, margin: '0 auto' }}>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700 }}>Vault sync</h1>
        <p style={{ color: 'var(--muted)', fontSize: 13, marginTop: 4 }}>
          Connect a shared Obsidian vault (git repo) so its notes are searchable in chat.
          Confidential notes are quarantined automatically and never leave the org.
        </p>
      </div>
      <VaultSyncPage
        initialConfig={configResult.status === 'fulfilled' ? configResult.value : null}
        initialRun={latestRunResult.status === 'fulfilled' ? latestRunResult.value : null}
      />
    </div>
  )
}
