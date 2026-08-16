import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'

// Shared target for every protected layout's "backend says this token is
// invalid" branch (app/(admin|client)/layout.tsx, app/{agent,chat,library,
// skills,studio,tasks}/layout.tsx). A plain `redirect('/login')` from a
// Server Component can't touch cookies — next/headers only allows
// cookies().set()/delete() from a Server Action or Route Handler — so a
// stale/expired access_token cookie survived the redirect. middleware.ts
// only checks whether the cookie is PRESENT (not whether the backend still
// considers it valid) and bounces any token-bearing /login visit straight
// back to /w, so the two disagreed forever: protected route -> 401 ->
// /login -> cookie still present -> /w -> 401 -> /login -> ...
// (ERR_TOO_MANY_REDIRECTS). Routing here first clears the cookie so the
// next request has none, and middleware's `!token` branch takes over
// correctly.
export async function GET(req: NextRequest) {
  const cookieStore = await cookies()
  cookieStore.delete('access_token')
  return NextResponse.redirect(new URL('/login', req.url))
}
