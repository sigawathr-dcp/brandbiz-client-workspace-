import type { Finding } from './types'

// app/routers/client.py:695 splits the raw Perplexity markdown response on
// every newline into one `finding` per line, dropping blank lines. That
// destroys multi-line markdown blocks — a GFM table's header/separator/rows
// each become separate findings, and every bullet becomes its own single-item
// list. Naively rejoining with '\n\n' (one blank line between every finding)
// would re-separate those rows/items right back apart.
//
// This reassembles them: consecutive lines that are both table rows, or both
// list items, rejoin with a single '\n' so they stay one block; everything
// else gets a blank line between it, as before. Works on already-stored
// ResearchRun rows just as well as newly-run scans, since it operates purely
// on the finding text at render time.
const TABLE_ROW = /^\s*\|.*\|\s*$/
const LIST_ITEM = /^\s*(?:[-*]\s|\d+\.\s)/

export function findingsToMarkdown(findings: Finding[]): string {
  const lines = findings.map((f) => f.text).filter(Boolean)
  return lines.reduce((acc, line, i) => {
    if (i === 0) return line
    const prev = lines[i - 1]
    const sameBlock =
      (TABLE_ROW.test(prev) && TABLE_ROW.test(line)) ||
      (LIST_ITEM.test(prev) && LIST_ITEM.test(line))
    return acc + (sameBlock ? '\n' : '\n\n') + line
  }, '')
}
