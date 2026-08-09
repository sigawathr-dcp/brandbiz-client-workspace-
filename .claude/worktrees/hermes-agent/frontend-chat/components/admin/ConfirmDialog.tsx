'use client'

interface Props {
  title: string
  description: string
  onConfirm: () => void
  onCancel: () => void
  confirmLabel?: string
  confirmClass?: string
}

export default function ConfirmDialog({
  title, description, onConfirm, onCancel,
  confirmLabel = 'Confirm', confirmClass = 'primary',
}: Props) {
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 200,
      background: 'rgba(0,0,0,0.7)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 12, padding: 28, width: 420, maxWidth: '90vw',
      }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 10 }}>{title}</h2>
        <p style={{ color: 'var(--muted)', fontSize: 13, marginBottom: 24, whiteSpace: 'pre-wrap' }}>
          {description}
        </p>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button className="ghost" onClick={onCancel}>Cancel</button>
          <button className={confirmClass} onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  )
}
