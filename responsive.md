# Make the app responsive

## Status: already implemented and verified

All steps below are **complete in the working tree** (uncommitted). Verified by direct file reads:

- `AuditTable.tsx:107` — wrapper now `overflowX: 'auto'` ✔
- `TopUsersTable.tsx:5` — `<table>` wrapped in `<div style={{ overflowX: 'auto' }}>` ✔
- `PlanRating.tsx:126` — inline `gridTemplateColumns` replaced with `className="client-nps-grid"` ✔
- `globals.css:419` (`repeat(10, 1fr)` base) and `globals.css:521` (`@media (max-width: 480px)` →
  `repeat(5, 1fr)`) ✔

Verification also already done in a real browser (logged in as the seeded mock admin, exact-width
iframe harness at 390px/800px, plus a temporary — since deleted — component-harness page for the
auth-gated admin tables): NPS grid computes 5 columns at 390px / 10 at 800px; both admin tables
report `overflow-x: auto` with `scrollWidth > clientWidth` (they scroll instead of clipping).
`docker compose build frontend-chat` (a full `next build`) passed cleanly twice.

**Remaining work: none.** The only optional follow-up is committing the changed files
(`app/globals.css`, `components/admin/AuditTable.tsx`, `components/admin/TopUsersTable.tsx`,
`components/client/PlanRating.tsx`) if desired.

---

## Context

The request was "make this app responsive" for the whole `frontend-chat` Next.js app. Investigation
(background Explore agent + direct reads of the flagged files) found this is **not a greenfield
task** — two full responsive shell systems already exist and are well-engineered:

- **Internal app shell** (`ResponsiveShell.tsx` + `NavSidebar.tsx`, used by `/chat`, `/studio`,
  `/tasks`, `/skills`, `/agent`, `/library`, and all `(admin)` routes): sidebar + main on desktop,
  off-canvas drawer + hamburger topbar at ≤768px (`globals.css:224-306`).
- **Client Workspaces shell** (`ClientWorkspace.tsx`, used by `/w`, `/w/plans*`, not on
  `ResponsiveShell`): a 3-column grid (nav rail / chat / work panel) that degrades in two stages —
  nav rail becomes an off-canvas drawer at ≤1180px, then the whole grid collapses to one column
  with the work panel also going off-canvas at ≤768px (`globals.css:308-510`).

Both systems follow one deliberate, documented convention: components are styled almost entirely
with inline `style={{}}` (reading CSS custom-property design tokens), **except** the specific
layout properties that must flip at a breakpoint — those live in a named class in `globals.css` so
the `@media` rule can win (inline styles always beat class-based media queries). `viewport` meta is
already correctly configured in `app/layout.tsx`. `lib/useIsMobile.ts` mirrors the 768px breakpoint
in JS for components that need it in React logic, not just CSS (`ChatPane`, `StudioPage`,
`AboutModal`, `CreateAgentForm`, `SkillsPage`).

So this pass is a **gap-closing audit**: keep the existing conventions and breakpoints intact, find
and fix the handful of places that were never brought into the responsive system. Direct
verification turned up three concrete, confirmed gaps:

1. **`components/admin/AuditTable.tsx`** (`frontend-chat/components/admin/AuditTable.tsx:107`) —
   the table's wrapper div used `overflow: 'hidden'`, not `overflow-x: auto`. On a narrow viewport
   the multi-column audit table (action, user, timestamp, IP, details, etc.) would just get clipped
   instead of horizontally scrolling. Every other admin table (`UsersTable.tsx`,
   `ClientDetailPage.tsx`, the table in `AdminConsole.tsx`) already wraps its `<table>` in
   `overflowX: 'auto'` — this one was missed.
2. **`components/admin/TopUsersTable.tsx`** — the `<table>` had **no wrapper div at all**, so there
   was nothing to catch horizontal overflow on narrow screens. Same fix pattern as above.
3. **`components/client/PlanRating.tsx:126`** — the 1-10 NPS score buttons used a fixed
   `gridTemplateColumns: 'repeat(10,1fr)'` inline style. On a phone (≤480px), ten buttons with a
   6px gap end up only ~26-28px wide each — usable but cramped, and it was the one interactive
   surface in the client shell with zero small-screen adjustment. Since `PlanRating.tsx` otherwise
   uses inline styles exclusively, this needed the same treatment as the rest of the codebase: pull
   just the grid property into a new named class (`.client-nps-grid`) in `globals.css`, then add a
   `@media (max-width: 480px)` rule dropping it to `repeat(5,1fr)` (two rows of 5) so each button
   stays comfortably tappable.

No other confirmed gaps were found: `MetricCards.tsx`/`AdminConsole.tsx`'s dashboard card grids
already use `repeat(auto-fill, minmax(...))`, which is inherently responsive; the login page,
`/try/<token>` (`RedeemInvite.tsx`), and `/p/<token>` (`SharedPlanView.tsx`) are simple
centered/fluid layouts with no fixed-width traps; `PlanDraftCard.tsx`'s budget table is a plain
2-column table inside an already-responsive 640px-max chat bubble and doesn't need its own
breakpoint.

