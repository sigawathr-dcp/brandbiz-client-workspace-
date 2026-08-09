import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000'

export async function GET(req: NextRequest) {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json({ error: 'Unauthenticated' }, { status: 401 })

  const search = req.nextUrl.searchParams.toString()
  const res = await fetch(`${BACKEND}/admin/reveals${search ? `?${search}` : ''}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store',
  })
  const body = await res.text()
  return new NextResponse(body, { status: res.status, headers: { 'Content-Type': 'application/json' } })
}

export async function POST(req: NextRequest) {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json({ error: 'Unauthenticated' }, { status: 401 })

  const body = await req.text()
  const res = await fetch(`${BACKEND}/reveal`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body,
    cache: 'no-store',
  })
  const resBody = await res.text()
  return new NextResponse(resBody, { status: res.status, headers: { 'Content-Type': 'application/json' } })
}
