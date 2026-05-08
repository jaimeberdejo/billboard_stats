---
phase: quick-260508-mbw
plan: 01
subsystem: api
tags: [postgres, sql-builder, records, custom-query, parameter-binding]

# Dependency graph
requires:
  - phase: quick-260430-e13
    provides: results-count input + custom-query path through getCustomRecords()
provides:
  - Working custom-query Songs/Albums/Artists with multiple comma-separated artists (no more 500 / generic error banner).
  - Reusable SQL-shape regression script at scripts/verify-artist-placeholders.mjs.
affects: [records-view, custom-query, sql-builder, future-records-changes]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "SQL-shape verification via standalone Node mirror (no DB, no Next.js runtime needed)."
    - "Capture-base-before-map pattern for per-iteration $N placeholders in lazy-counter SQL builders."

key-files:
  created:
    - scripts/verify-artist-placeholders.mjs
  modified:
    - src/lib/records.ts

key-decisions:
  - "Mirror builder logic in the verification script rather than importing src/lib/records.ts, to avoid pulling in the Next.js runtime + getSql() DB client."
  - "Capture artistBase before the .map() so each iteration emits its own $N, instead of refactoring placeholder() to be eager."
  - "Leave Site C (artists no-year branch, ~line 593) untouched — it was already correct with `$${index + 2}` and changing it would risk regression."

patterns-established:
  - "Capture-base-before-map: any time a builder uses a lazy `placeholder()` that reads `params.length`, the .map() must capture the base offset BEFORE the map and emit `$${base + index + 1}` per iteration; pushing into params during/after the map keeps subsequent placeholder() calls correct."

requirements-completed:
  - QUICK-260508-MBW

# Metrics
duration: 6min
completed: 2026-05-08
---

# Phase quick-260508-mbw: Fix comma-separated artist input failure Summary

**Fixed comma-separated `artistNames` in custom-query Songs/Albums/Artists by emitting per-iteration `$N` placeholders for the artist ILIKE clause, eliminating the Postgres parameter-count mismatch that surfaced as "Failed to load custom records".**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-05-08T14:09:58Z
- **Completed:** 2026-05-08
- **Tasks:** 2 of 3 executed (Task 3 is human-verify checkpoint, intentionally left for the user)
- **Files modified:** 1
- **Files created:** 1

## Accomplishments
- Fixed Site A (`buildFilters()` for songs/albums) and Site B (artists + year filter) in `src/lib/records.ts`: each artist ILIKE clause now binds its own `$N`, captured from a base offset taken BEFORE the `.map()` so the lazy `placeholder()` callers downstream remain correct after `params.push(...artistValues)`.
- Verified Site C (artists no-year branch, ~line 593) is byte-identical to before — the diff has zero hunks inside its block.
- Added `scripts/verify-artist-placeholders.mjs`, a dependency-free Node script that mirrors both fixed sites and asserts the SQL-shape contract for five scenarios (two-artist solo, two-artist + peakMin, two-artist with offset=1, single-artist, Site B with year-filter prefix). Prints `OK: artist placeholder shape verified` on pass.

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix per-iteration placeholders for artist ILIKE clauses (Sites A and B)** — `c46a25a3` (fix)
2. **Task 2: Programmatic SQL-shape trace for the three artist branches** — `f4efbf59` (test)

**Task 3 (`checkpoint:human-verify`):** Not executed — left for the user to run the dev server and exercise the five UI scenarios listed in the plan. Per orchestrator constraints, this executor stops before the human-verify checkpoint.

## Files Created/Modified
- `src/lib/records.ts` — Two SQL builder hunks at Site A (`buildFilters()`, ~line 549) and Site B (artists + year-filter, ~line 660). Each captures `artistBase` before the artist `.map()` and emits `$${artistBase + index + 1}` per iteration. Site C (~line 593) intentionally untouched.
- `scripts/verify-artist-placeholders.mjs` — Standalone Node regression script mirroring both fixed builders. Five `node:assert/strict` scenarios; `node scripts/verify-artist-placeholders.mjs` prints `OK: artist placeholder shape verified` on pass.