## Implementation (all done)

1. **`frontend-chat/components/admin/AuditTable.tsx`** — changed the wrapper div's
   `overflow: 'hidden'` to `overflowX: 'auto'` so the table scrolls horizontally instead of
   clipping on narrow screens.
2. **`frontend-chat/components/admin/TopUsersTable.tsx`** — wrapped the existing
   `<table>...</table>` in a `<div style={{ overflowX: 'auto' }}>`, matching the pattern already
   used in `UsersTable.tsx`.
3. **`frontend-chat/app/globals.css`** — added near the other `.client-*` rules:
   ```css
   .client-nps-grid {
     grid-template-columns: repeat(10, 1fr);
   }
   ```
   and a new media block:
   ```css
   @media (max-width: 480px) {
     .client-nps-grid {
       grid-template-columns: repeat(5, 1fr);
     }
   }
   ```
4. **`frontend-chat/components/client/PlanRating.tsx:126`** — replaced the inline
   `gridTemplateColumns: 'repeat(10,1fr)'` with `className="client-nps-grid"` on that div
   (keeping `display: 'grid'`, `gap: 6`, and the `onMouseLeave` handler as-is).

## Verification (done)

Real-browser verification, not just type-checking:

- Logged in at `http://localhost:3100` as the seeded mock admin
  (`backend/scripts/seed_mock_users.py`).
- Because the OS-maximized Chrome window ignored `resize_window`, an **iframe harness** was used:
  a same-origin `<iframe>` injected at exact CSS pixel widths (390px / 800px) pointing at the real
  authenticated page.
- `PlanRating` on a real saved plan page: computed `grid-template-columns` = 5 equal ~51px columns
  at 390px, 10 equal columns at 800px. Confirmed by screenshot and `getComputedStyle`.
- Admin tables are auth-gated behind tenant routing in this environment, so a temporary throwaway
  route rendered the real `AuditTable`/`TopUsersTable` with mock data: both wrappers computed
  `overflow-x: auto` with `scrollWidth > clientWidth` at 390px (629px table in a 352px box; 407px
  in a 354px box). The throwaway route was deleted afterward and its absence confirmed via
  `git status`.
- Note: the `frontend-chat` container is a baked production standalone image (no volume mount, no
  hot reload) — code changes require `docker compose build frontend-chat && docker compose up -d
  frontend-chat` to take effect. Both rebuilds during verification compiled cleanly.

No regressions observed in the existing responsive behavior (`/chat` drawer at ≤768px, `/w`
nav-rail drawer at ≤1180px, work-panel drawer at ≤768px).

---

## Follow-up fix (2026-08-10): "Market scan" / "Plan & budget" clicks broke the layout

User report: clicking the **Market scan** and **Plan & budget** chapters in the `/w` journey rail
made the app "not responsive".

**Root cause** (desktop/tablet, >768px): `.client-navrail` and `.client-workpanel` are grid items
in `.client-grid`, and grid items default to `min-height: auto` (= content height). Clicking
"Market scan" switches the work panel to the Research tab, whose content (e.g. 41 findings +
20 sources) stretched the 372px column to ~5600px tall — past the viewport-bounded track. The
panel's internal `overflowY: auto` scroller then never activated (`scrollHeight === clientHeight`),
so everything below the fold was unreachable and wheel-scrolling did nothing. It also blew the
outer 100vh `overflow: hidden` shell's scrollHeight out to ~5600px, so the `scrollIntoView` used
by chapter navigation ("Plan & budget" scrolls to the plan card) scrolled that shell too and
visually corrupted the whole page. The chat column was immune only because it already carried an
inline `minHeight: 0`.

**Fix:**
- `frontend-chat/app/globals.css` — added `min-height: 0` to `.client-navrail` and
  `.client-workpanel`, plus `overflow-y: auto` on `.client-navrail` (the journey rail had no
  scroll container at all, so on short viewports — e.g. a 667px-tall phone — its footer was
  clipped and unreachable).
- `frontend-chat/components/client/NavRail.tsx` — root `height: '100%'` → `minHeight: '100%'` so
  the rail grows with content and the wrapper scrolls it.

**Verified** (real browser, rebuilt Docker image):
- Desktop 1464px: after clicking "Market scan", panel height is track-bounded, page
  `scrollHeight === clientHeight` (no blowout), internal scroller scrolls (5652px of content in a
  956px box), layout intact in screenshots. "Plan & budget" navigates to `/w/plans/<id>`.
- 390×667 iframe harness: journey drawer opens (x −386→0) and scrolls (739px content in 663px),
  "Market scan" closes it and slides in the work panel (x 386→0) showing Research with a working
  scroller; ✕ closes it; "Plan & budget" navigates to the saved plan.
- Note for future browser verification: when the Chrome window is hidden/minimized, tabs get no
  frames — CSS transitions freeze at their from-value and CDP screenshots time out. Disable the
  element's `transition` before measuring end states, or make sure the window is visible.
