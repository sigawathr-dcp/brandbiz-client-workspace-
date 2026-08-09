import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

export async function GET(request: Request) {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json(null, { status: 401 })

  try {
    const url = new URL(request.url)
    const qs = url.searchParams.toString()
    const res = await fetch(
      `${BACKEND_URL}/files${qs ? '?' + qs : ''}`,
      {
        headers: { Cookie: `access_token=${token}` },
        cache: 'no-store',
      },
    )
    if (!res.ok) return NextResponse.json(null, { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json(null, { status: 502 })
  }
}
