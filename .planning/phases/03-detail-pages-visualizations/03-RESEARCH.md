# Phase 3: Detail Pages & Visualizations - Research

**Researched:** 2026-04-28  
**Domain:** Next.js App Router entity detail pages backed by PostgreSQL stats tables and chart-run history queries [VERIFIED: .planning/ROADMAP.md] [VERIFIED: billboard_stats/db/schema.sql]  
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

No CONTEXT.md exists for this phase, so there are no locked user decisions beyond the roadmap, requirements, UI spec, and project instructions. [VERIFIED: gsd-sdk init.phase-op has_context=false] [VERIFIED: .planning/ROADMAP.md] [VERIFIED: .planning/REQUIREMENTS.md] [VERIFIED: .planning/phases/03-detail-pages-visualizations/03-UI-SPEC.md]
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DETAILS-01 | Song detail page with stats bar and artist pill links [VERIFIED: .planning/REQUIREMENTS.md] | Use `songs`, `song_stats`, `song_artists`, and `artists`; reuse the legacy `get_song()` + `get_chart_run()` split in TypeScript. [VERIFIED: billboard_stats/services/song_service.py] [VERIFIED: billboard_stats/db/schema.sql] |
| DETAILS-02 | Album detail page with stats bar and artist pill links [VERIFIED: .planning/REQUIREMENTS.md] | Use `albums`, `album_stats`, `album_artists`, and `artists`; mirror the legacy album service shape in TypeScript. [VERIFIED: billboard_stats/services/album_service.py] [VERIFIED: billboard_stats/db/schema.sql] |
| DETAILS-03 | Artist detail page with career aggregates and Hot 100/B200 tables [VERIFIED: .planning/REQUIREMENTS.md] | Use `artist_stats` for aggregates and separate song/album list queries for tables. [VERIFIED: billboard_stats/services/artist_service.py] [VERIFIED: billboard_stats/db/schema.sql] |
| DETAILS-04 | Week-by-week chart history table for songs and albums [VERIFIED: .planning/REQUIREMENTS.md] | Reuse the chronological chart-run queries, then render newest-first in UI to match the UI contract. [VERIFIED: billboard_stats/services/song_service.py] [VERIFIED: billboard_stats/services/album_service.py] [VERIFIED: .planning/phases/03-detail-pages-visualizations/03-UI-SPEC.md] |
| DETAILS-05 | Inline SVG chart run visualization with inverted Y-axis and peak annotation [VERIFIED: .planning/REQUIREMENTS.md] | Build a dedicated client visualization component fed by server-fetched chart history; only render when at least two points exist. [VERIFIED: .planning/phases/03-detail-pages-visualizations/03-UI-SPEC.md] [VERIFIED: BillboardStats.html] |
</phase_requirements>

## Summary

Phase 3 should be planned as three server-rendered entity routes, not as one generic “detail page” abstraction. The current app already uses server-first pages with small client islands, and the legacy Python app already defines separate data contracts for song, album, and artist detail surfaces. [VERIFIED: src/app/page.tsx] [VERIFIED: src/components/charts/latest-charts-view.tsx] [VERIFIED: billboard_stats/services/song_service.py] [VERIFIED: billboard_stats/services/album_service.py] [VERIFIED: billboard_stats/services/artist_service.py]

The database shape is favorable for this phase because the stats needed by the UI are already precomputed in `song_stats`, `album_stats`, and `artist_stats`, while weekly history remains queryable from `hot100_entries` and `b200_entries`. The main planning risk is not SQL invention; it is preserving the legacy phantom-week filtering and keeping the UI contract aligned with the approved dense newsroom spec. [VERIFIED: billboard_stats/db/schema.sql] [VERIFIED: billboard_stats/etl/stats_builder.py] [VERIFIED: src/lib/charts.ts] [VERIFIED: .planning/phases/03-detail-pages-visualizations/03-UI-SPEC.md]

The cleanest implementation plan is: server route per entity type, shared TypeScript service helpers per entity domain, plain semantic tables for history/drill-down, and a single small client component for the collapsible SVG chart-run visualization. [CITED: node_modules/next/dist/docs/01-app/01-getting-started/03-layouts-and-pages.md] [CITED: node_modules/next/dist/docs/01-app/01-getting-started/06-fetching-data.md] [VERIFIED: src/components/charts/chart-table.tsx] [VERIFIED: BillboardStats.html]

