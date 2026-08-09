import PlanPrintView from '@/components/client/PlanPrintView'

export const metadata = { title: 'Brandbiz — plan (print)' }

export default async function ClientPlanPrintPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return <PlanPrintView planId={id} />
}
