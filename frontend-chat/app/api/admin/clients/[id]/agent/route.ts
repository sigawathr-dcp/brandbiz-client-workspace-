import { NextRequest } from 'next/server'
import { adminProxy } from '@/lib/adminBff'

export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return adminProxy(`/admin/clients/${id}/agent`, 'GET', req)
}

export async function PUT(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return adminProxy(`/admin/clients/${id}/agent`, 'PUT', req)
}
