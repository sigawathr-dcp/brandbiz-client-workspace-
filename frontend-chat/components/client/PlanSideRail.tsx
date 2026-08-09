'use client'

import { parseProvenance } from './provenance'
import type { SavedPlan } from './types'

// Client Workspaces redesign (PLAN.md Task 5.10) — the plan document's
// 320px right rail: what the plan drew on (Provenance), its real save
// history (Versions — plan_versions gets exactly one row per plan today;
// this renders that row, never a fabricated v2+), and a storage note.
export default function PlanSideRail({ plan }: { plan: SavedPlan }) {
  const rows = parseProvenance(plan.provenance)

  return (
    <div
      className="no-print"
      style={{
        borderLeft: '1px solid var(--line)',
        background: 'var(--surface)',
        padding: '18px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 18,
      }}
    >
      {rows.length > 0 && (
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, color: 'var(--ink)' }}>Provenance</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
            {rows.map((row) => (
              <div
                key={row.key}
                style={{
                  display: 'flex',
                  gap: 9,
                  alignItems: 'center',
                  border: '1px solid var(--line)',
                  borderRadius: 8,
                  padding: '8px 10px',
                }}
              >
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 600,
                    borderRadius: 4,
                    padding: '2px 5px',
                    flex: 'none',
                    ...(row.code === 'RATE'
                      ? { color: 'var(--t1)', background: 'var(--t1-bg)' }
                      : row.code === 'CASE'
                        ? { color: 'var(--accent)', background: 'var(--accent-weak)' }
                        : { color: 'var(--info)', background: 'var(--info-bg)' }),
                  }}
                >
                  {row.code}
                </span>
                <div
                  style={{
                    fontSize: 12,
                    fontFamily: 'var(--font-mono)',
                    color: 'var(--ink-2)',
                    minWidth: 0,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {row.label}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, color: 'var(--ink)' }}>Versions</div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {plan.versions.map((v) => (
            <div key={v.version} style={{ display: 'flex', gap: 10, padding: '9px 0', borderBottom: '1px solid var(--line)' }}>
              <span style={{ fontSize: 11.5, fontFamily: 'var(--font-mono)', color: 'var(--accent)', width: 22 }}>
                v{v.version}
              </span>
              <div style={{ fontSize: 12, color: 'var(--ink-2)' }}>
                Saved from chat · {new Date(v.created_at).toLocaleString()}
              </div>
            </div>
          ))}
          {plan.status === 'draft' && (
            <div style={{ display: 'flex', gap: 10, padding: '9px 0', color: 'var(--ink-4)' }}>
              <span style={{ fontSize: 11.5, fontFamily: 'var(--font-mono)', width: 22 }}>—</span>
              <div style={{ fontSize: 12 }}>Expert revision pending</div>
            </div>
          )}
        </div>
      </div>

      <div
        style={{
          background: 'var(--surface-2)',
          borderRadius: 10,
          padding: '12px 13px',
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
        }}
      >
        <div style={{ fontSize: 11.5, lineHeight: 1.55, color: 'var(--ink-2)' }}>
          Stored as a plan, outside chat messages — so the 30-day message deletion doesn&apos;t take it with them.
        </div>
      </div>
    </div>
  )
}
