// Client-safe error helper for the /client/** funnel (Phase 5, D21/D22).
// The BFF routes (lib/clientBff.ts) always forward the backend's JSON body
// and status through unchanged, and substitute their own {"detail": ...}
// body where they fail first (missing cookie, backend unreachable) — so a
// `detail` string is present on every failure path. This lives outside
// clientBff.ts because that module imports next/headers and is server-only;
// this one runs in the browser, inside the useCallback handlers in
// ClientWorkspace.tsx.
export async function errorDetail(res: Response, fallback = 'Request failed'): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body?.detail === 'string') return body.detail
  } catch {
    // non-JSON body
  }
  return `${fallback} (HTTP ${res.status})`
}
