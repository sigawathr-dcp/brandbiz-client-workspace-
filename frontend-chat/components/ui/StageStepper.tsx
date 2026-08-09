import { Ic } from './Icon'

interface StageStepperProps {
  stages: string[]
  labels: Record<string, string>
  current: string
  /** Renders the active step as an error state (red ✕) instead of the normal accent dot. */
  failed?: boolean
}

export default function StageStepper({ stages, labels, current, failed }: StageStepperProps) {
  const idx = stages.indexOf(current)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 0, marginTop: 8 }}>
      {stages.map((s, i) => {
        const done = !failed && i < idx
        const active = i === idx
        const isFailedStep = Boolean(failed) && active
        return (
          <div key={s} style={{ display: 'flex', alignItems: 'center', flex: i < stages.length - 1 ? 1 : 'none' }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
              <div style={{
                width: 18, height: 18, borderRadius: '50%',
                background: isFailedStep ? 'var(--t4)' : done ? 'var(--t1)' : active ? 'var(--accent)' : 'var(--surface-2)',
                border: `2px solid ${isFailedStep ? 'var(--t4)' : done ? 'var(--t1)' : active ? 'var(--accent)' : 'var(--line)'}`,
                display: 'grid', placeItems: 'center', transition: 'all .3s',
              }}>
                {done && <Ic.check size={10} strokeWidth={2.5} style={{ color: '#fff' }} />}
                {isFailedStep && <span style={{ color: '#fff', fontSize: 10, fontWeight: 700, lineHeight: 1 }}>✕</span>}
              </div>
              <span style={{
                fontSize: 9.5, marginTop: 3,
                color: isFailedStep ? 'var(--t4)' : done ? 'var(--t1)' : active ? 'var(--accent)' : 'var(--ink-4)',
                fontWeight: active || done ? 600 : 400, whiteSpace: 'nowrap',
              }}>
                {labels[s] ?? s}
              </span>
            </div>
            {i < stages.length - 1 && (
              <div style={{
                height: 2, flex: 1,
                background: done ? 'var(--t1)' : 'var(--line)',
                margin: '-8px 4px 0', borderRadius: 1, transition: 'background .3s',
              }} />
            )}
          </div>
        )
      })}
    </div>
  )
}
