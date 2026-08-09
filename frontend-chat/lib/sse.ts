// Shared Server-Sent Events reader for the hand-rolled `data: {json}\n\n` protocol
// emitted by the backend chat endpoints (POST /chat, POST /client/chat, POST
// /chat/arena). Extracted from the identical loops that used to live inline in
// ChatPane.tsx and ClientWorkspace.tsx — behavior is unchanged, only the
// duplication is gone.

export interface SSEEvent {
  type: string
  branch?: 'a' | 'b'
  [key: string]: unknown
}

/**
 * Read a fetch Response body as a stream of SSE events. Malformed `data:` lines
 * are silently skipped (matches prior behavior in both call sites) rather than
 * aborting the whole stream.
 */
export async function* readSSE(res: Response): AsyncGenerator<SSEEvent> {
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        yield JSON.parse(line.slice(6)) as SSEEvent
      } catch {
        // ignore malformed SSE
      }
    }
  }
}
