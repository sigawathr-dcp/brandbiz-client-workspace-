import { cookies } from 'next/headers'
import { NextRequest } from 'next/server'

export async function POST(req: NextRequest) {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value

  if (!token) {
    return new Response('Unauthorized', { status: 401 })
  }

  const body = await req.json()
  const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000'

  const backendRes = await fetch(`${backendUrl}/chat`, {
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

  // Stream SSE directly to the browser
  return new Response(backendRes.body, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'X-Accel-Buffering': 'no',
    },
  })
}
