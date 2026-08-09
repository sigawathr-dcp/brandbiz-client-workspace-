import { Suspense, cache } from 'react'
import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import ConversationList from '@/components/ConversationList'
import ConsentGate from '@/components/ConsentGate'
import NavSidebar from '@/components/NavSidebar'
import PageSpinner from '@/components/ui/PageSpinner'
import ResponsiveShell from '@/components/ResponsiveShell'
import { ConversationsProvider } from '@/components/ConversationsProvider'

interface Conversation {
  id: string
  title: string | null
  updated_at: string
}

interface UserInfo {
  id: string
  email: string
  display_name: string | null
  avatar_url: string | null
  role: string
  requires_consent: boolean
  workspace_id: string | null // D21/D22 — set for a client-workspace seat
  internal_app_enabled: boolean // D23 — client seats may use this app when true
}

/**
 * Fetch from the internal backend.
 *
 * Returns the parsed JSON on success, or null on 404/other non-fatal codes.
 * Throws on network errors (ECONNREFUSED etc.) and on 401 (let the caller
 * redirect to login) so failures never silently produce a logged-out sidebar.
 */
async function fetchFromBackend<T>(
  path: string,
  token: string,
  opts: { revalidate?: number } = {},
): Promise<T | null> {
  const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000'
  // Network errors propagate — they must not be swallowed here.
  const res = await fetch(`${backendUrl}${path}`, {
    headers: { Cookie: `access_token=${token}` },
    // Cookie header is part of the fetch cache key, so this stays scoped
    // to the requesting user's session.
    ...(opts.revalidate !== undefined
      ? { next: { revalidate: opts.revalidate } }
      : { cache: 'no-store' as const }),
  })
  if (res.status === 401) {
    // Token missing or expired — hard throw so the caller can redirect.
    throw Object.assign(new Error('Unauthorized'), { status: 401 })
  }
  if (!res.ok) return null
  return res.json() as Promise<T>
}

// cache() dedupes this across the two call sites below (sidebar + content)
// so the render only makes one /auth/me request.
const getUser = cache((token: string) => fetchFromBackend<UserInfo>('/auth/me', token, { revalidate: 5 }))

export default async function ChatLayout({ children }: { children: React.ReactNode }) {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value || ''

  if (!token) {
    redirect('/login')
  }

  return (
    <ConversationsProvider>
      <ResponsiveShell
        sidebar={
          // NavSidebar's primary nav doesn't depend on user data and tolerates
          // user={null} (no footer/admin item), so it renders immediately as
          // the fallback instead of blanking the sidebar while auth + the
          // conversation list resolve.
          <Suspense fallback={<NavSidebar user={null} />}>
            <ChatSidebar token={token} />
          </Suspense>
        }
        mainStyle={{ overflow: 'hidden' }}
      >
        <Suspense fallback={<PageSpinner />}>
          <GatedMain token={token}>{children}</GatedMain>
        </Suspense>
      </ResponsiveShell>
    </ConversationsProvider>
  )
}

async function ChatSidebar({ token }: { token: string }) {
  let user: UserInfo | null = null
  let conversations: Conversation[] | null = null

  try {
    ;[conversations, user] = await Promise.all([
      // Always fresh — router.refresh() after the first prompt of a new
      // conversation relies on this fetch actually hitting the backend, not
      // a cached window, so the sidebar updates immediately and reliably.
      fetchFromBackend<Conversation[]>('/conversations', token),
      getUser(token),
    ])
  } catch (err: unknown) {
    const status = (err as { status?: number }).status
    if (status === 401) {
      redirect('/login')
    }
    throw err
  }

  return <ConversationList conversations={conversations ?? []} user={user} />
}

async function GatedMain({ token, children }: { token: string; children: React.ReactNode }) {
  let user: UserInfo | null = null

  try {
    user = await getUser(token)
  } catch (err: unknown) {
    const status = (err as { status?: number }).status
    if (status === 401) {
      redirect('/login')
    }
    // Network / 5xx: backend unreachable. Re-throw so Next.js error.tsx
    // (or the default error boundary) shows "Something went wrong" rather
    // than silently rendering ungated content.
    throw err
  }

  // D21/D22, amended by D23 — a client-workspace seat landing here (e.g. a
  // stale bookmark) belongs in its own shell UNLESS internal_app_enabled is
  // on, in which case the backend actually admits them (see app/deps.py::
  // require_internal) and this page should render normally. When the flag
  // is off, this just avoids showing them a broken, half-empty internal
  // chat page before the backend 403s every internal router.
  if (user?.workspace_id && !user.internal_app_enabled) {
    redirect('/w')
  }

  return <ConsentGate requiresConsent={user?.requires_consent ?? false}>{children}</ConsentGate>
}
