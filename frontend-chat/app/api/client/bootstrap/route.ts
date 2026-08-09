import { NextRequest } from 'next/server'
import { proxyJson } from '@/lib/clientBff'

export async function GET(req: NextRequest) {
  return proxyJson('/client/bootstrap', 'GET', req)
}
