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
        // Media beside the text on a wide card, stacked above it once the
        // card is narrow — the work panel is ~372px and drops to full-width
        // drawer under 768px (.client-workpanel in globals.css), where a
        // 132px media column would leave the copy unreadable.
        flexWrap: 'wrap',
        alignItems: 'stretch',
        // No gap: the text block carries symmetric padding instead, so it
        // reads correctly both side-by-side and stacked (a gap would leave
        // the copy flush against the left edge once the row wraps).
        gap: 0,
        border: '1px solid var(--line)',
        borderRadius: 11,
        padding: showImage ? 0 : '12px 13px',
        background: 'var(--surface)',
        overflow: 'hidden',
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
            // flex-basis 132 with grow:1 = a fixed-ish media column that
            // becomes a full-width banner when the row wraps.
            flex: '1 1 132px',
            maxWidth: 176,
            minWidth: 132,
            alignSelf: 'stretch',
            minHeight: 108,
            objectFit: 'cover',
            display: 'block',
          }}
        />
      )}
      <div
        style={{
          minWidth: 0,
          // Needs to be wider than the media before the row is allowed to sit
          // side by side; below that the whole thing wraps to a stacked card.
          flex: '999 1 200px',
          padding: showImage ? '12px 13px' : undefined,
        }}
      >
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
        {!!m.matched_on?.length && (
          <div
            style={{
              marginTop: 8,
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              gap: 5,
              fontSize: 11.5,
              color: 'var(--ink-3)',
            }}
          >
            <span>ตรงกับ</span>
            {m.matched_on.map((d) => (
              <span
                key={d}
                style={{
                  background: 'var(--surface-2)',
                  border: '1px solid var(--line)',
                  borderRadius: 99,
                  padding: '1px 7px',
                  color: 'var(--ink-2)',
                  whiteSpace: 'nowrap',
                }}
              >
                {d}
              </span>
            ))}
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
  if (result && result.library_available === false) {
    // Zero chunks reachable — a setup fault (unseeded / mis-scoped case
    // library), not a scoring outcome. Must not read as "nothing similar".
    return (
      <div style={{ marginTop: 14, fontSize: 12.5, color: 'var(--ink-3)' }}>
        The case library isn&apos;t available for this workspace yet.
        {showDetail && (
          <div style={{ marginTop: 4, fontSize: 11.5, fontFamily: 'monospace' }}>
            Reason: retrieval returned 0 chunks — check the library seed / file scope (ADR 0002)
          </div>
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
