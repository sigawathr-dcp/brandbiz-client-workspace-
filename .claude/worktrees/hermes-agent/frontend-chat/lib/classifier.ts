/**
 * Client-side message classifier — display only.
 * Powers the live tier chip and KB mock.
 * The authoritative classification/policy decision still happens server-side.
 *
 * Ported from the reference prototype (data.jsx).
 */

import type { TierKey } from './domain'

export interface ClassifyReason {
  label: string
  sample?: string
}

export interface ClassifyResult {
  tier: TierKey
  reasons: ClassifyReason[]
}

/** Thai national ID checksum validation (13 digits) */
function validThaiID(digits: string): boolean {
  if (!/^\d{13}$/.test(digits)) return false
  let sum = 0
  for (let i = 0; i < 12; i++) sum += parseInt(digits[i], 10) * (13 - i)
  const check = (11 - (sum % 11)) % 10
  return check === parseInt(digits[12], 10)
}

interface KeywordRule {
  tier: TierKey
  re: RegExp
  label: string
}

const KEYWORD_RULES: KeywordRule[] = [
  { tier: 'T4', re: /\b(project\s+apollo|m&a|merger|acquisition target|source\s*code|board\s+deck|cap\s*table)\b/i, label: 'restricted keyword' },
  { tier: 'T4', re: /(ลับที่สุด|ความลับทางการค้า)/, label: 'Thai restricted keyword' },
  { tier: 'T3', re: /\b(customer|ลูกค้า|patient|passport|credit\s*card)\b/i, label: 'PII keyword' },
  { tier: 'T2', re: /\b(internal|ภายใน|salary|payroll|เงินเดือน)\b/i, label: 'internal keyword' },
]

const TIER_LEVELS: Record<TierKey, number> = { T1: 1, T2: 2, T3: 3, T4: 4 }

/**
 * Classify a draft message and return the highest matching tier with reasons.
 * Returns T1/General if text is empty or no rules match.
 */
export function detectTier(text: string): ClassifyResult {
  if (!text || !text.trim()) return { tier: 'T1', reasons: [] }

  const reasons: ClassifyReason[] = []
  let best: TierKey = 'T1'

  function bump(tier: TierKey) {
    if (TIER_LEVELS[tier] > TIER_LEVELS[best]) best = tier
  }

  // Thai national ID — checksum validated to cut false positives
  const idMatches = text.match(/\d[\d\s-]{12,20}\d/g) ?? []
  for (const m of idMatches) {
    const digits = m.replace(/\D/g, '')
    if (digits.length === 13 && validThaiID(digits)) {
      bump('T3')
      reasons.push({ label: 'Thai national ID', sample: m.trim() })
    }
  }

  // Credit-card-ish 16 digits
  const cc = text.match(/\b(?:\d[ -]?){16}\b/)
  if (cc) { bump('T3'); reasons.push({ label: 'card number', sample: cc[0].trim() }) }

  // Email → internal
  const email = text.match(/[\w.+-]+@[\w-]+\.[\w.-]+/)
  if (email) { bump('T2'); reasons.push({ label: 'email address', sample: email[0] }) }

  for (const rule of KEYWORD_RULES) {
    const m = text.match(rule.re)
    if (m) { bump(rule.tier); reasons.push({ label: rule.label, sample: m[0] }) }
  }

  return { tier: best, reasons }
}
