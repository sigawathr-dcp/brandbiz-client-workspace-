/**
 * Fallback for the <main> content area while a layout's auth/session fetch
 * resolves. Scoped to the content pane only — the sidebar renders instantly
 * elsewhere (NavSidebar tolerates `user={null}`), so this must NOT cover the
 * full viewport. Layout-level fetches (e.g. `/auth/me`) block navigation
 * with no visible feedback if awaited directly in the layout body — Next's
 * file-based `loading.tsx` convention does NOT cover a layout's own async
 * work (see https://nextjs.org/docs/app/api-reference/file-conventions/loading).
 * Wrapping just the data-dependent content in an explicit <Suspense
 * fallback={<PageSpinner />}> gives real, instant feedback instead.
 */
export default function PageSpinner() {
  return (
    <div style={{
      height: '100%',
      width: '100%',
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
