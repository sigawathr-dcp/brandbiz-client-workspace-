import { NextRequest } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

// Client Workspaces (Phase 5, D21/D22) — BFF proxy for the invite-redemption
// entry point. Same shape as app/api/login/route.ts: forward the JSON body,
// forward the Set-Cookie the backend issues (the redeemed invite IS the
// login — see app/routers/client_public.py). Unauthenticated by design;
// this is the /try/[token] page's only backend call.
export async function POST(req: NextRequest) {
  const body = await req.json()
  const res = await fetch(`${BACKEND_URL}/public/redeem`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  const headers = new Headers({ 'Content-Type': 'application/json' })
  const setCookie = res.headers.get('set-cookie')
  if (setCookie) headers.set('set-cookie', setCookie)

  return new Response(res.body, { status: res.status, headers })
}