**Primary recommendation:** Plan Phase 3 around `/songs/[id]`, `/albums/[id]`, and `/artists/[id]` server pages with thin data helpers in `src/lib`, plus one reusable client-side SVG visualization component for song/album runs. [CITED: node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/dynamic-routes.md] [VERIFIED: src/components/charts/chart-table.tsx] [VERIFIED: billboard_stats/services/song_service.py] [VERIFIED: billboard_stats/services/album_service.py] [VERIFIED: billboard_stats/services/artist_service.py]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Entity route resolution and initial detail render | Frontend Server [CITED: node_modules/next/dist/docs/01-app/01-getting-started/03-layouts-and-pages.md] | Database / Storage [CITED: node_modules/next/dist/docs/01-app/01-getting-started/06-fetching-data.md] | The existing app already fetches page data in server components, and detail pages should follow the same pattern for direct loads and metadata. [VERIFIED: src/app/page.tsx] [CITED: node_modules/next/dist/docs/01-app/03-api-reference/04-functions/generate-metadata.md] |
| Song and album aggregate stats | Database / Storage [VERIFIED: billboard_stats/db/schema.sql] | Frontend Server [CITED: node_modules/next/dist/docs/01-app/01-getting-started/06-fetching-data.md] | `song_stats` and `album_stats` already own peak, weeks, debut, and related aggregate fields. [VERIFIED: billboard_stats/db/schema.sql] |
| Artist career aggregates | Database / Storage [VERIFIED: billboard_stats/db/schema.sql] | Frontend Server [VERIFIED: billboard_stats/services/artist_service.py] | `artist_stats` is the canonical source for cross-chart totals and `max_simultaneous_hot100`. [VERIFIED: billboard_stats/db/schema.sql] [VERIFIED: billboard_stats/etl/stats_builder.py] |
| Week-by-week chart history | Database / Storage [VERIFIED: billboard_stats/services/song_service.py] | Frontend Server [VERIFIED: billboard_stats/services/album_service.py] | Weekly rows come from entry tables joined to `chart_weeks`, then the page renders them newest-first. [VERIFIED: billboard_stats/services/song_service.py] [VERIFIED: billboard_stats/services/album_service.py] [VERIFIED: .planning/phases/03-detail-pages-visualizations/03-UI-SPEC.md] |
| Chart-run collapse/expand interaction | Browser / Client [VERIFIED: BillboardStats.html] | Frontend Server [VERIFIED: .planning/phases/03-detail-pages-visualizations/03-UI-SPEC.md] | Only the toggle and inline SVG need client state; the data itself should arrive from the server. [VERIFIED: BillboardStats.html] [CITED: node_modules/next/dist/docs/01-app/01-getting-started/06-fetching-data.md] |
| Navigation between chart rows and detail pages | Browser / Client [CITED: node_modules/next/dist/docs/01-app/03-api-reference/02-components/link.md] | Frontend Server [CITED: node_modules/next/dist/docs/01-app/01-getting-started/03-layouts-and-pages.md] | Use `next/link` from browse/artist tables into dynamic detail routes. [VERIFIED: src/components/shell/primary-nav.tsx] [CITED: node_modules/next/dist/docs/01-app/03-api-reference/02-components/link.md] |

## Project Constraints (from CLAUDE.md)

