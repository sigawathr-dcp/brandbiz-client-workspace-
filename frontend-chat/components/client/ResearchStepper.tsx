'use client'

import { MarkdownContent } from '@/components/ui/Markdown'
import { findingsToMarkdown } from './researchMarkdown'
import type { ResearchResult } from './types'

// Client Workspaces (Phase 5, D21/D22) — the "External market scan · IAG"
// widget rendered inline in the transcript. IAG ≈ Perplexity (per
// DSME_ai.md's mapping); citations are real, returned by the Perplexity API
// call in POST /client/research — not decorative.
export default function ResearchStepper({
  status,
  result,
  error,
  showDetail,
}: {
  status: 'pending' | 'done' | 'error'
  result?: ResearchResult
  error?: string
  showDetail?: boolean
}) {
  return (
    <div
      style={{
        marginTop: 14,
        border: '1px solid var(--line)',
        borderRadius: 11,
        background: 'var(--surface-2)',
        padding: '13px 14px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: status === 'done' ? 11 : 0 }}>
        {status === 'pending' && (
          <span
            style={{
              width: 12,
              height: 12,
              borderRadius: '50%',
              border: '2px solid var(--accent)',
              borderTopColor: 'transparent',
              animation: 'spin 0.8s linear infinite',
            }}
          />
        )}
        {status === 'done' && (
          <span
            style={{
              width: 12,
              height: 12,
              borderRadius: '50%',
              background: 'var(--t1-bg)',
              border: '2px solid var(--t1)',
            }}
          />
        )}
        {status === 'error' && (
          <span
            style={{
              width: 12,
              height: 12,
              borderRadius: '50%',
              background: 'var(--danger-bg)',
              border: '2px solid var(--danger)',
            }}
          />
        )}
        <span
          style={{
            fontSize: 11.5,
            fontWeight: 600,
            letterSpacing: '.05em',
            textTransform: 'uppercase',
            color: 'var(--ink-3)',
          }}
        >
          External market scan · IAG
        </span>
      </div>

      {status === 'pending' && (
        <div style={{ fontSize: 12.5, color: 'var(--ink-3)', marginTop: 8 }}>
          Searching · reading · synthesizing…
        </div>
      )}

      {status === 'error' && (
        <div style={{ fontSize: 12.5, color: 'var(--ink-3)', marginTop: 8 }}>
          Market research is temporarily unavailable.
          {showDetail && error && (
            <div style={{ marginTop: 4, fontSize: 11.5, fontFamily: 'monospace' }}>Reason: {error}</div>
          )}
        </div>
      )}

      {status === 'done' && result && (
        <div
          style={{
            borderTop: '1px solid var(--line-2)',
            paddingTop: 12,
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
          }}
        >
          {result.findings.length > 0 && (
            <div style={{ fontSize: 13.5, lineHeight: 1.6, color: 'var(--ink-2)' }}>
              <MarkdownContent text={findingsToMarkdown(result.findings)} />
            </div>
          )}
          {result.citations.length > 0 && (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
              {result.citations.map((c) => (
                <span
                  key={c.index}
                  style={{
                    fontSize: 11,
                    color: 'var(--ink-2)',
                    background: 'var(--surface)',
                    border: '1px solid var(--line-2)',
                    borderRadius: 6,
                    padding: '3px 8px',
                  }}
                >
                  [{c.index}] {c.source}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
