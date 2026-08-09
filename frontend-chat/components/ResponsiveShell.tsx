'use client'

import { useEffect, useState } from 'react'
import { usePathname } from 'next/navigation'
import { Ic } from './ui/Icon'

interface ResponsiveShellProps {
  /** Rendered NavSidebar (already Suspense-wrapped by the caller layout). */
  sidebar: React.ReactNode
  /** Main content area. */
  children: React.ReactNode
  /**
   * Per-layout overrides for the main content area, applied on top of the
   * `.app-main` class (e.g. chat wants `overflow:'hidden'` because ChatPane
   * manages its own internal scroll region; other areas want 'auto').
   */
  mainStyle?: React.CSSProperties
}

/**
 * Shared app shell: sidebar + main on desktop, an off-canvas drawer with a
 * hamburger topbar on mobile (≤768px, see --bp-mobile in globals.css).
 *
 * Positioning (width/flex/fixed placement) lives in CSS classes so the
 * @media rules in globals.css can override it — inline styles on the
 * sidebar/main would win over a plain class-based media query otherwise.
 */
export default function ResponsiveShell({ sidebar, children, mainStyle }: ResponsiveShellProps) {
  const [open, setOpen] = useState(false)
  const pathname = usePathname()

  // Close the drawer on navigation so it doesn't stay open behind the new page.
  useEffect(() => {
    setOpen(false)
  }, [pathname])

  // Lock background scroll while the drawer is open on mobile.
  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [open])

  return (
    <div className="app-shell">
      <div className="app-topbar">
        <button
          type="button"
          className="app-hamburger"
          aria-label={open ? 'Close navigation' : 'Open navigation'}
          aria-expanded={open}
          onClick={() => setOpen(o => !o)}
        >
          {open ? <Ic.x size={20} strokeWidth={1.9} /> : <Ic.Menu size={20} strokeWidth={1.9} />}
        </button>
      </div>

      {open && <div className="app-scrim" onClick={() => setOpen(false)} />}

      <div className={`app-sidebar-slot${open ? ' open' : ''}`}>
        {sidebar}
      </div>

      <main className="app-main" style={mainStyle}>
        {children}
      </main>
    </div>
  )
}
