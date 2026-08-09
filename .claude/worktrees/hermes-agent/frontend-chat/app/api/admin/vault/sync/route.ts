/**
 * BFF proxy for POST /admin/vault/sync (trigger a sync run).
 */
import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000'

export async function POST(req: NextRequest) {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json({ error: 'Unauthenticated' }, { status: 401 })

  const body = await req.text()
  const res = await fetch(`${BACKEND}/admin/vault/sync`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: body || '{}',
    cache: 'no-store',
  })
  const respBody = await res.text()
  return new NextResponse(respBody, { status: res.status, headers: { 'Content-Type': 'application/json' } })
}
