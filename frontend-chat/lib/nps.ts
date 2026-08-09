// Shared NPS bucketing (PLAN.md Task 5.10) — used by the client plan
// document's rating widget (components/client/PlanRating.tsx) and the
// staff-facing expert leads inbox (components/admin/LeadsInboxPage.tsx),
// which is why this lives in lib/ rather than components/client/.

export type NpsBucket = 'detractor' | 'passive' | 'promoter'

export interface NpsVerdict {
  bucket: NpsBucket
  label: string
  color: string
  background: string
}

export function npsVerdict(score: number): NpsVerdict {
  if (score <= 6) {
    return { bucket: 'detractor', label: `Detractor · ${score}/10`, color: 'var(--danger)', background: 'var(--danger-bg)' }
  }
  if (score <= 8) {
    return { bucket: 'passive', label: `Passive · ${score}/10`, color: 'var(--warning)', background: 'var(--warning-bg)' }
  }
  return { bucket: 'promoter', label: `Promoter · ${score}/10`, color: 'var(--t1)', background: 'var(--t1-bg)' }
}
