---
quick_task: 260507-q4i-link-date-references-on-artist-song-and-
type: summary
completed: 2026-05-07
status: complete
key-files:
  modified:
    - src/components/detail/stats-bar.tsx
    - src/components/detail/chart-history-table.tsx
    - src/components/detail/detail-header.tsx
    - src/components/artist/artist-catalog-table.tsx
    - src/app/song/[id]/page.tsx
    - src/app/album/[id]/page.tsx
    - src/app/artist/[id]/page.tsx
decisions:
  - "Widened DetailHeader.subtitle from `string` to `ReactNode` (one-line change) so the artist page can pass linked-date JSX without redesigning DetailHeader."
  - "Defaulted artist subtitle range links to `chart=hot-100` because ArtistStats does not expose first_chart_type / latest_chart_type (confirmed in src/lib/artists.ts)."
  - "Used a reusable inline `chartHref(date)` helper on song and album pages instead of a shared util — the helper is two lines and lives where `detail.chartType` is in scope, avoiding an extra import."
metrics:
  tasks: 3
  commits: 3
---

# Quick Task 260507-q4i: Link Date References on Artist, Song, and Album Pages — Summary

Made every chart-relevant date displayed on song, album, and artist detail pages a hyperlink to the home `/` chart-week view (`?chart={hot-100|billboard-200}&date={YYYY-MM-DD}`), using `next/link` and the existing hover convention (`transition-colors hover:text-[#C8102E]` — no underline, no blue link styling).

## Tasks Completed

### Task 1 — Make shared components link-aware (`b9ce58f7`)

- **`src/components/detail/stats-bar.tsx`**: extended `StatsBarItem` with optional `href?: string`. When `href` is set AND `value !== "—"`, the value renders inside `<Link>` with the hover convention; otherwise renders as the original `<p>`. Length-based font sizing and accent coloring preserved across both branches via a shared `valueClassName`.
- **`src/components/detail/chart-history-table.tsx`**: added required `chartType: ChartType` prop (imported from `@/lib/charts`). Week column now wraps `formatWeek(point.chart_date)` in `<Link href="/?chart={chartType}&date={point.chart_date}">` — note the URL `date=` uses the **raw** `chart_date` (YYYY-MM-DD), not the formatted display string.
- **`src/components/artist/artist-catalog-table.tsx`**: added required `chartType: ChartType` prop. Debut and Last cells render `<Link>` only when the underlying `row.debut_date` / `row.last_date` is non-null; null values render as plain `"—"`. Title-column Link and sort behavior left intact.

### Task 2 — Wire song and album detail pages (`ede9747b`)

