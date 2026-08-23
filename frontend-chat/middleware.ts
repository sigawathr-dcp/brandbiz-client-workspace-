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

  // Redirect off request.nextUrl, NOT request.url. In Docker the Next server
  // binds 0.0.0.0:3000, and request.url carries that internal origin — so
  // `new URL('/login', request.url)` sent the browser to
  // http://0.0.0.0:3000/login, which is not a routable address
  // (ERR_ADDRESS_INVALID). nextUrl is derived from the incoming Host header,
  // so cloning it keeps the origin the browser actually used (localhost:3100).
  if (!token && pathname !== '/login') {
    const url = request.nextUrl.clone()
    url.pathname = '/login'
    return NextResponse.redirect(url)
  }

  if (token && pathname === '/login') {
    // Everyone previews the client workspace first — see app/login/page.tsx.
    const url = request.nextUrl.clone()
    url.pathname = '/w'
    return NextResponse.redirect(url)
  }

  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
}
