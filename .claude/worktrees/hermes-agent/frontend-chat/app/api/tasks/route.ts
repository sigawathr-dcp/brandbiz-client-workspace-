import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

export async function GET() {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json([], { status: 401 })

  try {
    const res = await fetch(`${BACKEND_URL}/tasks`, {
      headers: { Cookie: `access_token=${token}` },
      cache: 'no-store',
    })
    if (!res.ok) return NextResponse.json([], { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json([], { status: 502 })
  }
}

export async function POST(req: NextRequest) {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json({ detail: 'Not authenticated' }, { status: 401 })

  try {
    const body = await req.json()
    const res = await fetch(`${BACKEND_URL}/tasks`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Cookie: `access_token=${token}`,
      },
      body: JSON.stringify(body),
    })
    // Read as text first so a non-JSON error body (e.g. Starlette 500 HTML/text)
    // doesn't throw and collapse into the misleading "Backend unreachable" message.
    const text = await res.text()
    let data: unknown
    try { data = JSON.parse(text) } catch { data = { detail: text } }
    return NextResponse.json(data, { status: res.status })
  } catch {
    return NextResponse.json({ detail: 'Backend unreachable' }, { status: 502 })
  }
}
