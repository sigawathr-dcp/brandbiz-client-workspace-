'use client'

import { useEffect } from 'react'
import PlanDocument from './PlanDocument'

// Client Workspaces (Phase 6, D21/D22) — PDF export via the browser's own
// print-to-PDF, no PDF library or headless browser needed. Reuses
// PlanDocument's exact markup; elements marked className="no-print" (top
// bar, Export/Talk-to-an-expert buttons) are hidden only in print media.
export default function PlanPrintView({ planId }: { planId: string }) {
  useEffect(() => {
    const t = setTimeout(() => window.print(), 700)
    return () => clearTimeout(t)
  }, [])

  return (
    <>
      <style>{`
        @media print {
          .no-print { display: none !important; }
          body { background: #fff !important; }
        }
      `}</style>
      <PlanDocument planId={planId} />
    </>
  )
}
