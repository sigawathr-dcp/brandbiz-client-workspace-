/**
 * ProviderMark — text-mark glyph in a rounded square.
 * Local model gets an accent-coloured "Q"; external providers
 * get the first letter of provider name on a neutral background.
 */

interface ProviderMarkProps {
  provider: string
  isLocal?: boolean
  size?: number
  className?: string
}

export default function ProviderMark({ provider, isLocal, size = 26, className }: ProviderMarkProps) {
  const local = isLocal ?? provider.toLowerCase() === 'local'
  const letter = local ? 'Q' : provider.charAt(0).toUpperCase()

  return (
    <div
      className={className}
      style={{
        width: size,
        height: size,
        flex: 'none',
        borderRadius: Math.round(size * 0.28),
        display: 'grid',
        placeItems: 'center',
        fontFamily: 'var(--font-mono)',
        fontWeight: 600,
        fontSize: Math.round(size * 0.42),
        background: local ? 'var(--accent-weak)' : 'var(--surface-2)',
        color: local ? 'var(--accent)' : 'var(--ink-2)',
        border: '1px solid var(--line)',
        userSelect: 'none',
      }}
    >
      {letter}
    </div>
  )
}
