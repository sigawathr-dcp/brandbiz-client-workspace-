import { NextRequest } from 'next/server'
import { proxyJson } from '@/lib/clientBff'

export async function POST(req: NextRequest) {
  return proxyJson('/client/cases', 'POST', req)
}
