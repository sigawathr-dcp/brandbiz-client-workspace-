import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

// DB redesign — server-side replacement for the old `bb:activePlan:*`
// localStorage key (Task 5.12): the plan switcher calls this when the
// client picks a different plan as "active" (what a revision targets).
export async function POST(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value
  if (!token) return NextResponse.json({ detail: 'Unauthorized' }, { status: 401 })

  const res = await fetch(`${BACKEND_URL}/client/plans/${id}/activate`, {
    method: 'POST',
    headers: { Cookie: `access_token=${token}` },
  })
  const text = await res.text()
  try {
    return NextResponse.json(JSON.parse(text), { status: res.status })
  } catch {
    return new NextResponse(text, { status: res.status })
  }
}
