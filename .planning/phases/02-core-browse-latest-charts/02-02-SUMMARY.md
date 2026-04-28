---
phase: 02-core-browse-latest-charts
plan: 02
subsystem: api
tags: [typescript, nextjs, postgresql, neon, charts, data-status]

requires:
  - phase: 01-project-setup-infrastructure
    provides: Neon db connection via src/lib/db.ts, Next.js App Router scaffold
provides:
  - TypeScript chart helpers (getWeeklyChart, getAvailableDates) mirroring Python chart_service.py
  - TypeScript data-status helper (getDataSummary) mirroring Python data_status_service.py
  - /api/charts route handler with chart type + date validation
  - /api/data-status route handler with aggregate counts and latest dates
affects: [core-browse-latest-charts-03, detail-pages-visualizations, search-records]

tech-stack:
  added: []
  patterns: [server-side SQL via Neon getSql, validated route handler pattern, typed chart entry contract]

key-files:
  created:
    - src/lib/charts.ts
    - src/lib/data-status.ts
    - src/app/api/charts/route.ts
    - src/app/api/data-status/route.ts
  modified: []

key-decisions:
  - "Route handlers delegate all SQL to shared lib helpers — no inline queries"
  - "chart type restricted to hot-100 | billboard-200 at the route level (400 on invalid)"
  - "Phantom-week detection implemented in charts.ts to match Python behavior"

patterns-established:
  - "Validated route handler: parse params → validate → call lib helper → return typed JSON"
  - "Shared lib helper owns SQL; route owns HTTP contract"

requirements-completed:
  - BROWSE-03
  - BROWSE-05

duration: 8min
completed: 2026-04-28
---

# Phase 02-02: Chart & Data-Status APIs Summary

**Ported Python chart and data-status services to typed TypeScript helpers and validated Next.js route handlers.**

## Performance

- **Duration:** ~8 min
- **Completed:** 2026-04-28
- **Tasks:** 2/2
- **Files modified:** 4

## Accomplishments

1. **`src/lib/charts.ts`** — `getWeeklyChart()` and `getAvailableDates()` typed helpers. Supports `hot-100` and `billboard-200`. Returns `{ entries, availableDates, latestDate }`. Includes phantom-week filtering matching Python behavior.
2. **`src/lib/data-status.ts`** — `getDataSummary()` returns aggregate counts (`chart_weeks`, `hot100_entries`, `b200_entries`, `songs`, `albums`, `artists`, `song_stats`, `album_stats`, `artist_stats`) and grouped latest chart dates.
3. **`src/app/api/charts/route.ts`** — GET handler validating `chart` (hot-100|billboard-200) and optional `date` (YYYY-MM-DD). Returns `{ chartType, selectedDate, latestDate, availableDates, entries }`. Returns 400 on invalid input, 500 on DB failure.
4. **`src/app/api/data-status/route.ts`** — GET handler returning `{ counts, latestDates, chart_weeks, songs, albums, artists, hot100_entries, b200_entries }`.

## Self-Check: PASSED

- ✓ `npm run build` — clean, /api/charts and /api/data-status appear as dynamic routes
- ✓ All acceptance criteria met (hot-100, billboard-200, availableDates, latestDate, selectedDate, 400, latestDates, chart_weeks)
- ✓ No inline SQL in route handlers — lib helpers own all queries
- ✓ No STATE.md or ROADMAP.md modified
