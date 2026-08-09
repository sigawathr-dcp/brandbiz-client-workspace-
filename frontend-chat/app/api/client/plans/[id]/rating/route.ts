import { NextRequest } from 'next/server'
import { proxyJson } from '@/lib/clientBff'

export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return proxyJson(`/client/plans/${id}/rating`, 'POST', req)
}
