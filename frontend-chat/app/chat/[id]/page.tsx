import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import ChatPane from '@/components/ChatPane'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  model_used: string | null
  created_at: string
}

interface ConversationDetail {
  id: string
  title: string | null
  agent_id: string | null
  messages: Message[]
}

export default async function ChatPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const cookieStore = await cookies()
  const token = cookieStore.get('access_token')?.value

  if (!token) {
    redirect('/login')
  }

  const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000'
  const res = await fetch(`${backendUrl}/conversations/${id}`, {
    headers: { Cookie: `access_token=${token}` },
    cache: 'no-store',
  })

  if (!res.ok) {
    redirect('/chat')
  }

  const data: ConversationDetail = await res.json()

  return (
    <ChatPane
      conversationId={id}
      initialMessages={data.messages.map(m => ({
        role: m.role,
        content: m.content,
        // Thread persisted model so the badge shows on page reload.
        // Downgrade reason isn't stored per-message, so only the label shows for history.
        model: m.model_used ?? undefined,
      }))}
      initialAgentId={data.agent_id ?? null}
    />
  )
}
