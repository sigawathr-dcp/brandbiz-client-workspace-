'use client'

import { Ic } from '../ui/Icon'
import type { Journey, JourneyStage } from './journey'

// Client Workspaces redesign (PLAN.md Task 5.10) — the 212px left rail:
// progress card, "Your journey" stage list, "Rewards" unlock list, a link
// to My plans, and a privacy footer. All state comes from journey.ts —
// this component only renders it.
export default function NavRail({
  journey,
  planCount,
  workspaceName,
  onClose,
}: {
  journey: Journey
  planCount: number
  workspaceName: string
  onClose?: () => void
}) {
  return (
    <div
      style={{
        borderRight: '1px solid var(--line)',
        background: 'var(--surface)',
        padding: '16px 12px',
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
        minHeight: 0,
        height: '100%',
      }}
    >
      {onClose && (
        <button
          className="client-navrail-close"
          onClick={onClose}
          aria-label="Close"
          style={{
            width: 30,
            height: 30,
            borderRadius: 8,
            border: '1px solid var(--line-2)',
            background: 'var(--surface)',
            color: 'var(--ink-2)',
            cursor: 'pointer',
            alignItems: 'center',
            justifyContent: 'center',
            alignSelf: 'flex-end',
            marginBottom: 4,
          }}
        >
          <Ic.x size={14} />
        </button>
      )}

      {/* progress card */}
      <div
        style={{
          border: '1px solid var(--line)',
          borderRadius: 12,
          background: 'var(--surface-2)',
          padding: '12px 13px',
          marginBottom: 6,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 7, marginBottom: 3 }}>
          <div
            style={{
              fontSize: 22,
              fontWeight: 600,
              letterSpacing: '-.02em',
              color: 'var(--accent)',
              fontFamily: 'var(--font-mono)',
            }}
          >
            {journey.pct}%
          </div>
          <div style={{ fontSize: 11, color: 'var(--ink-3)' }}>complete</div>
        </div>
        <div style={{ fontSize: 11.5, fontWeight: 500, color: 'var(--ink-2)', marginBottom: 9 }}>
          {journey.chapterLabel}
        </div>
        <div style={{ height: 6, borderRadius: 3, background: 'var(--surface-sunk)', overflow: 'hidden' }}>
          <div
            style={{
              height: '100%',
              borderRadius: 3,
              background: 'var(--accent)',
              width: `${journey.pct}%`,
              transition: 'width .6s cubic-bezier(.2,.8,.2,1)',
            }}
          />
        </div>
      </div>

      <div
        style={{
          fontSize: 10.5,
          fontWeight: 600,
          letterSpacing: '.08em',
          textTransform: 'uppercase',
          color: 'var(--ink-4)',
          padding: '2px 8px 2px',
        }}
      >
        Your journey
      </div>
      {journey.stages.map((s, i) => (
        <StageRow key={s.id} stage={s} num={i + 1} />
      ))}

      <div style={{ height: 1, background: 'var(--line)', margin: '8px 4px' }} />
      <div
        style={{
          fontSize: 10.5,
          fontWeight: 600,
          letterSpacing: '.08em',
          textTransform: 'uppercase',
          color: 'var(--ink-4)',
          padding: '2px 8px 4px',
        }}
      >
        Rewards
      </div>
      {journey.rewards.map((r) => (
        <div key={r.id} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', padding: '7px 10px', borderRadius: 9 }}>
          <div
            style={{
              width: 20,
              height: 20,
              flex: 'none',
              borderRadius: 6,
              display: 'grid',
              placeItems: 'center',
              marginTop: 1,
              background: r.unlocked ? 'var(--t1-bg)' : 'var(--surface-2)',
              color: r.unlocked ? 'var(--t1)' : 'var(--ink-4)',
              border: r.unlocked ? 'none' : '1px solid var(--line)',
            }}
          >
            {r.unlocked ? <Ic.check size={12} strokeWidth={1.7} /> : <Ic.lock size={11} strokeWidth={1.7} />}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                fontSize: 12,
                fontWeight: r.unlocked ? 600 : 400,
                color: r.unlocked ? 'var(--ink)' : 'var(--ink-4)',
                lineHeight: 1.35,
              }}
            >
              {r.label}
            </div>
            <div style={{ fontSize: 10.5, color: 'var(--ink-4)', marginTop: 1 }}>{r.note}</div>
          </div>
        </div>
      ))}

      <div style={{ height: 1, background: 'var(--line)', margin: '8px 4px' }} />
      <a
        href="/w/plans"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 9,
          width: '100%',
          textAlign: 'left',
          padding: '8px 10px',
          borderRadius: 8,
          fontSize: 13.5,
          fontWeight: 500,
          textDecoration: 'none',
          color: 'var(--ink-2)',
          opacity: planCount > 0 ? 1 : 0.55,
        }}
      >
        <Ic.file size={16} />
        My plans
        <span
          style={{
            marginLeft: 'auto',
            fontSize: 11,
            fontFamily: 'var(--font-mono)',
            color: planCount > 0 ? 'var(--accent)' : 'var(--ink-4)',
          }}
        >
          {planCount}
        </span>
      </a>

      <div style={{ flex: 1 }} />
      <div style={{ borderTop: '1px solid var(--line)', padding: '12px 10px 4px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', gap: 7, alignItems: 'flex-start' }}>
          <span style={{ flex: 'none', marginTop: 1, color: 'var(--t1)' }}>
            <Ic.shield size={15} />
          </span>
          <div style={{ fontSize: 11, lineHeight: 1.5, color: 'var(--ink-3)' }}>
            Scoped to <span style={{ color: 'var(--ink-2)', fontWeight: 500 }}>{workspaceName}</span>. Brandbiz
            staff can&apos;t read this thread without a logged 4-eyes reveal.
          </div>
        </div>
        <div style={{ fontSize: 11, lineHeight: 1.5, color: 'var(--ink-4)' }}>
          Messages auto-delete after 30 days. Saved plans are kept.
        </div>
      </div>
    </div>
  )
}