- Read the relevant guide in `node_modules/next/dist/docs/` before changing Next.js code because this repo treats the installed Next.js version as authoritative over training knowledge. [VERIFIED: AGENTS.md] [VERIFIED: CLAUDE.md]
- Heed deprecation notices in the installed Next.js docs while planning and implementing this phase. [VERIFIED: AGENTS.md]
- Preserve the existing no-component-library approach; the approved UI contract for this phase explicitly forbids introducing shadcn, Radix, or card-heavy dashboard patterns. [VERIFIED: .planning/phases/03-detail-pages-visualizations/03-UI-SPEC.md]

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Next.js | `16.2.4` published state verified 2026-04-28 [VERIFIED: package.json] [VERIFIED: npm registry] | App Router dynamic routes, server pages, metadata, and `notFound()` handling [CITED: node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/dynamic-routes.md] [CITED: node_modules/next/dist/docs/01-app/03-api-reference/04-functions/generate-metadata.md] [CITED: node_modules/next/dist/docs/01-app/03-api-reference/04-functions/not-found.md] | Already installed and already used for server-first page rendering in Phase 2. [VERIFIED: package.json] [VERIFIED: src/app/page.tsx] |
| React | `19.2.4` installed, `19.2.5` latest registry patch as of 2026-04-28 [VERIFIED: package.json] [VERIFIED: npm registry] | Client island for visualization toggle and SVG rendering [VERIFIED: src/components/charts/latest-charts-view.tsx] | Existing app already uses React client components for small interactive islands. [VERIFIED: src/components/charts/latest-charts-view.tsx] |
| `@neondatabase/serverless` | `1.1.0` published 2026-04-17 [VERIFIED: package.json] [VERIFIED: npm registry] | Direct Postgres access from server components and route helpers [VERIFIED: src/lib/db.ts] | This is the current database adapter in the app. [VERIFIED: src/lib/db.ts] |
| Tailwind CSS | `4.2.4` published 2026-04-28 [VERIFIED: package.json] [VERIFIED: npm registry] | Dense CSS utility styling consistent with the existing UI tokens [VERIFIED: src/app/globals.css] | The app already uses Tailwind v4 theme tokens in CSS instead of a component kit. [VERIFIED: src/app/globals.css] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `next/link` | bundled with Next.js [CITED: node_modules/next/dist/docs/01-app/03-api-reference/02-components/link.md] | Link browse rows, artist pills, and artist drill-down tables into entity routes [VERIFIED: src/components/shell/primary-nav.tsx] | Use for all route transitions instead of `onClick` navigation wrappers. [CITED: node_modules/next/dist/docs/01-app/03-api-reference/02-components/link.md] |
| `next/navigation` `notFound()` | bundled with Next.js [CITED: node_modules/next/dist/docs/01-app/03-api-reference/04-functions/not-found.md] | Route-level missing entity handling with `noindex` behavior [CITED: node_modules/next/dist/docs/01-app/03-api-reference/04-functions/not-found.md] | Use when a song, album, or artist ID does not exist. [CITED: node_modules/next/dist/docs/01-app/03-api-reference/04-functions/not-found.md] |
| `next/font/local` | bundled with Next.js [VERIFIED: src/app/layout.tsx] | Preserve the current Space Grotesk setup on detail pages [VERIFIED: src/app/layout.tsx] | Already configured globally; do not replace it in this phase. [VERIFIED: src/app/layout.tsx] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Server-rendered detail pages [VERIFIED: src/app/page.tsx] | Client-only detail pages [ASSUMED] | Client-only would duplicate loading/error state, lose direct-load strength, and diverge from the existing Phase 2 architecture. [VERIFIED: src/app/page.tsx] [CITED: node_modules/next/dist/docs/01-app/01-getting-started/06-fetching-data.md] |
| Numeric ID routes derived from current schema [VERIFIED: billboard_stats/db/schema.sql] | Slug routes [ASSUMED] | Slugs add canonicalization and lookup work, while current browse/search data already key entities by numeric IDs. [VERIFIED: src/lib/charts.ts] [VERIFIED: billboard_stats/db/schema.sql] |

**Installation:**
```bash
# No new packages are required for the recommended Phase 3 baseline.
```

**Version verification:** `next@16.2.4`, `react@19.2.5`, `@neondatabase/serverless@1.1.0`, and `tailwindcss@4.2.4` were verified against the npm registry on 2026-04-28; the repo currently pins `react@19.2.4`, one patch behind latest. [VERIFIED: npm registry] [VERIFIED: package.json]

## Architecture Patterns

### System Architecture Diagram

```text
Browse table row / artist pill click
  -> next/link to /songs/[id] | /albums/[id] | /artists/[id]
    -> server page resolves params
      -> entity service helper in src/lib/details/*
        -> base entity query (songs/albums/artists)
        -> stats query (song_stats/album_stats/artist_stats)
        -> related artists or related song/album tables
        -> chart-run query (songs/albums only)
          -> Neon PostgreSQL
    -> page renders title + stats bar
      -> optional client Chart Run toggle
        -> inline SVG with inverted Y-axis + peak annotation
      -> semantic table(s)
        -> row links to related detail routes
    -> missing entity
      -> notFound()
```

### Recommended Project Structure
```text
src/
├── app/
│   ├── songs/[id]/page.tsx          # Song detail route
│   ├── albums/[id]/page.tsx         # Album detail route
│   ├── artists/[id]/page.tsx        # Artist detail route
│   └── not-found.tsx                # Shared not-found fallback if desired
├── components/
│   ├── detail/
│   │   ├── detail-header.tsx
│   │   ├── stats-bar.tsx
│   │   ├── artist-pill-list.tsx
│   │   ├── chart-history-table.tsx
│   │   └── chart-run-visualization.tsx
│   └── charts/
│       └── movement-badge.tsx
└── lib/
    ├── detail-types.ts
    ├── songs.ts
    ├── albums.ts
    └── artists.ts
```

