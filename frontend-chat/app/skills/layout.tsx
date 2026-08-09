import { Suspense, cache } from 'react'
import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import NavSidebar from '@/components/NavSidebar'
import ConsentGate from '@/components/ConsentGate'
import PageSpinner from '@/components/ui/PageSpinner'
import ResponsiveShell from '@/components/ResponsiveShell'

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000'

interface UserInfo {
  id: string
  email: string
  display_name: string | null
  avatar_url: string | null
  role: string
  requires_consent: boolean
  workspace_id: string | null // D23 — set for a client-workspace seat
  internal_app_enabled: boolean // D23 — client seats may use this app when true
}

// cache() dedupes this across the two call sites below (sidebar + content)
// so the render only makes one /auth/me request.
const getUser = cache(async (token: string): Promise<UserInfo | null> => {
  try {
    const res = await fetch(`${BACKEND}/auth/me`, {
      headers: { Cookie: `access_token=${token}` },
      next: { revalidate: 5 },
    })
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
})

export default async function SkillsLayout({ children }: { children: React.ReactNode }) {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) redirect('/login')

  return (
    <ResponsiveShell
      sidebar={
        <Suspense fallback={<NavSidebar user={null} />}>
          <AuthedSidebar token={token} />
        </Suspense>
      }
      mainStyle={{ overflow: 'auto' }}
    >
      <Suspense fallback={<PageSpinner />}>
        <GatedContent token={token}>{children}</GatedContent>
      </Suspense>
    </ResponsiveShell>
  )
}

async function AuthedSidebar({ token }: { token: string }) {
  const user = await getUser(token)
  if (!user) redirect('/login')
  return <NavSidebar user={user} />
}

async function GatedContent({ token, children }: { token: string; children: React.ReactNode }) {
  const user = await getUser(token)
  if (!user) redirect('/login')
  // D21/D22, amended by D23 — this layout had no workspace check before
  // D23, so a client seat could already reach a full internal shell over
  // panes that all 403'd. Redirect to /w unless internal_app_enabled lets
  // the backend actually serve this page — mirrors app/chat/layout.tsx.
  if (user.workspace_id && !user.internal_app_enabled) redirect('/w')
  return <ConsentGate requiresConsent={user.requires_consent}>{children}</ConsentGate>
}
