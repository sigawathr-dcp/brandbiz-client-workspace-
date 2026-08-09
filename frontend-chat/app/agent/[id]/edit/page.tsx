'use client'

import { use } from 'react'
import CreateAgentForm from '@/components/agent/CreateAgentForm'

export default function EditAgentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  return <CreateAgentForm agentId={id} />
}
