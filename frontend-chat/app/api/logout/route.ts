import { cookies } from 'next/headers'

export async function POST() {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value

  if (token) {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000'
    await fetch(`${backendUrl}/auth/logout`, {
      method: 'POST',
      headers: { Cookie: `access_token=${token}` },
    }).catch(() => {})
  }

  const response = new Response(JSON.stringify({ status: 'ok' }), {
    headers: { 'Content-Type': 'application/json' },
  })
  // Clear the cookie on the Next.js side too
  cookieStore.delete('access_token')
  return response
}
