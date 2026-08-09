import type { TierKey } from '@/lib/domain'
import { TIERS } from '@/lib/domain'
import Icon from './Icon'

interface TierBadgeProps {
  tier: TierKey
  /** 'badge' = pill with label, 'subtle' = icon + T-number only, 'sm' = small pill */
  mode?: 'badge' | 'subtle' | 'sm'
  size?: 'md' | 'sm'
  /** @deprecated use mode='sm' */
  variant?: 'badge' | 'subtle' | 'sm'
  className?: string
  style?: React.CSSProperties
}

export default function TierBadge({
  tier,
  mode,
  size,
  variant,
  className,
  style,
}: TierBadgeProps) {
  const t = TIERS[tier]
  // Resolve mode: explicit mode > variant > size shorthand
  const resolvedMode = mode ?? (variant === 'sm' ? 'sm' : variant) ?? (size === 'sm' ? 'sm' : 'badge')
  const sm = resolvedMode === 'sm'

  if (resolvedMode === 'subtle') {
    return (
      <span
        className={className}
        title={t.description}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 5, color: t.color, ...style }}
      >
        <Icon name={t.level >= 3 ? 'lock' : 'shield'} size={14} stroke={2} />
        <span style={{ fontSize: 12, fontWeight: 600 }}>T{t.level}</span>
      </span>
    )
  }

  return (
    <span
      className={className}
      title={t.description}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: sm ? '2px 8px' : '3px 10px',
        borderRadius: 99,
        background: t.bg,
        color: t.color,
        fontSize: sm ? 11 : 12,
        fontWeight: 600,
        lineHeight: 1.4,
        whiteSpace: 'nowrap',
        ...style,
      }}
    >
      <Icon name={t.level >= 3 ? 'lock' : 'shield'} size={sm ? 12 : 13} stroke={2.2} />
      T{t.level} · {t.label}
    </span>
  )
}
