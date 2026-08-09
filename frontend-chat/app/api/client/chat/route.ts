import { cookies } from 'next/headers'
import { NextRequest } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

// Mirrors app/api/chat/route.ts exactly, targeting /client/chat instead of
// /chat — same SSE passthrough contract (see components/ChatPane.tsx's
// parser, reused as-is by components/client/ClientWorkspace.tsx).
export async function POST(req: NextRequest) {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return new Response('Unauthorized', { status: 401 })

  const body = await req.json()

  const backendRes = await fetch(`${BACKEND_URL}/client/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Cookie: `access_token=${token}`,
    },
    body: JSON.stringify(body),
  })

  if (!backendRes.ok) {
    return new Response(await backendRes.text(), { status: backendRes.status })
  }

  return new Response(backendRes.body, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'X-Accel-Buffering': 'no',
    },
  })
}
