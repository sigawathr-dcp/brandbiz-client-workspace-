import { NextRequest } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

// BFF proxy for LINE Login — same shape as app/api/public/redeem/route.ts:
// forward the JSON body, forward the Set-Cookie the backend issues (the
// verified LINE login IS the login — see app/routers/client_public.py).
// Unauthenticated by design; this is the /try page's only backend call.
//
// The id_token is forwarded verbatim and never inspected here. It is only
// meaningful once LINE has verified it against the channel secret, which
// lives on the backend and must not reach this process.
export async function POST(req: NextRequest) {
  const body = await req.json()
  const res = await fetch(`${BACKEND_URL}/public/line/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  const headers = new Headers({ 'Content-Type': 'application/json' })
  const setCookie = res.headers.get('set-cookie')
  if (setCookie) headers.set('set-cookie', setCookie)

  return new Response(res.body, { status: res.status, headers })
}
