import { NextRequest } from 'next/server'
import { proxyJson } from '@/lib/clientBff'

// Task 5.11 — editable company profile. Correct one or more already-
// answered intake fields; see app/routers/client.py::edit_intake_fields.
export async function PATCH(req: NextRequest) {
  return proxyJson('/client/intake/fields', 'PATCH', req)
}
