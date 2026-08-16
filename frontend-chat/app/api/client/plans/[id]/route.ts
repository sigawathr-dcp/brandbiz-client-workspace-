import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'
import { proxyJson } from '@/lib/clientBff'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

// Task 5.11 — save a re-drafted plan over an existing one (profile edit ->
// resubmit -> plan v2+). See app/routers/client.py::revise_plan.
export async function PUT(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return proxyJson(`/client/plans/${id}`, 'PUT', req)
}

export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json({ detail: 'Unauthorized' }, { status: 401 })

  try {
    const res = await fetch(`${BACKEND_URL}/client/plans/${id}`, {
      headers: { Cookie: `access_token=${token}` },
      cache: 'no-store',
    })
    const text = await res.text()
    try {
      return NextResponse.json(JSON.parse(text), { status: res.status })
    } catch {
      return new NextResponse(text, { status: res.status })
    }
  } catch {
    return NextResponse.json({ detail: 'Backend unavailable' }, { status: 502 })
  }
}
