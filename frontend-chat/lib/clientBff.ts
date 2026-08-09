import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

// Client Workspaces (Phase 5, D21/D22) — shared JSON-proxy body for the
// /api/client/** BFF routes. Same cookie-forwarding contract as every other
// route in app/api/**: read the httpOnly access_token cookie server-side,
// re-attach it as a Cookie header on the backend call (never exposed to the
// browser as a Bearer token — see frontend-chat's auth notes).
export async function proxyJson(
  backendPath: string,
  method: 'GET' | 'POST',
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
        ...(method === 'POST' ? { 'Content-Type': 'application/json' } : {}),
      },
      body: method === 'POST' ? await req.text() : undefined,
      cache: 'no-store',
    })
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
