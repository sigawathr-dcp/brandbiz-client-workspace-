'use client'

import { useState } from 'react'
import type { CaseMatchItem, CasesResult } from './types'

// Client Workspaces (Phase 5, D21/D22) — case-library match cards, inline
// in the transcript. Scores come from real pgvector cosine similarity
// (POST /client/cases -> app/tools/rag_search.retrieve), not canned demo
// numbers — the file must actually be attached to the workspace's agent as
// a knowledge file and pass the RAG relevance threshold to appear here.
//
// The card leads with what a prospective client actually reads for trust:
// the brand name, the kind of work, a short Thai narrative, and a link to
// the live work page — parsed server-side by app/services/case_card.py.
// Filenames and raw similarity percentages are debug detail, shown only in
// staff preview (showDetail).

// "case-study_ptt_lubricants.md" -> "PTT LUBRICANTS" — last-resort label
// when the document had no parseable client/title.
function labelFromFilename(filename: string): string {
  return filename
    .replace(/^case-study[_-]?/, '')
    .replace(/\.[^.]+$/, '')
    .replace(/_/g, ' ')
    .toUpperCase()
}

function CaseCard({ m, showDetail }: { m: CaseMatchItem; showDetail?: boolean }) {
  const heading = m.client || m.title || labelFromFilename(m.filename)
  // The campaign title is a useful second line only when it says something
  // the heading doesn't (placeholder write-ups repeat the client name).
  const campaign = m.title && m.title !== heading ? m.title : null
  // Remote portfolio URLs rot; fall back to the text-only layout on error
  // rather than showing a broken-image glyph next to every card.
  const [imgOk, setImgOk] = useState(true)
  const showImage = Boolean(m.image_url) && imgOk
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 11,
        border: '1px solid var(--line)',
        borderRadius: 11,
        padding: '12px 13px',
        background: 'var(--surface)',
      }}
    >
      {showImage && (
        <img
          src={m.image_url!}
          alt={heading}
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setImgOk(false)}
          style={{
            width: 64,
            height: 64,
            flexShrink: 0,
            objectFit: 'cover',
            borderRadius: 8,
            border: '1px solid var(--line)',
          }}
        />
      )}
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink)' }}>{heading}</div>
          {m.category && (
            <span
              style={{
                fontSize: 10.5,
                fontWeight: 600,
                letterSpacing: 0.3,
                color: 'var(--ink-3)',
                background: 'var(--surface-2)',
                borderRadius: 99,
                padding: '2px 8px',
                whiteSpace: 'nowrap',
              }}
            >
              {m.category}
            </span>
          )}
          {showDetail && (
            <span style={{ fontSize: 10.5, color: 'var(--ink-3)', fontFamily: 'monospace' }}>
              {m.filename} · {Math.round(m.score * 100)}%
            </span>
          )}
        </div>
        {campaign && (
          <div style={{ marginTop: 3, fontSize: 12, color: 'var(--ink-3)' }}>{campaign}</div>
        )}
        {m.summary && (
          <div
            style={{
              marginTop: 6,
              fontSize: 13,
              lineHeight: 1.55,
              color: 'var(--ink-2)',
              display: '-webkit-box',
              WebkitLineClamp: 3,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}
          >
            {m.summary}
          </div>
        )}
        {m.source_url && (
          <a
            href={m.source_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'inline-block',
              marginTop: 8,
              fontSize: 12.5,
              fontWeight: 600,
              color: 'var(--t1)',
              textDecoration: 'none',
            }}
          >
            ดูผลงานจริง ↗
          </a>
        )}
      </div>
    </div>
  )
}

export default function CaseMatchCards({
  status,
  result,
  error,
  showDetail,
}: {
  status: 'pending' | 'done' | 'error'
  result?: CasesResult
  error?: string
  showDetail?: boolean
}) {
  if (status === 'pending') {
    return (
      <div style={{ marginTop: 14, fontSize: 12.5, color: 'var(--ink-3)' }}>
        Comparing against the Brandbiz case library…
      </div>
    )
  }
  if (status === 'error') {
    return (
      <div style={{ marginTop: 14, fontSize: 12.5, color: 'var(--ink-3)' }}>
        Case matching is temporarily unavailable.
        {showDetail && error && (
          <div style={{ marginTop: 4, fontSize: 11.5, fontFamily: 'monospace' }}>Reason: {error}</div>
        )}
      </div>
    )
  }
  if (!result || result.matches.length === 0) {
    return (
      <div style={{ marginTop: 14, fontSize: 12.5, color: 'var(--ink-3)' }}>
        No case studies matched closely enough to show.
      </div>
    )
  }

  return (
    <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 9 }}>
      {result.matches.map((m) => (
        <CaseCard key={m.file_id} m={m} showDetail={showDetail} />
      ))}
    </div>
  )
}
