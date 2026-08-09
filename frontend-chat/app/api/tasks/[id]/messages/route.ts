import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json({ detail: 'Not authenticated' }, { status: 401 })

  const { id } = await params
  try {
    const body = await req.json()
    const res = await fetch(`${BACKEND_URL}/tasks/${id}/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Cookie: `access_token=${token}`,
      },
      body: JSON.stringify(body),
    })
    const text = await res.text()
    let data: unknown
    try { data = JSON.parse(text) } catch { data = { detail: text } }
    return NextResponse.json(data, { status: res.status })
  } catch {
    return NextResponse.json({ detail: 'Backend unreachable' }, { status: 502 })
  }
}