function StageRow({ stage, num }: { stage: JourneyStage; num: number }) {
  const dotBase = {
    width: 22,
    height: 22,
    flex: 'none' as const,
    borderRadius: '50%',
    display: 'grid',
    placeItems: 'center',
    fontSize: 10.5,
    fontWeight: 600,
    fontFamily: 'var(--font-mono)',
  }
  const dotStyle =
    stage.state === 'done'
      ? { ...dotBase, background: 'var(--t1)', color: '#fff' }
      : stage.state === 'current'
        ? { ...dotBase, background: 'var(--accent)', color: '#fff', animation: 'glowRing 1.9s ease-in-out infinite' }
        : { ...dotBase, background: 'var(--surface-2)', color: 'var(--ink-4)', border: '1px solid var(--line)' }

  return (
    <div
      style={{
        display: 'flex',
        gap: 10,
        alignItems: 'flex-start',
        padding: '9px 10px',
        borderRadius: 10,
        background: stage.state === 'current' ? 'var(--accent-weak)' : 'transparent',
      }}
    >
      <div style={dotStyle}>
        {stage.state === 'done' ? (
          <Ic.check size={12} strokeWidth={1.7} />
        ) : stage.state === 'current' ? (
          num
        ) : (
          <Ic.lock size={11} strokeWidth={1.7} />
        )}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 13,
            fontWeight: stage.state === 'locked' ? 400 : 600,
            color:
              stage.state === 'done' ? 'var(--ink)' : stage.state === 'current' ? 'var(--accent)' : 'var(--ink-4)',
          }}
        >
          {stage.name}
        </div>
        <div style={{ fontSize: 11, marginTop: 2, color: stage.state === 'locked' ? 'var(--ink-4)' : 'var(--ink-3)' }}>
          {stage.note}
        </div>
      </div>
    </div>
  )
}
