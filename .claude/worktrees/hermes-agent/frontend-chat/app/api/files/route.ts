/**
 * BFF proxy for GET /files (list) and POST /files (upload).
 * Mirrors the pattern from app/api/chat/route.ts — reads the httpOnly
 * access_token cookie and forwards to the backend.
 */
import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000'

export async function GET(_req: NextRequest) {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json({ error: 'Unauthenticated' }, { status: 401 })

  const res = await fetch(`${BACKEND}/files`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store',
  })
  const body = await res.text()
  return new NextResponse(body, {
    status: res.status,
    headers: { 'Content-Type': 'application/json' },
  })
}

export async function POST(req: NextRequest) {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json({ error: 'Unauthenticated' }, { status: 401 })

  // Forward the multipart form-data as-is.
  const formData = await req.formData()
  const res = await fetch(`${BACKEND}/files`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  })
  const body = await res.text()
  return new NextResponse(body, {
    status: res.status,
    headers: { 'Content-Type': 'application/json' },
  })
}
