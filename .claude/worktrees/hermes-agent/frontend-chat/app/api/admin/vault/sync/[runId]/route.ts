/**
 * BFF proxy for GET /admin/vault/sync/{runId} (poll one run's status).
 */
import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000'

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ runId: string }> },
) {
  const { runId } = await params
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json({ error: 'Unauthenticated' }, { status: 401 })

  const res = await fetch(`${BACKEND}/admin/vault/sync/${runId}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store',
  })
  const body = await res.text()
  return new NextResponse(body, { status: res.status, headers: { 'Content-Type': 'application/json' } })
}
