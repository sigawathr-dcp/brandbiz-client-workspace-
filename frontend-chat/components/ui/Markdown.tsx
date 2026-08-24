'use client'

// ---------------------------------------------------------------------------
// Markdown renderer — no external deps.
//
// Extracted from ChatPane.tsx so it can be reused wherever assistant/agent
// output is rendered (chat bubbles, Tasks detail page result panel, etc.)
// without duplicating the parser.
// ---------------------------------------------------------------------------

import { memo, useMemo } from 'react'

function parseInline(text: string): React.ReactNode[] {
  const result: React.ReactNode[] = []
  const regex = /(`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\n]+\*)/g
  let last = 0, m: RegExpExecArray | null, idx = 0
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) result.push(text.slice(last, m.index))
    const tok = m[0]
    if (tok.startsWith('**'))
      result.push(<strong key={idx++}>{tok.slice(2, -2)}</strong>)
    else if (tok.startsWith('`'))
      result.push(
        <code key={idx++} style={{
          background: 'var(--surface-2)',
          color: 'var(--ink)',
          padding: '1px 5px',
          borderRadius: 4,
          fontFamily: 'var(--font-mono)',
          fontSize: '0.88em',
        }}>
          {tok.slice(1, -1)}
        </code>
      )
    else
      result.push(<em key={idx++}>{tok.slice(1, -1)}</em>)
    last = m.index + tok.length
  }
  if (last < text.length) result.push(text.slice(last))
  return result
}

type MdBlock =
  | { t: 'h'; level: 1 | 2 | 3; text: string }
  | { t: 'p'; text: string }
  | { t: 'ul'; items: string[] }
  | { t: 'ol'; items: string[] }
  | { t: 'code'; lang: string; code: string }
  | { t: 'img'; alt: string; src: string }
  | { t: 'table'; head: string[]; rows: string[][] }
  | { t: 'rule' }
  | { t: 'blank' }

function splitTableRow(row: string): string[] {
  return row.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
}

function parseBlocks(src: string): MdBlock[] {
  const lines = src.split('\n')
  const blocks: MdBlock[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (line.startsWith('```')) {
      const lang = line.slice(3).trim(); i++
      const code: string[] = []
      while (i < lines.length && !lines[i].startsWith('```')) { code.push(lines[i]); i++ }
      blocks.push({ t: 'code', lang, code: code.join('\n') }); i++; continue
    }
    const h3 = line.match(/^### (.+)/); if (h3) { blocks.push({ t: 'h', level: 3, text: h3[1] }); i++; continue }
    const h2 = line.match(/^## (.+)/);  if (h2) { blocks.push({ t: 'h', level: 2, text: h2[1] }); i++; continue }
    const h1 = line.match(/^# (.+)/);   if (h1) { blocks.push({ t: 'h', level: 1, text: h1[1] }); i++; continue }
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(line.trim())) { blocks.push({ t: 'rule' }); i++; continue }
    if (/^[*-] /.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^[*-] /.test(lines[i])) { items.push(lines[i].slice(2)); i++ }
      blocks.push({ t: 'ul', items }); continue
    }
    if (/^\d+\. /.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\d+\. /.test(lines[i])) { items.push(lines[i].replace(/^\d+\. /, '')); i++ }
      blocks.push({ t: 'ol', items }); continue
    }
    const imgMatch = line.match(/^!\[([^\]]*)\]\(([^)]+)\)/)
    if (imgMatch) { blocks.push({ t: 'img', alt: imgMatch[1], src: imgMatch[2] }); i++; continue }
    if (
      /^\s*\|/.test(line) &&
      i + 1 < lines.length &&
      /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])
    ) {
      const head = splitTableRow(line)
      i += 2
      const rows: string[][] = []
      while (i < lines.length && /^\s*\|/.test(lines[i])) { rows.push(splitTableRow(lines[i])); i++ }
      blocks.push({ t: 'table', head, rows }); continue
    }
    if (line.trim() === '') { blocks.push({ t: 'blank' }); i++; continue }
    const para: string[] = []
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !lines[i].startsWith('#') &&
      !lines[i].startsWith('```') &&
      !/^[*-] /.test(lines[i]) &&
      !/^\d+\. /.test(lines[i]) &&
      !/^\s*\|/.test(lines[i]) &&
      !/^(-{3,}|\*{3,}|_{3,})$/.test(lines[i].trim())
    ) { para.push(lines[i]); i++ }
    if (para.length) blocks.push({ t: 'p', text: para.join(' ') })
  }
  return blocks
}

export const MarkdownContent = memo(function MarkdownContent({ text }: { text: string }) {
  const blocks = useMemo(() => parseBlocks(text), [text])
  return (
    <>
      {blocks.map((b, i) => {
        switch (b.t) {
          case 'h':
            return (
              <div key={i} style={{
                margin: '8px 0 4px',
                fontWeight: 600,
                color: 'var(--ink)',
                fontSize: b.level === 1 ? '1.12em' : b.level === 2 ? '1.04em' : '0.97em',
              }}>
                {parseInline(b.text)}
              </div>
            )
          case 'p':
            return <p key={i} style={{ margin: '4px 0' }}>{parseInline(b.text)}</p>
          case 'ul':
            return (
              <ul key={i} style={{ margin: '4px 0', paddingLeft: 20 }}>
                {b.items.map((it, j) => <li key={j}>{parseInline(it)}</li>)}
              </ul>
            )
          case 'ol':
            return (
              <ol key={i} style={{ margin: '4px 0', paddingLeft: 20 }}>
                {b.items.map((it, j) => <li key={j}>{parseInline(it)}</li>)}
              </ol>
            )
          case 'code':
            return (
              <pre key={i} style={{
                background: 'var(--surface-sunk)',
                border: '1px solid var(--line)',
                borderRadius: 'var(--r-md)',
                padding: '10px 14px',
                overflowX: 'auto',
                margin: '6px 0',
                fontSize: '0.85em',
                fontFamily: 'var(--font-mono)',
                color: 'var(--ink-2)',
                lineHeight: 1.6,
              }}>
                <code>{b.code}</code>
              </pre>
            )
          case 'table':
            return (
              <div key={i} className="md-table-wrap">
                <table className="md-table">
                  <thead>
                    <tr>{b.head.map((h, j) => <th key={j}>{parseInline(h)}</th>)}</tr>
                  </thead>
                  <tbody>
                    {b.rows.map((r, j) => (
                      <tr key={j}>
                        {r.map((c, k) => (
                          <td key={k} data-label={b.head[k] ?? ''}>{parseInline(c)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          case 'img':
            return (
              <img
                key={i}
                src={b.src}
                alt={b.alt}
                style={{ maxWidth: '100%', borderRadius: 8, display: 'block', margin: '8px 0' }}
              />
            )
          case 'rule':
            return <hr key={i} style={{ border: 'none', borderTop: '1px solid var(--line)', margin: '8px 0' }} />
          case 'blank':
            return <div key={i} style={{ height: 6 }} />
          default:
            return null
        }
      })}
    </>
  )
})