## Decisions Made
- **Mirror over import in the verification script.** Importing `src/lib/records.ts` would pull in Next.js module resolution and `getSql()` (DB client). The mirror keeps the regression check deterministic, hermetic, and runnable any time without standing up a JS test harness.
- **Capture-base-before-map (chosen) vs. eager placeholder() (rejected).** Refactoring `placeholder()` to push first / read after would have meant restructuring every call site (peakMin, peakMax, weeksMin, debutPosMin/Max, the LIMIT clause) — a much bigger blast radius than the bug warranted. The capture-base pattern fixes only the buggy callsites and leaves all other `placeholder()` consumers alone.
- **Site C untouched.** It already used the hardcoded `$${index + 2}` form (because `chart` reserves `$1`); changing it would have required converting both branches to the same pattern, increasing diff surface for no behavioral gain. Site C documented in the plan as a regression guard.

## Deviations from Plan

None — plan executed exactly as written. The only off-plan effort was diagnosing that the previous edits had landed in the main checkout instead of the worktree (resolved by reverting the main checkout file and re-applying the edits in `.claude/worktrees/agent-a21609df313d10faf/`); no production code or behavior was affected.

## Issues Encountered

- **Pre-existing TypeScript errors in unrelated files.** `npx tsc --noEmit` reports four `Cannot find name 'PageProps'` errors in `src/app/{album,artist,song}/[id]/page.tsx` and `src/app/page.tsx`. These existed at HEAD (`6ca6a559`) before any edits in this task — confirmed by stashing the records.ts change and re-running tsc. They are unrelated to the artist-placeholder bug and out of scope per the executor's scope-boundary rule. Logged at `.planning/quick/260508-mbw-fix-comma-separated-artist-input-failure/deferred-items.md` for follow-up.
- **Worktree path drift (resolved).** Initial edits inadvertently targeted the main checkout (`/Users/jaimeberdejosanchez/projects/billboard_stats/src/lib/records.ts`) instead of the per-agent worktree path. Detected via `git diff` showing no changes despite a clearly modified file. Resolved by `git checkout -- src/lib/records.ts` in the main checkout and re-applying both Edits at the worktree path. The main checkout's pre-existing dirty file (`src/components/charts/chart-controls.tsx`) was not touched; net effect on main checkout is zero.

## Verification
- `npx eslint src/lib/records.ts` → clean (no output).
- `node scripts/verify-artist-placeholders.mjs` → `OK: artist placeholder shape verified`.
- `git diff` on `src/lib/records.ts` shows changes ONLY at Site A (`@@ -547,7 +547,11 @@`) and Site B (`@@ -655,7 +659,12 @@`); Site C around line 593 has zero hunks. (`grep -n "artistValues.map"` post-fix returns three matches; the only single-line match is Site C's pre-existing `(_, index) => \`a.name ILIKE $${index + 2}\``.)
- `npx tsc --noEmit`: 4 pre-existing `PageProps` errors in unrelated files (see Issues Encountered); no new errors introduced by this change.
- **Manual UI verification (Task 3):** intentionally NOT executed by the executor — left for the user. The plan lists five scenarios (Songs/Albums/Artists with `Katy, Taylor`, plus single-artist and year-filter regression checks) plus a `curl` against `/api/records?...artistNames=Katy%2C%20Taylor`.

## User Setup Required

None — no external service configuration required.

## Self-Check: PASSED

- File `src/lib/records.ts`: FOUND (modified)
- File `scripts/verify-artist-placeholders.mjs`: FOUND (created)
- Commit `c46a25a3` (Task 1 fix): FOUND in `git log`
- Commit `f4efbf59` (Task 2 verification script): FOUND in `git log`
- `node scripts/verify-artist-placeholders.mjs` exit 0 with expected output

## Next Phase Readiness

Ready for human verification (Task 3). Once the user runs `npm run dev` and confirms the five scenarios return rows with no error banner (and the curl returns a `rows` array), the orchestrator can produce the docs commit covering this SUMMARY.md, the PLAN.md, and STATE.md.

---
*Phase: quick-260508-mbw*
*Completed: 2026-05-08*
