import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

export async function POST() {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json({ detail: 'Not authenticated' }, { status: 401 })

  try {
    const res = await fetch(`${BACKEND_URL}/hermes/host-jobs`, {
      method: 'POST',
      headers: { Cookie: `access_token=${token}` },
      cache: 'no-store',
    })
    const text = await res.text()
    let data: unknown
    try { data = JSON.parse(text) } catch { data = { detail: text } }
    return NextResponse.json(data, { status: res.status })
  } catch {
    return NextResponse.json({ detail: 'Backend unreachable' }, { status: 502 })
  }
}
