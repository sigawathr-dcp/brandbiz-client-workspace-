import PlanDocument from '@/components/client/PlanDocument'

export const metadata = { title: 'Brandbiz — plan' }

export default async function ClientPlanPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return <PlanDocument planId={id} />
}
