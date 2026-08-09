import { cookies } from 'next/headers'
import { NextRequest } from 'next/server'

export async function PATCH(req: NextRequest) {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value

  if (!token) {
    return new Response('Unauthorized', { status: 401 })
  }

  const body = await req.json()
  const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000'

  const res = await fetch(`${backendUrl}/auth/me/preferences`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Cookie: `access_token=${token}`,
    },
    body: JSON.stringify(body),
  })

  return new Response(res.body, {
    status: res.status,
    headers: { 'Content-Type': 'application/json' },
  })
}
