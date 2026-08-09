import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

// Client Workspaces admin screens (Phase 5/6, D21/D22) — shared proxy body
// for /api/admin/clients/** BFF routes. Same cookie-forwarding contract as
// lib/clientBff.ts and every other route in app/api/**.
export async function adminProxy(
  backendPath: string,
  method: 'GET' | 'POST' | 'PUT' | 'PATCH',
  req: NextRequest
): Promise<NextResponse> {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json({ detail: 'Unauthorized' }, { status: 401 })

  try {
    const res = await fetch(`${BACKEND_URL}${backendPath}`, {
      method,
      headers: {
        Cookie: `access_token=${token}`,
        ...(method !== 'GET' ? { 'Content-Type': 'application/json' } : {}),
      },
      body: method !== 'GET' ? await req.text() : undefined,
      cache: 'no-store',
    })
    if (res.status === 204) return new NextResponse(null, { status: 204 })
    const text = await res.text()
    try {
      return NextResponse.json(JSON.parse(text), { status: res.status })
    } catch {
      return new NextResponse(text, { status: res.status }) as unknown as NextResponse
    }
  } catch {
    return NextResponse.json({ detail: 'Backend unavailable' }, { status: 502 })
  }
}
