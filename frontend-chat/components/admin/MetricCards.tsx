import Link from 'next/link'
import { Ic } from '@/components/ui/Icon'
import type { IconProps } from '@/components/ui/Icon'
import type { DashboardMetrics } from '@/lib/admin-api'

type IconDef = (props: IconProps) => React.ReactElement

function Card({ title, value, sub, warn, Icon }: {
  title: string; value: string | number; sub?: string; warn?: boolean; Icon: IconDef
}) {
  return (
    <div style={{
      background: 'var(--surface)',
      border: `1px solid ${warn ? 'var(--warning)' : 'var(--border)'}`,
      borderRadius: 8, padding: '16px 20px', animation: 'fadeUp 0.25s ease',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <span style={{ color: 'var(--muted)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          {title}
        </span>
        <Icon size={14} style={{ color: warn ? 'var(--warning)' : 'var(--muted)', flexShrink: 0 }} />
      </div>
      <div style={{ fontSize: 28, fontWeight: 700, marginTop: 8, color: warn ? 'var(--warning)' : 'var(--text)' }}>
        {value}
      </div>
      {sub && <div style={{ color: 'var(--muted)', fontSize: 11, marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

export default function MetricCards({ m }: { m: DashboardMetrics }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', gap: 16 }}>
      <Card title="Active Users" value={m.active_users.toLocaleString()} sub="is_active = true" Icon={Ic.Users} />
      <Card title="Messages (Month)" value={m.total_messages_month.toLocaleString()} sub={`since ${m.period_start}`} Icon={Ic.MessageSquare} />
      <Card title="External Cost" value={`$${m.external_cost_month_usd.toFixed(2)}`} sub="this month" warn={m.external_cost_month_usd > 0} Icon={Ic.TrendingUp} />
      <Card title="PII Blocks" value={m.pii_blocks_month.toLocaleString()} sub="this month" warn={m.pii_blocks_month > 0} Icon={Ic.Shield} />
      <div style={{ position: 'relative' }}>
        <Card title="Pending Reveals" value={m.pending_reveals.toLocaleString()} warn={m.pending_reveals > 0} Icon={Ic.Eye} />
        {m.pending_reveals > 0 && (
          <Link href="/reveal" style={{ position: 'absolute', bottom: 12, right: 14, fontSize: 11, color: 'var(--warning)', fontWeight: 600 }}>
            Review &rarr;
          </Link>
        )}
      </div>
    </div>
  )
}
