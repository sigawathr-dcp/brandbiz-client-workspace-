import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

// Client Workspaces (Phase 5/6, D21/D22) — unauthenticated proxy for a
// plan's share link. No cookie involved by design; the token itself is the
// credential (mirrors /api/public/redeem's unauthenticated shape).
export async function GET(_req: NextRequest, { params }: { params: Promise<{ token: string }> }) {
  const { token } = await params
  try {
    const res = await fetch(`${BACKEND_URL}/public/plans/${token}`, { cache: 'no-store' })
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
