---
phase: 02-core-browse-latest-charts
plan: 01
subsystem: ui
tags: [nextjs, react, tailwind, navigation, app-router]

# Dependency graph
requires:
  - phase: 01-project-setup
    provides: Next.js App Router scaffold with Tailwind v4, Space Grotesk font, and root layout
provides:
  - Shared SiteShell component wrapping all routes with desktop sticky top nav and mobile bottom nav
  - PrimaryNav client component with pathname-derived active state for four browse destinations
  - MobileBottomNav client component with fixed bottom bar visible below sm breakpoint
  - Routable placeholder pages for /search, /records, and /status
affects: [02-02, 02-03, 03, 04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Client component island for pathname-aware nav (usePathname inside 'use client' boundary)"
    - "SiteShell wrapper in root layout keeps nav outside page-specific layouts"
    - "Tailwind sm: breakpoint switches desktop nav / hides mobile nav"

key-files:
  created:
    - src/components/shell/site-shell.tsx
    - src/components/shell/primary-nav.tsx
    - src/components/shell/mobile-bottom-nav.tsx
    - src/app/search/page.tsx
    - src/app/records/page.tsx
    - src/app/status/page.tsx
  modified:
    - src/app/layout.tsx

key-decisions:
  - "usePathname placed in client components (primary-nav, mobile-bottom-nav) not in the server layout — required by Next.js 16 App Router (layouts do not re-render on navigation)"
  - "SiteShell is a server component; only the nav child components carry the 'use client' directive — keeps shell lightweight (TM-02-02 mitigation)"
  - "status/page.tsx ships as a skeleton with no fetch() calls — live data deferred to Plan 03"
  - "search and records pages are explicit Phase 4 placeholders with links back to Latest Charts"

patterns-established:
  - "Pattern: client nav island — extract usePathname into a client sub-component imported by the server shell"
  - "Pattern: mobile bottom nav uses fixed positioning with pb-14 on main to prevent content overlap"

requirements-completed: [CORE-04]

# Metrics
duration: 3min
completed: 2026-04-28
---

# Phase 2 Plan 01: Browse Shell and Navigation Summary

**Shared SiteShell with sticky desktop top nav and mobile fixed bottom nav, plus routable placeholder pages for Search, Records, and Data Status**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-28T16:36:45Z
- **Completed:** 2026-04-28T16:39:09Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Built SiteShell wrapping all routes: 44px sticky top header (desktop) plus fixed bottom nav (mobile, below sm)
- PrimaryNav and MobileBottomNav derive active state from `usePathname` in client components, satisfying TM-02-01 (no mutable client flags)
- Search, Records, and Data Status are all routable — no broken nav targets
- Data Status skeleton ships without any `fetch()` calls — ready for Plan 03 to wire live data

## Task Commits

Each task was committed atomically:

1. **Task 1: Build shared phase 2 site shell** - `246b5c38` (feat)
2. **Task 2: Add routable placeholder browse pages** - `6acfecdd` (feat)

## Files Created/Modified
- `src/components/shell/site-shell.tsx` - Server component shell; renders sticky header + main + mobile nav
- `src/components/shell/primary-nav.tsx` - Client component; sticky top nav links with usePathname active state
- `src/components/shell/mobile-bottom-nav.tsx` - Client component; fixed bottom nav visible below sm breakpoint
- `src/app/layout.tsx` - Updated root layout to wrap children in SiteShell
- `src/app/search/page.tsx` - Phase 4 placeholder with link to Latest Charts
- `src/app/records/page.tsx` - Phase 4 placeholder with link to Latest Charts
- `src/app/status/page.tsx` - Data Status skeleton (no fetch) for Plan 03 to populate

## Decisions Made
- `usePathname` kept inside client component boundaries only — Next.js 16 App Router layouts are server components that do not re-render on navigation, so pathname must be read in a client island
- Shell itself is a server component (no `'use client'`) to keep the nav wrapper lightweight and avoid blocking fetches (TM-02-02 mitigation)
- status/page.tsx intentionally ships with skeleton UI and dashes (—) — Plan 03 will replace with live DB data

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

- `src/app/status/page.tsx`: Stats bar and table cells render `—` as placeholder values. This is intentional — Plan 03 will replace with live database reads. The plan explicitly states "Plan 03 will replace with live content; do not implement database reads here yet."

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Navigation shell is locked in for all four Phase 2 destinations
- All routes render successfully under the shared shell
- Plan 02-02 (Latest Charts page) and Plan 02-03 (Data Status) can now build their page content knowing the shell contract is stable
- No blockers

---
*Phase: 02-core-browse-latest-charts*
*Completed: 2026-04-28*
