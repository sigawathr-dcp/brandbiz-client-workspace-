// Client Workspaces redesign (PLAN.md Task 5.10) — turns a saved Plan's
// `provenance` JSONB into the rows the plan document's side rail renders.
//
// Defensive by necessity: plans saved before this redesign (and before
// draft_plan() started copying research_sources — see
// backend/app/services/plan.py) won't have every field below, and the
// column is untyped JSONB, so a malformed or partial value must degrade to
// "fewer rows", never a crash.
//
// Deliberately does NOT invent a rate-card filename or per-code detail —
// app/services/plan.py's provenance only ever carries rate_card_codes
// (a list of codes), not a source workbook name, so the RATE row states a
// count, not a fabricated document.

export interface ProvenanceRow {
  key: string
  code: 'RATE' | 'CASE' | 'WEB'
  label: string
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null
}

export function parseProvenance(raw: unknown): ProvenanceRow[] {
  if (!isRecord(raw)) return []
  const rows: ProvenanceRow[] = []

  const rateCardCodes = Array.isArray(raw.rate_card_codes)
    ? raw.rate_card_codes.filter((c): c is string => typeof c === 'string')
    : []
  if (rateCardCodes.length > 0) {
    rows.push({
      key: 'rate',
      code: 'RATE',
      label: `${rateCardCodes.length} rate-card line item${rateCardCodes.length === 1 ? '' : 's'}`,
    })
  }

  const caseFiles = Array.isArray(raw.case_files) ? raw.case_files : []
  for (const cf of caseFiles) {
    if (isRecord(cf) && typeof cf.filename === 'string' && cf.filename) {
      const id = typeof cf.file_id === 'string' ? cf.file_id : cf.filename
      rows.push({ key: `case-${id}`, code: 'CASE', label: cf.filename })
    }
  }

  const researchSources = Array.isArray(raw.research_sources) ? raw.research_sources : []
  if (researchSources.length > 0) {
    rows.push({
      key: 'web',
      code: 'WEB',
      label: `${researchSources.length} cited source${researchSources.length === 1 ? '' : 's'}`,
    })
  }

  return rows
}
