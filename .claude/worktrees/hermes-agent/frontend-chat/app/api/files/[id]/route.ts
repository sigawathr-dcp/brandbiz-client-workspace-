/**
 * BFF proxy for GET /files/{id} (status poll) and DELETE /files/{id}.
 */
import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000'

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json({ error: 'Unauthenticated' }, { status: 401 })

  const res = await fetch(`${BACKEND}/files/${id}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store',
  })
  const body = await res.text()
  return new NextResponse(body, {
    status: res.status,
    headers: { 'Content-Type': 'application/json' },
  })
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json({ error: 'Unauthenticated' }, { status: 401 })

  const res = await fetch(`${BACKEND}/files/${id}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  })
  // 204 No Content — return empty body
  return new NextResponse(null, { status: res.status })
}
