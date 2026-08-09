'use client'

import { createContext, useCallback, useContext, useMemo, useState } from 'react'

export interface Conversation {
  id: string
  title: string | null
  updated_at: string
}

interface ConversationsContextValue {
  optimistic: Conversation[]
  addOptimistic: (conv: Conversation) => void
  removeOptimistic: (id: string) => void
}

const ConversationsContext = createContext<ConversationsContextValue | null>(null)

export function ConversationsProvider({ children }: { children: React.ReactNode }) {
  const [optimistic, setOptimistic] = useState<Conversation[]>([])

  const addOptimistic = useCallback((conv: Conversation) => {
    setOptimistic(prev => prev.some(c => c.id === conv.id) ? prev : [conv, ...prev])
  }, [])

  const removeOptimistic = useCallback((id: string) => {
    setOptimistic(prev => prev.filter(c => c.id !== id))
  }, [])

  const value = useMemo(
    () => ({ optimistic, addOptimistic, removeOptimistic }),
    [optimistic, addOptimistic, removeOptimistic],
  )

  return (
    <ConversationsContext.Provider value={value}>
      {children}
    </ConversationsContext.Provider>
  )
}

export function useConversations(): ConversationsContextValue {
  const ctx = useContext(ConversationsContext)
  if (!ctx) throw new Error('useConversations must be used within a ConversationsProvider')
  return ctx
}
