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