### Pattern 1: One server page per entity type
**What:** Build separate route files for song, album, and artist pages rather than a generic catch-all detail route. [CITED: node_modules/next/dist/docs/01-app/01-getting-started/03-layouts-and-pages.md]  
**When to use:** Always for this phase, because the required data and UI shape differ materially across the three entity types. [VERIFIED: .planning/REQUIREMENTS.md] [VERIFIED: BillboardStats.html]  
**Example:**
```typescript
// Source: node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/dynamic-routes.md
import { notFound } from "next/navigation";
import { getSongDetail } from "@/lib/songs";

export default async function SongPage(props: PageProps<"/songs/[id]">) {
  const { id } = await props.params;
  const song = await getSongDetail(Number(id));

  if (!song) {
    notFound();
  }

  return <SongDetailView detail={song} />;
}
```

### Pattern 2: Mirror the Python service split in TypeScript
**What:** Keep detail helpers split into `getSongDetail`, `getSongChartRun`, `getArtistDetail`, `getArtistSongs`, and `getArtistAlbums` instead of merging everything into one mega-query module. [VERIFIED: billboard_stats/services/song_service.py] [VERIFIED: billboard_stats/services/album_service.py] [VERIFIED: billboard_stats/services/artist_service.py]  
**When to use:** For all data access in this phase. [VERIFIED: .planning/ROADMAP.md]  
**Example:**
```typescript
// Source: billboard_stats/services/song_service.py
export async function getSongDetail(songId: number) {
  const [songRow, statsRows, artistRows] = await Promise.all([
    // songs
    // song_stats
    // song_artists -> artists
  ]);

  return mapSongDetail(songRow, statsRows[0] ?? null, artistRows);
}
```

### Pattern 3: Shared history table plus chart-specific axis config
**What:** Use one history-table component for songs and albums, and one visualization component parameterized by chart max/ticks. [VERIFIED: .planning/phases/03-detail-pages-visualizations/03-UI-SPEC.md] [VERIFIED: BillboardStats.html]  
**When to use:** For DETAILS-04 and DETAILS-05. [VERIFIED: .planning/REQUIREMENTS.md]  
**Example:**
```typescript
// Source: .planning/phases/03-detail-pages-visualizations/03-UI-SPEC.md
const Y_AXIS_TICKS = {
  "hot-100": [1, 25, 50, 75, 100],
  "billboard-200": [1, 50, 100, 150, 200],
} as const;
```

### Anti-Patterns to Avoid
- **Catch-all detail route like `/entity/[type]/[id]`:** This hides meaningful differences between song, album, and artist pages and complicates metadata and not-found handling. [VERIFIED: .planning/REQUIREMENTS.md] [CITED: node_modules/next/dist/docs/01-app/03-api-reference/04-functions/generate-metadata.md]
- **Client-fetching the entire detail page after mount:** This regresses direct-load performance and duplicates error/loading logic the server can already own. [VERIFIED: src/app/page.tsx] [CITED: node_modules/next/dist/docs/01-app/01-getting-started/06-fetching-data.md]
- **Recomputing aggregate stats from chart-run rows in the UI:** The schema already provides canonical stats tables; deriving them in React invites drift. [VERIFIED: billboard_stats/db/schema.sql]
- **Using browse-row movement logic as the only source of history-table semantics:** Detail history rows already have `last_pos`, `is_new`, `peak_pos`, and `weeks_on_chart` directly in the run query. [VERIFIED: billboard_stats/services/song_service.py] [VERIFIED: billboard_stats/services/album_service.py]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Detail-route dispatch | A custom in-memory “page stack” like the HTML prototype demo [VERIFIED: BillboardStats.html] | Real App Router dynamic routes with `next/link` and `notFound()` [CITED: node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/dynamic-routes.md] [CITED: node_modules/next/dist/docs/01-app/03-api-reference/04-functions/not-found.md] | The prototype stack is only for demo navigation; the Next app already has real routing. [VERIFIED: src/app/page.tsx] [VERIFIED: src/components/shell/primary-nav.tsx] |
| Stats derivation | Client-side loops to compute peak/debut/weeks from chart history [ASSUMED] | `song_stats`, `album_stats`, and `artist_stats` [VERIFIED: billboard_stats/db/schema.sql] | The ETL already defines canonical aggregate logic, including phantom-week filtering. [VERIFIED: billboard_stats/etl/stats_builder.py] |
| Visualization library | Altair/Recharts/D3 for this simple embedded sparkline-style run [VERIFIED: billboard_stats/app.py] [ASSUMED] | Inline SVG in a focused React component [VERIFIED: BillboardStats.html] [VERIFIED: .planning/phases/03-detail-pages-visualizations/03-UI-SPEC.md] | The approved UI calls for an inline, lightweight, collapsible research aid rather than a dashboard charting surface. [VERIFIED: .planning/phases/03-detail-pages-visualizations/03-UI-SPEC.md] |
| Entity pills and drill-down tables | A generic card system [ASSUMED] | Plain chips and semantic tables styled with Tailwind utilities [VERIFIED: BillboardStats.html] [VERIFIED: src/components/charts/chart-table.tsx] | The visual contract is compact, text-first, and anti-card. [VERIFIED: .planning/phases/03-detail-pages-visualizations/03-UI-SPEC.md] |

