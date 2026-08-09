import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export function middleware(request: NextRequest) {
  const token = request.cookies.get('access_token')?.value
  const { pathname } = request.nextUrl

  // Client Workspaces (Phase 5, D21/D22): /try/<token> redeems an invite
  // into a fresh session, so it must be reachable with no cookie at all —
  // same reasoning as /login. /p/<token> (Phase 6) is a public read-only
  // plan share link. Neither goes through the token-required gate below.
  if (pathname.startsWith('/try/') || pathname.startsWith('/p/')) {
    return NextResponse.next()
  }

  if (!token && pathname !== '/login') {
    return NextResponse.redirect(new URL('/login', request.url))
  }

  if (token && pathname === '/login') {
    // Everyone previews the client workspace first — see app/login/page.tsx.
    return NextResponse.redirect(new URL('/w', request.url))
  }

  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
}
