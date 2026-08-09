import type { Metadata } from 'next'
import ChatSearch from '@/components/ChatSearch'

export const metadata: Metadata = { title: 'Search chats' }

export default function SearchPage() {
  return <ChatSearch />
}
