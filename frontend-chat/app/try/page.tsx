import LineLogin from '@/components/client/LineLogin'

export const metadata = { title: 'Brandbiz — sign in with LINE' }

// Read LINE_LIFF_ID at REQUEST time, not build time.
//
// Without this, Next statically prerenders this page during `next build`
// (it uses no dynamic API, so it is eligible), evaluates process.env then —
// when the compose `environment:` block has not been applied yet — and bakes
// the empty string into the prerendered output forever. The page then always
// renders the "not configured" state no matter what the container's env says.
//
// This is the same build-vs-runtime trap as NEXT_PUBLIC_*, which is why the
// LIFF id is not exposed that way either: avoiding NEXT_PUBLIC only moves the
// read to the server, it does not by itself make the read happen per request.
export const dynamic = 'force-dynamic'

// The LIFF app's endpoint URL points here. /try/[token] (invite redemption)
// still exists as the break-glass path — see app/routers/client_public.py.
export default function TryPage() {
  return <LineLogin liffId={process.env.LINE_LIFF_ID ?? ''} />
}
