// Client-side API helpers (browser → Next.js API routes → FastAPI backend)
// All auth is handled via the httpOnly access_token cookie forwarded by the proxy routes.

export interface Conversation {
  id: string
  title: string | null
  created_at: string
  updated_at: string
}

export async function fetchConversations(
  opts: { q?: string; limit?: number; signal?: AbortSignal } = {},
): Promise<Conversation[]> {
  const params = new URLSearchParams()
  if (opts.q) params.set('q', opts.q)
  if (opts.limit) params.set('limit', String(opts.limit))
  const qs = params.toString()
  const res = await fetch(`/api/conversations${qs ? `?${qs}` : ''}`, { signal: opts.signal })
  if (!res.ok) return []
  return res.json()
}
