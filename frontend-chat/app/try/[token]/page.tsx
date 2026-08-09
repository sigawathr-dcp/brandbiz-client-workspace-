import RedeemInvite from '@/components/client/RedeemInvite'

export const metadata = { title: 'Brandbiz — one moment' }

export default async function TryTokenPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params
  return <RedeemInvite token={token} />
}
