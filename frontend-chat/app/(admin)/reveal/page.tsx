import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { fetchReveals, type RevealRequestSummary } from '@/lib/admin-api'
import RevealQueue from '@/components/admin/RevealQueue'

export const metadata = { title: 'Reveal Queue — AI Gateway' }

export default async function RevealPage() {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) redirect('/login')

  let allReveals: RevealRequestSummary[] = []
  try {
    allReveals = await fetchReveals(token, { limit: '100' })
  } catch {
    // Show empty state if backend unavailable
  }

  return (
    <div style={{ padding: 32, maxWidth: 1000, margin: '0 auto' }}>
      <RevealQueue initialItems={allReveals} />
    </div>
  )
}
