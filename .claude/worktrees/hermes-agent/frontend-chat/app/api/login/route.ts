import { NextRequest } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

export async function POST(req: NextRequest) {
  const body = await req.json()
  const res = await fetch(`${BACKEND_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  const headers = new Headers({ 'Content-Type': 'application/json' })
  // Forward the auth cookie the backend sets
  const setCookie = res.headers.get('set-cookie')
  if (setCookie) headers.set('set-cookie', setCookie)

  return new Response(res.body, { status: res.status, headers })
}
