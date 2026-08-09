import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'


export async function POST() {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) {
    return NextResponse.json({ detail: 'Not authenticated' }, { status: 401 })
  }

  const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000'
  const res = await fetch(`${backendUrl}/auth/acknowledge-consent`, {
    method: 'POST',
    headers: { Cookie: `access_token=${token}` },
  })

  const body = await res.json()
  return NextResponse.json(body, { status: res.status })
}
