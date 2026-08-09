import { Suspense, cache } from 'react'
import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import NavSidebar from '@/components/NavSidebar'
import PageSpinner from '@/components/ui/PageSpinner'

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000'

interface UserInfo {
  id: string
  email: string
  display_name: string | null
  avatar_url: string | null
  role: string
  requires_consent: boolean
}

// cache() dedupes this across the two call sites below (sidebar + content)
// so the render only makes one /auth/me request.
const getUser = cache(async (token: string): Promise<UserInfo | null> => {
  try {
    const res = await fetch(`${BACKEND}/auth/me`, {
      headers: { Cookie: `access_token=${token}` },
      // Short revalidate window — avoids a live backend round-trip on every
      // sidebar tab click. Cookie header is part of the fetch cache key, so
      // this stays scoped to the requesting user's session.
      next: { revalidate: 5 },
    })
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
})

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) redirect('/login')

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {/* NavSidebar's primary nav doesn't depend on user data and tolerates
          user={null} (no footer/admin item), so it renders immediately as
          the fallback instead of blanking the sidebar while auth resolves. */}
      <Suspense fallback={<NavSidebar user={null} />}>
        <AuthedSidebar token={token} />
      </Suspense>
      <main style={{ flex: 1, overflow: 'auto', minWidth: 0 }}>
        <Suspense fallback={<PageSpinner />}>
          <GatedContent token={token}>{children}</GatedContent>
        </Suspense>
      </main>
    </div>
  )
}

async function AuthedSidebar({ token }: { token: string }) {
  const user = await getUser(token)
  if (!user) redirect('/login')
  if (user.role !== 'ADMIN') redirect('/chat')
  return <NavSidebar user={user} />
}

async function GatedContent({ token, children }: { token: string; children: React.ReactNode }) {
  const user = await getUser(token)
  if (!user) redirect('/login')
  if (user.role !== 'ADMIN') redirect('/chat')
  return <>{children}</>
}
