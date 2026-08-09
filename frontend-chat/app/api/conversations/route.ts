import { cookies } from 'next/headers'
import type { NextRequest } from 'next/server'

export async function GET(request: NextRequest) {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value

  if (!token) {
    return new Response('Unauthorized', { status: 401 })
  }

  const params = new URLSearchParams()
  const q = request.nextUrl.searchParams.get('q')
  const limit = request.nextUrl.searchParams.get('limit')
  if (q) params.set('q', q)
  if (limit) params.set('limit', limit)
  const qs = params.toString()

  const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000'
  const res = await fetch(`${backendUrl}/conversations${qs ? `?${qs}` : ''}`, {
    headers: { Cookie: `access_token=${token}` },
    cache: 'no-store',
  })

  return new Response(res.body, {
    status: res.status,
    headers: { 'Content-Type': 'application/json' },
  })
}
