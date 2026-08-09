import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

export async function GET() {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json(null, { status: 401 })

  try {
    const res = await fetch(`${BACKEND_URL}/studio/generations`, {
      headers: { Cookie: `access_token=${token}` },
      cache: 'no-store',
    })
    if (!res.ok) return NextResponse.json(null, { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json(null, { status: 502 })
  }
}
