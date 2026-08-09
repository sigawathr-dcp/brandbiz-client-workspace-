export default function ChatConversationLoading() {
  return (
    <div style={{
      height: '100%',
      display: 'grid',
      placeItems: 'center',
    }}>
      <div style={{
        width: 22,
        height: 22,
        border: '3px solid var(--line)',
        borderTopColor: 'var(--accent)',
        borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
      }} />
    </div>
  )
}
