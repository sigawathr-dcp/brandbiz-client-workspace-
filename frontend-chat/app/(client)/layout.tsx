import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

// Client Workspaces (Phase 5, D21/D22) — the client-only route group. This
// shell is deliberately NOT ResponsiveShell/NavSidebar (the design has its
// own top bar + nav rail, see components/client/ClientWorkspace.tsx); its
// only job is the auth guard: unauthenticated -> /login (no self-serve
// entry exists — a real seat always arrives via /try/<token>).
//
// Internal staff (workspace_id === null) are let THROUGH, not bounced to
// /chat: everyone lands here right after login and previews the demo
// workspace (backend: app/deps.py::require_client_context) before
// stepping into their own tools via the "Continue to internal app" link
// ClientWorkspace.tsx renders when GET /client/bootstrap reports
// is_preview. A real client seat still can't reach /chat at all
// (app/chat/layout.tsx redirects them back here) — this only removes the
// reverse block for staff.
interface UserInfo {
  workspace_id: string | null
}

async function getUser(token: string): Promise<UserInfo | null> {
  const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000'
  const res = await fetch(`${backendUrl}/auth/me`, {
    headers: { Cookie: `access_token=${token}` },
    cache: 'no-store',
  })
  if (!res.ok) return null
  return res.json()
}

export default async function ClientLayout({ children }: { children: React.ReactNode }) {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value

  if (!token) {
    redirect('/login')
  }

  const user = await getUser(token)
  if (!user) {
    redirect('/login')
  }

  return <>{children}</>
}