**Key insight:** The hard problems in this domain are already solved in the schema and ETL; Phase 3 should translate those contracts into routes and components, not redesign the data model. [VERIFIED: billboard_stats/db/schema.sql] [VERIFIED: billboard_stats/etl/stats_builder.py]

## Common Pitfalls

### Pitfall 1: Dropping phantom-week filtering on detail queries
**What goes wrong:** Detail charts and history tables show false early weeks before the chart really started. [VERIFIED: src/lib/charts.ts]  
**Why it happens:** The browse helpers already copied the legacy filtered CTEs, but a new detail helper might accidentally query entry tables directly. [VERIFIED: src/lib/charts.ts] [VERIFIED: billboard_stats/services/song_service.py] [VERIFIED: billboard_stats/services/album_service.py]  
**How to avoid:** Reuse the same filtered CTE pattern from `src/lib/charts.ts` and the legacy detail services. [VERIFIED: src/lib/charts.ts] [VERIFIED: billboard_stats/services/song_service.py] [VERIFIED: billboard_stats/services/album_service.py]  
**Warning signs:** Chart-run counts disagree with `total_weeks` in the stats tables. [VERIFIED: billboard_stats/db/schema.sql]

### Pitfall 2: Using the wrong default sort direction for history
**What goes wrong:** The query returns chronological order, but the UI spec requires newest week first in the table. [VERIFIED: billboard_stats/services/song_service.py] [VERIFIED: billboard_stats/services/album_service.py] [VERIFIED: .planning/phases/03-detail-pages-visualizations/03-UI-SPEC.md]  
**Why it happens:** The legacy chart-run services order by ascending `chart_date`; the prototype reverses in the UI before rendering the history table. [VERIFIED: billboard_stats/services/song_service.py] [VERIFIED: billboard_stats/services/album_service.py] [VERIFIED: BillboardStats.html]  
**How to avoid:** Keep the raw query chronological for visualization math, then derive a reversed array specifically for table rendering. [VERIFIED: BillboardStats.html]  
**Warning signs:** The first row of history is the debut week instead of the most recent week. [VERIFIED: BillboardStats.html]

### Pitfall 3: Treating artist pages like song/album pages
**What goes wrong:** The artist page becomes a stretched single-entity template and loses its aggregate-first information architecture. [VERIFIED: .planning/phases/03-detail-pages-visualizations/03-UI-SPEC.md] [VERIFIED: BillboardStats.html]  
**Why it happens:** Shared-detail abstractions are over-applied. [ASSUMED]  
**How to avoid:** Plan a distinct artist page view model with aggregate stats plus two drill-down tables. [VERIFIED: .planning/REQUIREMENTS.md] [VERIFIED: billboard_stats/services/artist_service.py]  
**Warning signs:** The page contains a chart-run module or a chart-history table for artists even though the success criteria do not require one. [VERIFIED: .planning/ROADMAP.md]

### Pitfall 4: Missing the Next.js 16 `params` contract
**What goes wrong:** Route code treats `params` as synchronous and drifts toward deprecated patterns. [CITED: node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/dynamic-routes.md]  
**Why it happens:** Older Next.js examples used synchronous `params`. [CITED: node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/dynamic-routes.md]  
**How to avoid:** Type page props with `PageProps<'/songs/[id]'>` or equivalent and `await props.params`. [CITED: node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/dynamic-routes.md]  
**Warning signs:** New route files destructure `params.id` directly without awaiting `params`. [CITED: node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/dynamic-routes.md]

