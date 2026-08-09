import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

export async function GET() {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json({ detail: 'Not authenticated' }, { status: 401 })

  try {
    const res = await fetch(`${BACKEND_URL}/hermes/helper-script`, {
      headers: { Cookie: `access_token=${token}` },
      cache: 'no-store',
    })
    const text = await res.text()
    if (!res.ok) {
      let data: unknown
      try { data = JSON.parse(text) } catch { data = { detail: text } }
      return NextResponse.json(data, { status: res.status })
    }
    return new NextResponse(text, {
      status: 200,
      headers: {
        'Content-Type': 'text/plain; charset=utf-8',
        'Content-Disposition': 'attachment; filename="install-helper.cmd"',
      },
    })
  } catch {
    return NextResponse.json({ detail: 'Backend unreachable' }, { status: 502 })
  }
}
