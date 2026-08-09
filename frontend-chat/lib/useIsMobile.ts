'use client'

import { useEffect, useState } from 'react'

const MOBILE_QUERY = '(max-width: 768px)'

/**
 * True when the viewport matches the mobile breakpoint (≤768px — keep in
 * sync with --bp-mobile in globals.css and the @media queries driving
 * .app-shell/.app-sidebar-slot). SSR-safe: always false on first render,
 * then syncs to the real match on mount and stays in sync via the
 * matchMedia 'change' listener (covers resize + orientation change).
 */
export function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState(false)

  useEffect(() => {
    const mql = window.matchMedia(MOBILE_QUERY)
    setIsMobile(mql.matches)
    const onChange = (e: MediaQueryListEvent) => setIsMobile(e.matches)
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [])

  return isMobile
}
