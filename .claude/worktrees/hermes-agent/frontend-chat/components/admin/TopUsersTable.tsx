import type { TopUserItem } from '@/lib/admin-api'

export default function TopUsersTable({ users }: { users: TopUserItem[] }) {
  return (
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>User</th>
          <th style={{ textAlign: 'right' }}>Messages</th>
          <th style={{ textAlign: 'right' }}>Cost (USD)</th>
        </tr>
      </thead>
      <tbody>
        {users.map((u, i) => (
          <tr key={u.user_id}>
            <td style={{ color: 'var(--muted)', width: 32 }}>{i + 1}</td>
            <td>
              <div style={{ fontWeight: 500 }}>{u.display_name || u.email}</div>
              {u.display_name && <div style={{ color: 'var(--muted)', fontSize: 11 }}>{u.email}</div>}
            </td>
            <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
              {u.message_count.toLocaleString()}
            </td>
            <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: u.cost_usd > 0 ? 'var(--warning)' : 'var(--muted)' }}>
              ${u.cost_usd.toFixed(4)}
            </td>
          </tr>
        ))}
        {users.length === 0 && (
          <tr>
            <td colSpan={4} style={{ textAlign: 'center', color: 'var(--muted)', padding: 24 }}>
              No activity this month.
            </td>
          </tr>
        )}
      </tbody>
    </table>
  )
}
