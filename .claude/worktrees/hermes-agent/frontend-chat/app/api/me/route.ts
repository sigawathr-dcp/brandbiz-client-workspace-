import { cookies } from 'next/headers'

export async function GET() {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value

  if (!token) {
    return new Response('Unauthorized', { status: 401 })
  }

  const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000'
  const res = await fetch(`${backendUrl}/auth/me`, {
    headers: { Cookie: `access_token=${token}` },
    cache: 'no-store',
  })

  return new Response(res.body, {
    status: res.status,
    headers: { 'Content-Type': 'application/json' },
  })
}
