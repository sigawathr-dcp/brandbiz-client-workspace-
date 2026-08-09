import ClientDetailPage from '@/components/admin/ClientDetailPage'

export const metadata = { title: 'Client workspace — AI Gateway' }

export default async function AdminClientDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return <ClientDetailPage workspaceId={id} />
}
