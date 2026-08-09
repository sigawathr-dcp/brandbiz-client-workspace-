import { redirect } from 'next/navigation'

export default function Home() {
  // See app/login/page.tsx — everyone lands in the client workspace first.
  redirect('/w')
}
