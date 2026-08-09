import { NextRequest } from 'next/server'
import { proxyJson } from '@/lib/clientBff'

export async function GET(req: NextRequest) {
  return proxyJson('/client/plans', 'GET', req)
}

export async function POST(req: NextRequest) {
  return proxyJson('/client/plans', 'POST', req)
}