## Code Examples

Verified patterns from official or canonical project sources:

### Dynamic detail route with `notFound()`
```typescript
// Source: node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/dynamic-routes.md
// Source: node_modules/next/dist/docs/01-app/03-api-reference/04-functions/not-found.md
import { notFound } from "next/navigation";

export default async function Page(props: PageProps<"/artists/[id]">) {
  const { id } = await props.params;
  const artist = await getArtistDetail(Number(id));

  if (!artist) {
    notFound();
  }

  return <ArtistDetailView detail={artist} />;
}
```

### Canonical song chart-run query shape
```typescript
// Source: billboard_stats/services/song_service.py
SELECT cw.chart_date, e.rank, e.last_pos, e.is_new, e.peak_pos, e.weeks_on_chart
FROM hot100_entries e
JOIN chart_weeks cw ON e.chart_week_id = cw.id
WHERE e.song_id = $1
ORDER BY cw.chart_date;
```

### Canonical artist detail split
```typescript
// Source: billboard_stats/services/artist_service.py
const profile = await getArtistProfile(artistId);
const songs = await getArtistSongs(artistId);
const albums = await getArtistAlbums(artistId);
```

### UI-axis configuration for chart-run SVG
```typescript
// Source: .planning/phases/03-detail-pages-visualizations/03-UI-SPEC.md
const chartConfig = {
  "hot-100": { maxRank: 100, ticks: [1, 25, 50, 75, 100] },
  "billboard-200": { maxRank: 200, ticks: [1, 50, 100, 150, 200] },
} as const;
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Synchronous `params` in route pages [CITED: node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/dynamic-routes.md] | `params` is a promise and should be awaited [CITED: node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/dynamic-routes.md] | Next.js 15+ with deprecation noted in current docs [CITED: node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/dynamic-routes.md] | Phase 3 route plans should use the current async contract from the start. [CITED: node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/dynamic-routes.md] |
| Streamlit detail pages with Altair charts [VERIFIED: billboard_stats/app.py] | App Router server pages with focused client islands [VERIFIED: src/app/page.tsx] [CITED: node_modules/next/dist/docs/01-app/01-getting-started/06-fetching-data.md] | Project migration documented across Phases 1-3 [VERIFIED: .planning/ROADMAP.md] | The chart-run visualization should be a lightweight embedded component, not a separate plotting stack. [VERIFIED: .planning/phases/03-detail-pages-visualizations/03-UI-SPEC.md] |
| Tailwind config-first mental model [ASSUMED] | Tailwind v4 theme tokens declared in CSS [VERIFIED: src/app/globals.css] | Current repo state [VERIFIED: src/app/globals.css] | Styling work in this phase should extend `globals.css` conventions rather than assume a new config file. [VERIFIED: src/app/globals.css] |

**Deprecated/outdated:**
- Directly copying old synchronous `params` examples from older Next.js material is outdated for this repo’s installed version. [CITED: node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/dynamic-routes.md]
- Recreating the prototype’s in-memory navigation stack is outdated because the Next app already has real route-based navigation. [VERIFIED: BillboardStats.html] [VERIFIED: src/components/shell/primary-nav.tsx]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Client-only detail pages would be strictly worse than server-rendered pages for this phase. [ASSUMED] | Standard Stack / Alternatives | Low; if future interaction needs grow, one route could adopt more client behavior later. |
| A2 | Numeric ID routes are preferable to slugs for this v1 phase. [ASSUMED] | Standard Stack / Alternatives | Medium; changing to slugs later would require route and link updates. |
| A3 | Recharts or D3 are unnecessary for the SVG visualization. [ASSUMED] | Don't Hand-Roll | Low; if the chart spec expands significantly, a library could still be introduced later. |
| A4 | Shared-detail abstractions are the likely cause of artist-page drift. [ASSUMED] | Common Pitfalls | Low; this is a planning caution, not a hard dependency. |
| A5 | Tailwind’s older config-first model is the “old approach” relevant here. [ASSUMED] | State of the Art | Low; it does not affect the implementation recommendation to extend `globals.css`. |

## Open Questions

1. **Should browse-table rows become clickable in Phase 3 or wait for Phase 4 search/results parity?**
   - What we know: The prototype uses clickable rows to drill into song and album details, and Phase 3 requires the detail pages themselves. [VERIFIED: BillboardStats.html] [VERIFIED: .planning/ROADMAP.md]
   - What's unclear: Whether Phase 3 should include browse-table link wiring as part of its acceptance scope or treat it as incidental integration. [ASSUMED]
   - Recommendation: Treat row linking from the Latest Charts page as in-scope integration work because the detail routes need an entry path from existing UI. [VERIFIED: src/components/charts/chart-table.tsx] [ASSUMED]

2. **Should detail pages expose dynamic metadata titles per entity?**
   - What we know: Next.js supports `generateMetadata()` in server pages, and entity titles are available from the base queries. [CITED: node_modules/next/dist/docs/01-app/03-api-reference/04-functions/generate-metadata.md] [VERIFIED: billboard_stats/services/song_service.py] [VERIFIED: billboard_stats/services/album_service.py] [VERIFIED: billboard_stats/services/artist_service.py]
   - What's unclear: Whether metadata is considered phase scope or nice-to-have. [ASSUMED]
   - Recommendation: Include it in planning as a low-cost completion item because it naturally fits server-rendered entity pages. [CITED: node_modules/next/dist/docs/01-app/03-api-reference/04-functions/generate-metadata.md]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | Next.js build and local verification [VERIFIED: package.json] | ✓ [VERIFIED: local shell] | `v25.2.1` [VERIFIED: local shell] | — |
| npm | Package scripts and registry verification [VERIFIED: package.json] | ✓ [VERIFIED: local shell] | `11.7.0` [VERIFIED: local shell] | — |
| `DATABASE_URL` env var | Server-rendered detail queries through `getSql()` [VERIFIED: src/lib/db.ts] | ✗ [VERIFIED: local shell] | — | None for real data; only static/error-state UI can be exercised without it. [VERIFIED: src/lib/db.ts] |
| `psql` CLI | Optional manual DB inspection during implementation [ASSUMED] | ✗ [VERIFIED: local shell] | — | Use app-level queries and existing service code as reference instead. [VERIFIED: billboard_stats/services/song_service.py] [VERIFIED: billboard_stats/services/album_service.py] [VERIFIED: billboard_stats/services/artist_service.py] |

**Missing dependencies with no fallback:**
- `DATABASE_URL` is currently missing locally, so live detail-page queries cannot be verified end-to-end without configuring the database connection. [VERIFIED: src/lib/db.ts] [VERIFIED: local shell]

**Missing dependencies with fallback:**
- `psql` is missing, but implementation can still proceed using the checked-in schema, ETL, and service-layer query definitions. [VERIFIED: billboard_stats/db/schema.sql] [VERIFIED: billboard_stats/services/song_service.py] [VERIFIED: billboard_stats/services/album_service.py] [VERIFIED: billboard_stats/services/artist_service.py]

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no [VERIFIED: .planning/REQUIREMENTS.md] | User authentication is explicitly out of scope for v1. [VERIFIED: .planning/REQUIREMENTS.md] |
| V3 Session Management | no [VERIFIED: .planning/REQUIREMENTS.md] | No user accounts or sessions are planned for this app. [VERIFIED: .planning/REQUIREMENTS.md] |
| V4 Access Control | no [VERIFIED: .planning/REQUIREMENTS.md] | These are public read-only entity pages; the relevant safeguard is existence validation, not authorization. [VERIFIED: .planning/REQUIREMENTS.md] [CITED: node_modules/next/dist/docs/01-app/03-api-reference/04-functions/not-found.md] |
| V5 Input Validation | yes [VERIFIED: src/app/api/charts/route.ts] | Parse route IDs as numbers, reject invalid values, and continue using explicit allowlists/validation before DB access. [VERIFIED: src/app/api/charts/route.ts] [VERIFIED: src/lib/charts.ts] |
| V6 Cryptography | no [VERIFIED: .planning/REQUIREMENTS.md] | This phase does not introduce cryptographic features. [VERIFIED: .planning/REQUIREMENTS.md] |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Invalid route IDs leading to bad queries | Tampering | Validate numeric route params and return `notFound()` or a 404 path before querying. [CITED: node_modules/next/dist/docs/01-app/03-api-reference/04-functions/not-found.md] [VERIFIED: src/lib/charts.ts] |
| SQL injection through route/query inputs | Tampering | Keep user-derived values parameterized in SQL and preserve allowlist validation patterns already present in Phase 2 helpers. [VERIFIED: src/app/api/charts/route.ts] [VERIFIED: src/lib/charts.ts] |
| Leaking raw DB errors into the UI | Information Disclosure | Continue returning concise user-facing error states instead of surfacing stack traces or SQL text. [VERIFIED: src/app/api/charts/route.ts] [VERIFIED: src/app/status/page.tsx] |
| Client bundle overexposure of DB access logic | Information Disclosure | Keep DB calls in server components and `src/lib` server helpers only. [CITED: node_modules/next/dist/docs/01-app/01-getting-started/06-fetching-data.md] [VERIFIED: src/lib/db.ts] |

## Sources

### Primary (HIGH confidence)
- `node_modules/next/dist/docs/01-app/01-getting-started/03-layouts-and-pages.md` - App Router pages, layouts, nested routes, dynamic segments. [CITED: node_modules/next/dist/docs/01-app/01-getting-started/03-layouts-and-pages.md]
- `node_modules/next/dist/docs/01-app/01-getting-started/06-fetching-data.md` - Server-component data fetching and client-island guidance. [CITED: node_modules/next/dist/docs/01-app/01-getting-started/06-fetching-data.md]
- `node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/dynamic-routes.md` - Current dynamic route and `params` contract. [CITED: node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/dynamic-routes.md]
- `node_modules/next/dist/docs/01-app/03-api-reference/04-functions/generate-metadata.md` - Dynamic metadata rules for server pages. [CITED: node_modules/next/dist/docs/01-app/03-api-reference/04-functions/generate-metadata.md]
- `node_modules/next/dist/docs/01-app/03-api-reference/04-functions/not-found.md` - Canonical not-found handling. [CITED: node_modules/next/dist/docs/01-app/03-api-reference/04-functions/not-found.md]
- `billboard_stats/db/schema.sql` - Canonical table and index definitions for detail-page data. [VERIFIED: billboard_stats/db/schema.sql]
- `billboard_stats/services/song_service.py`, `album_service.py`, `artist_service.py` - Canonical legacy detail-query shapes. [VERIFIED: billboard_stats/services/song_service.py] [VERIFIED: billboard_stats/services/album_service.py] [VERIFIED: billboard_stats/services/artist_service.py]
- `billboard_stats/etl/stats_builder.py` - Canonical stat derivation and phantom-week filtering logic. [VERIFIED: billboard_stats/etl/stats_builder.py]
- `.planning/phases/03-detail-pages-visualizations/03-UI-SPEC.md` - Locked visual and interaction contract for this phase. [VERIFIED: .planning/phases/03-detail-pages-visualizations/03-UI-SPEC.md]

### Secondary (MEDIUM confidence)
- `BillboardStats.html` - Prototype continuity for detail-page interaction and SVG toggle behavior. [VERIFIED: BillboardStats.html]
- `src/app/page.tsx`, `src/components/charts/*.tsx`, `src/lib/charts.ts` - Current Next.js architectural precedent from Phase 2. [VERIFIED: src/app/page.tsx] [VERIFIED: src/components/charts/latest-charts-view.tsx] [VERIFIED: src/components/charts/chart-table.tsx] [VERIFIED: src/lib/charts.ts]
- npm registry metadata for `next`, `react`, `@neondatabase/serverless`, and `tailwindcss`. [VERIFIED: npm registry]

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Versions were verified against `package.json` and npm registry, and route/data-fetching behavior was checked against the installed Next.js docs. [VERIFIED: package.json] [VERIFIED: npm registry] [CITED: node_modules/next/dist/docs/01-app/01-getting-started/06-fetching-data.md]
- Architecture: HIGH - The recommended structure matches both the existing Phase 2 app architecture and the legacy service/query boundaries. [VERIFIED: src/app/page.tsx] [VERIFIED: billboard_stats/services/song_service.py] [VERIFIED: billboard_stats/services/album_service.py] [VERIFIED: billboard_stats/services/artist_service.py]
- Pitfalls: HIGH - The most important failure modes are directly evidenced by the ETL, legacy services, and locked UI contract. [VERIFIED: billboard_stats/etl/stats_builder.py] [VERIFIED: billboard_stats/services/song_service.py] [VERIFIED: billboard_stats/services/album_service.py] [VERIFIED: .planning/phases/03-detail-pages-visualizations/03-UI-SPEC.md]

**Research date:** 2026-04-28  
**Valid until:** 2026-05-28 for project-local architecture guidance; 2026-05-05 for npm-registry version currency. [VERIFIED: npm registry]
