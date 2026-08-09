/**
 * BFF proxy for GET/PUT /admin/vault/config.
 */
import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000'

export async function GET() {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json({ error: 'Unauthenticated' }, { status: 401 })

  const res = await fetch(`${BACKEND}/admin/vault/config`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store',
  })
  const body = await res.text()
  return new NextResponse(body, { status: res.status, headers: { 'Content-Type': 'application/json' } })
}

export async function PUT(req: NextRequest) {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json({ error: 'Unauthenticated' }, { status: 401 })

  const body = await req.text()
  const res = await fetch(`${BACKEND}/admin/vault/config`, {
    method: 'PUT',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body,
    cache: 'no-store',
  })
  const respBody = await res.text()
  return new NextResponse(respBody, { status: res.status, headers: { 'Content-Type': 'application/json' } })
}
