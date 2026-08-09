import type { ModelUsageItem } from '@/lib/admin-api'

export default function ModelUsageBars({ items }: { items: ModelUsageItem[] }) {
  if (items.length === 0) {
    return <p style={{ color: 'var(--muted)', fontSize: 13 }}>No external API usage this month.</p>
  }
  const maxCost = Math.max(...items.map(i => i.cost_usd), 0.0001)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {items.map(item => (
        <div key={item.model_code}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: 12 }}>
            <span style={{ fontWeight: 500 }}>{item.model_code}</span>
            <span style={{ color: 'var(--muted)' }}>
              {item.message_count.toLocaleString()} msgs &nbsp;·&nbsp;
              {(item.tokens_input + item.tokens_output).toLocaleString()} tok &nbsp;·&nbsp;
              <span style={{ color: item.cost_usd > 0 ? 'var(--warning)' : 'var(--muted)' }}>
                ${item.cost_usd.toFixed(4)}
              </span>
            </span>
          </div>
          <div style={{ background: 'var(--border)', borderRadius: 4, height: 6 }}>
            <div style={{
              background: 'var(--accent)', height: 6, borderRadius: 4,
              width: `${Math.max((item.cost_usd / maxCost) * 100, item.cost_usd > 0 ? 2 : 0)}%`,
            }} />
          </div>
        </div>
      ))}
    </div>
  )
}
