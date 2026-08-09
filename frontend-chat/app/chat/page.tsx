import ChatPane from '@/components/ChatPane'

export default async function NewChatPage({
  searchParams,
}: {
  searchParams: Promise<{ agent?: string }>
}) {
  const params = await searchParams
  return (
    <ChatPane
      conversationId={null}
      initialMessages={[]}
      initialAgentId={params.agent ?? null}
    />
  )
}
