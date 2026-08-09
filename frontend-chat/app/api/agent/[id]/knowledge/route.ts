import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

async function getToken() {
  const cookieStore = await cookies()
  return cookieStore.get('access_token')?.value
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const token = await getToken()
  if (!token) return NextResponse.json({ detail: 'Unauthorized' }, { status: 401 })
  const { id } = await params
  try {
    const body = await req.text()
    const res = await fetch(`${BACKEND_URL}/agents/${id}/knowledge`, {
      method: 'POST',
      headers: {
        Cookie: `access_token=${token}`,
        'Content-Type': 'application/json',
      },
      body,
      cache: 'no-store',
    })
    if (res.status === 204) return new NextResponse(null, { status: 204 })
    const text = await res.text()
    try {
      return NextResponse.json(JSON.parse(text), { status: res.status })
    } catch {
      return new NextResponse(text, { status: res.status })
    }
  } catch {
    return NextResponse.json({ detail: 'Backend unavailable' }, { status: 502 })
  }
}
