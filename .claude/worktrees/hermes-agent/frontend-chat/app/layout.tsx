import type { Metadata } from 'next'
import { IBM_Plex_Sans, IBM_Plex_Sans_Thai, IBM_Plex_Mono } from 'next/font/google'
import './globals.css'

const ibmSans = IBM_Plex_Sans({
  subsets: ['latin'],
  weight: ['300', '400', '500', '600', '700'],
  variable: '--font-sans',
  display: 'swap',
})

const ibmSansThai = IBM_Plex_Sans_Thai({
  subsets: ['thai'],
  weight: ['300', '400', '500', '600', '700'],
  variable: '--font-sans-thai',
  display: 'swap',
})

const ibmMono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
  variable: '--font-mono',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'Brandbiz AI',
  description: 'Brandbiz AI Chat',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="th"
      suppressHydrationWarning
      className={`${ibmSans.variable} ${ibmSansThai.variable} ${ibmMono.variable}`}
    >
      <body style={{ height: '100vh', overflow: 'hidden' }}>
        {children}
      </body>
    </html>
  )
}
