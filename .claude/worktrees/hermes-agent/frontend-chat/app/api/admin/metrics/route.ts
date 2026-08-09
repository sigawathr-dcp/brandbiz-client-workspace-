import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000'

export async function GET(req: NextRequest) {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json({ error: 'Unauthenticated' }, { status: 401 })

  const search = req.nextUrl.searchParams.toString()
  const res = await fetch(`${BACKEND}/admin/metrics${search ? `?${search}` : ''}`, {
    headers: { Authorization: `Bearer ${token}` }, cache: 'no-store',
  })
  const body = await res.text()
  return new NextResponse(body, { status: res.status, headers: { 'Content-Type': 'application/json' } })
}
