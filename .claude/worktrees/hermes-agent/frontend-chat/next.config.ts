import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  output: 'standalone',
  devIndicators: false,
  // BACKEND_URL is server-only (Next.js API routes → FastAPI). Not exposed to the browser.
  // NEXT_PUBLIC_API_URL is the public-facing backend URL for browser redirects (e.g. OAuth).
  env: {
    BACKEND_URL: process.env.BACKEND_URL || 'http://localhost:8000',
  },
}

export default nextConfig
