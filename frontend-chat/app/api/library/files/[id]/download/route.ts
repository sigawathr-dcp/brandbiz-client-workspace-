import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return new NextResponse(null, { status: 401 })

  const { id } = await params

  try {
    const res = await fetch(`${BACKEND_URL}/files/${id}/download`, {
      headers: { Cookie: `access_token=${token}` },
      cache: 'no-store',
    })
    if (!res.ok) return new NextResponse(null, { status: res.status })

    // Forward Content-Type and Content-Disposition from the backend
    const headers = new Headers()
    const ct = res.headers.get('content-type')
    const cd = res.headers.get('content-disposition')
    if (ct) headers.set('content-type', ct)
    if (cd) headers.set('content-disposition', cd)

    return new NextResponse(res.body, { status: 200, headers })
  } catch {
    return new NextResponse(null, { status: 502 })
  }
}
