import SharedPlanView from '@/components/client/SharedPlanView'

export const metadata = { title: 'Brandbiz — plan' }

export default async function SharedPlanPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params
  return <SharedPlanView token={token} />
}
