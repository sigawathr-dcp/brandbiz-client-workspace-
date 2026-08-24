import { Suspense, cache } from 'react'
import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import NavSidebar from '@/components/NavSidebar'
import ConsentGate from '@/components/ConsentGate'
import PageSpinner from '@/components/ui/PageSpinner'
import ResponsiveShell from '@/components/ResponsiveShell'
import { canUseTasks } from '@/lib/domain'

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

export default async function TasksLayout({ children }: { children: React.ReactNode }) {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) redirect('/login')

  return (
    <ResponsiveShell
      sidebar={
        // NavSidebar's primary nav doesn't depend on user data and tolerates
        // user={null} (no footer/admin item), so it renders immediately as
        // the fallback instead of blanking the sidebar while auth resolves.
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
  // Token was present but the backend rejected it (expired/stale) — route
  // through /api/session-expired to clear the cookie first, or
  // middleware.ts (which only checks cookie presence) bounces straight
  // back here forever. See that route's comment for the full loop.
  if (!user) redirect('/api/session-expired')
  // Hermes (and therefore Tasks) defaults to L5/L6/ADMIN — see
  // 0030_hermes_model_catalog.py. Hiding the page for everyone else avoids
  // showing a form whose only possible outcome is a 403 on submit.
  if (!canUseTasks(user.role)) redirect('/chat')
  return <NavSidebar user={user} />
}

async function GatedContent({ token, children }: { token: string; children: React.ReactNode }) {
  const user = await getUser(token)
  // Token was present but the backend rejected it (expired/stale) — route
  // through /api/session-expired to clear the cookie first, or
  // middleware.ts (which only checks cookie presence) bounces straight
  // back here forever. See that route's comment for the full loop.
  if (!user) redirect('/api/session-expired')
  if (!canUseTasks(user.role)) redirect('/chat')
  // D21/D22, amended by D23 — belt-and-suspenders alongside canUseTasks:
  // every client seat is role=L1 (redeem_invite hardcodes it), so
  // canUseTasks already redirects them above regardless of D23. Kept for
  // the same reason as the other internal-app layouts — coherent flag-off
  // behavior, no further change needed when internal_app_enabled flips.
  if (user.workspace_id && !user.internal_app_enabled) redirect('/w')
  return <ConsentGate requiresConsent={user.requires_consent}>{children}</ConsentGate>
}
