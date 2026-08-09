// Unlike the layout-level PageSpinner (components/ui/PageSpinner.tsx), this
// file-based loading.tsx covers the admin pages' OWN data fetching (e.g.
// admin-console's 7 parallel backend calls in lib/admin-api.ts), which run
// after the (admin) layout's auth check has already resolved and NavSidebar
// is already on screen — so this fills the <main> area, not the full viewport.
export default function AdminLoading() {
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
