import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000'

async function proxy(req: NextRequest, method: string) {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json({ error: 'Unauthenticated' }, { status: 401 })

  const body = method !== 'GET' ? await req.text() : undefined
  const res = await fetch(`${BACKEND}/admin/permissions/department`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body,
    cache: 'no-store',
  })
  const text = await res.text()
  return new NextResponse(text, {
    status: res.status,
    headers: { 'Content-Type': 'application/json' },
  })
}

export async function GET(req: NextRequest) { return proxy(req, 'GET') }
export async function PUT(req: NextRequest) { return proxy(req, 'PUT') }