- **`src/app/song/[id]/page.tsx`**: added local `chartHref(date)` helper that returns `undefined` for null dates and `/?chart=${detail.chartType}&date=${date}` otherwise. Added `href` to "Debut Date" and "Last Week" StatsBar items. Passed `chartType={detail.chartType}` to `<ChartHistoryTable />`. (`detail.chartType` is `"hot-100"` for songs.)
- **`src/app/album/[id]/page.tsx`**: same pattern — `chartHref` reuses `detail.chartType` (which is `"billboard-200"` for albums). StatsBar Debut Date / Last Week now linkable; `<ChartHistoryTable />` receives `chartType`.
- Other StatsBar items (Peak, Weeks on Chart, Weeks at #1, Weeks at Peak, Debut Position) are not chart-week dates and were left untouched.

### Task 3 — Wire artist detail page (`7274f080`)

- **`src/components/detail/detail-header.tsx`**: widened `subtitle` prop from `string` to `ReactNode` (smallest possible change — added `import type { ReactNode } from "react"` and changed the prop type).
- **`src/app/artist/[id]/page.tsx`**:
  - Added `renderDateRangeNode(start, end)` helper that returns plain text `"Career aggregate detail"` when both dates are null, or `{startNode} – {endNode}` where each node is a `<Link href="/?chart=hot-100&date={raw_date}">` for non-null sides and plain `"—"` for null sides.
  - Replaced the old `formatRange(...)` string in the `<DetailHeader subtitle=…>` prop with the new node helper. Removed `formatRange` (now unused — would have been a lint warning).
  - Passed `chartType="hot-100"` to the "Hot 100 Songs" catalog table and `chartType="billboard-200"` to the "Billboard 200 Albums" catalog table.
- Eight-item StatsBar block (Hot 100 Songs, B200 Albums, #1 Songs, #1 Albums, Hot 100 Weeks, B200 Weeks, Best Hot 100, Max Simultaneous) intentionally left untouched — none of those items are chart-week dates per the plan.

## Component API Confirmation

All three shared components extended additively where possible:

- `StatsBar` — backward-compatible: `href` is optional. Pre-existing call sites compile unchanged.
- `ChartHistoryTable` — `chartType` is **required**. The two call sites (song page, album page) were updated in the same PR.
- `ArtistCatalogTable` — `chartType` is **required**. The two call sites (both inside the artist page) were updated in the same PR.
- `DetailHeader` — `subtitle` widened to `ReactNode`; existing `string` callers (song, album, artist error/loading variants) remain valid because `string` is assignable to `ReactNode`.

## Edge Case Notes

- `DetailHeader.subtitle` widening is the only non-additive shared-component change. It's the smallest possible relaxation — `ReactNode` accepts everything `string` does.
- For null `debut_date` / `last_date` rows in `ArtistCatalogTable`, the cell still calls `formatDate(value)` (which returns `"—"`) — so the visible output is identical to the previous behavior; only the wrapping `<Link>` is conditional.
- The artist subtitle "Career aggregate detail" fallback (both dates null) is preserved unchanged.
- Per the plan and confirmed in `src/lib/artists.ts:46-47`, `ArtistStats` exposes `first_chart_date` / `latest_chart_date` only — no per-side chart-type column — so the artist subtitle defaults both endpoints to `chart=hot-100`.

## URL Shape

All linked dates produce URLs of the form `/?chart={chart-type}&date={YYYY-MM-DD}`, where the date segment is the raw chart_date string from the DB, never the formatted display string. Verified at five sites:

| File                                              | Chart type           | Notes                                |
| ------------------------------------------------- | -------------------- | ------------------------------------ |
| `src/components/detail/chart-history-table.tsx`   | `${chartType}` (var) | Week cell, raw `point.chart_date`    |
| `src/components/artist/artist-catalog-table.tsx`  | `${chartType}` (var) | Debut + Last cells, raw row dates    |
| `src/app/song/[id]/page.tsx`                      | `hot-100` (via var)  | StatsBar Debut Date + Last Week      |
| `src/app/album/[id]/page.tsx`                     | `billboard-200`      | StatsBar Debut Date + Last Week      |
| `src/app/artist/[id]/page.tsx`                    | `hot-100`            | DetailHeader subtitle range nodes    |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Widened `DetailHeader.subtitle` in Task 3 commit**
- **Found during:** Task 3 (the plan called this out as conditional: "If DetailHeader types subtitle as `string` only, widen it to `string | ReactNode`")
- **Issue:** `subtitle: string` rejects the JSX node returned by `renderDateRangeNode`.
- **Fix:** Changed prop type to `ReactNode` (which already includes `string`) and added the `import type { ReactNode } from "react"`.
- **Files modified:** `src/components/detail/detail-header.tsx`
- **Commit:** `7274f080`

**2. [Rule 1 - Cleanup after change] Removed unused `formatRange` helper**
- **Found during:** Task 3, after replacing the subtitle string with the new node helper.
- **Issue:** `formatRange(...)` had no remaining call sites and would have produced a lint/tsc unused-symbol warning.
- **Fix:** Deleted the function in the same Task 3 commit.
- **Files modified:** `src/app/artist/[id]/page.tsx`
- **Commit:** `7274f080`

## Verification

- `npx tsc --noEmit`: passes for everything in this task's scope. The four remaining `error TS2304: Cannot find name 'PageProps'` errors (in `src/app/page.tsx`, `src/app/song/[id]/page.tsx`, `src/app/album/[id]/page.tsx`, `src/app/artist/[id]/page.tsx`) are **pre-existing on the base commit** (verified by stashing this task's diff and re-running tsc — the same four errors appeared). They come from Next.js 16's `.next/types/` declaration files which a bare `tsc --noEmit` invocation does not include without the Next.js plugin. Out of scope for this task; logged here for visibility but not introduced by these changes.
- `npm run lint`: passes (no warnings, no errors).
- No automated component tests exist in this project.

## Deferred Issues

- The four pre-existing `PageProps` tsc errors above. These would be fixed by either running `next dev` / `next build` once (which generates `.next/types/`) and including those types in `tsconfig.json`, or by configuring the Next.js TypeScript plugin in `tsconfig.json`. Not in scope for this quick task.

## Self-Check: PASSED

Files verified to exist:
- `src/components/detail/stats-bar.tsx` — FOUND
- `src/components/detail/chart-history-table.tsx` — FOUND
- `src/components/detail/detail-header.tsx` — FOUND
- `src/components/artist/artist-catalog-table.tsx` — FOUND
- `src/app/song/[id]/page.tsx` — FOUND
- `src/app/album/[id]/page.tsx` — FOUND
- `src/app/artist/[id]/page.tsx` — FOUND

Commits verified in `git log`:
- `b9ce58f7` — FOUND
- `ede9747b` — FOUND
- `7274f080` — FOUND
