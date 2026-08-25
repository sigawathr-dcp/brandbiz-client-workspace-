import type { CSSProperties } from 'react'

// Client Workspaces (Phase 5, D21/D22) — the amount column of every budget
// table (PlanDraftCard, PlanDocument, SharedPlanView).
//
// `width: '1%'` makes the browser's auto table layout shrink the column to
// its widest amount and give the rest to the line-item label, and `nowrap`
// stops a long total like 793100.00 from breaking mid-number. Both are
// needed: on a phone the label column otherwise wins the width fight and
// the digits wrap onto a second line.
export const moneyCol: CSSProperties = {
  width: '1%',
  whiteSpace: 'nowrap',
}

// Thousands separators, for display only. Amounts reach the frontend as the
// server's canonical decimal strings ("216000.00" — app/services/
// rate_card.py::price does str(Decimal)), and this groups the integer part
// by string surgery rather than going through Number, so no amount can be
// re-rounded on its way to the screen. Anything that isn't a plain decimal
// (or is null, for a line an expert still has to price) passes through
// untouched.
export function money(amount: string | null | undefined): string {
  if (amount == null) return ''
  const m = /^(-?)(\d+)(\.\d+)?$/.exec(amount.trim())
  if (!m) return amount
  const [, sign, whole, frac = ''] = m
  return sign + whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + frac
}

// Percent-of-estimate column (replaces the amount column on every plan
// surface — PlanDraftCard, PlanDocument/PlanPrintView, SharedPlanView). The
// client sees how the estimate is split, not what it costs; the money is
// still what the server computed, it just isn't rendered.
//
// `parts` must be the rows that add up to `total` (the budget lines plus
// contingency), so the printed integers sum to exactly 100 — that's what the
// largest-remainder pass below is for: naive rounding of 33.4/33.3/33.3 shows
// 33/33/33 under a 100% total and reads as a bug. Unlike money(), this goes
// through Number: a percentage is a derived display value, not an amount, so
// float rounding can't leak into anything the client is quoted on.
export function percentShares(parts: string[], total: string): string[] {
  const t = Number(total)
  if (!Number.isFinite(t) || t <= 0) return parts.map(() => '—')

  const raw = parts.map((p) => {
    const n = Number(p)
    return Number.isFinite(n) ? (n / t) * 100 : 0
  })
  const out = raw.map((r) => Math.floor(r))
  let left = 100 - out.reduce((a, b) => a + b, 0)
  const byRemainder = raw
    .map((r, i) => ({ i, rem: r - Math.floor(r) }))
    .sort((a, b) => b.rem - a.rem)
  for (const { i } of byRemainder) {
    if (left <= 0) break
    out[i] += 1
    left -= 1
  }
  return out.map((n) => `${n}%`)
}

// Percent move between two totals ("+12%"), for the revision diff — the one
// place a changed estimate still has to be legible without naming a number.
export function percentDelta(before: string | null, after: string | null): string | null {
  const b = Number(before)
  const a = Number(after)
  if (!Number.isFinite(b) || !Number.isFinite(a) || b <= 0) return null
  const pct = Math.round(((a - b) / b) * 100)
  if (pct === 0) return null
  return `${pct > 0 ? '+' : ''}${pct}%`
}
