/**
 * BFF proxy for GET /admin/vault/sync/latest (most recent run, or null).
 * Registered as a static segment — Next.js resolves it ahead of the
 * dynamic [runId] route, same as FastAPI's /admin/vault/sync/latest
 * being registered ahead of /admin/vault/sync/{run_id} on the backend.
 */
import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000'

export async function GET() {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json({ error: 'Unauthenticated' }, { status: 401 })

  const res = await fetch(`${BACKEND}/admin/vault/sync/latest`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store',
  })
  const body = await res.text()
  return new NextResponse(body, { status: res.status, headers: { 'Content-Type': 'application/json' } })
}
