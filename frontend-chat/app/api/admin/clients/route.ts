import { NextRequest } from 'next/server'
import { adminProxy } from '@/lib/adminBff'

export async function GET(req: NextRequest) {
  return adminProxy('/admin/clients', 'GET', req)
}

export async function POST(req: NextRequest) {
  return adminProxy('/admin/clients', 'POST', req)
}
