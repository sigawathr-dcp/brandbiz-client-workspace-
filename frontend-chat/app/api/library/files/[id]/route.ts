import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json(null, { status: 401 })

  const { id } = await params

  try {
    const res = await fetch(`${BACKEND_URL}/files/${id}`, {
      method: 'DELETE',
      headers: { Cookie: `access_token=${token}` },
    })
    if (res.status === 204) return new NextResponse(null, { status: 204 })
    return NextResponse.json(null, { status: res.status })
  } catch {
    return NextResponse.json(null, { status: 502 })
  }
}
