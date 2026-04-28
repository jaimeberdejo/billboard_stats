# Phase 3: Detail Pages & Visualizations - Research

**Researched:** 2026-04-28
**Domain:** Next.js App Router detail pages backed by PostgreSQL stats tables and chart-history queries
**Confidence:** HIGH

<user_constraints>
## User Constraints

- Preserve the approved Phase 2 newsroom-style UI and dense data-first layout.
- Implement the HTML prototype faithfully before inventing new interaction patterns.
- Keep the Next.js app server-first where possible; use small client islands only for interaction that truly needs client state.
</user_constraints>

<architectural_responsibility_map>
## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Song/album/artist route rendering | Frontend Server | Browser/Client | Direct route loads should render usable detail pages without client bootstrap fetches. |
| Entity detail data queries | API/Backend | Database/Storage | Existing Python services already define the required data contracts. |
| Chart-history tables | Frontend Server | Browser/Client | Initial history payload should render on the server for immediate scanning. |
| Chart-run visualization toggle | Browser/Client | Frontend Server | Toggle state is a light client concern; the underlying data is still server-provided. |
| Artist/song/album cross-link navigation | Browser/Client | Frontend Server | Links should use App Router navigation on top of server-rendered routes. |

</architectural_responsibility_map>

<research_summary>
## Summary

Phase 3 is a vertical slice around entity detail routes, not just a visualization task. The existing Python services already define the exact backend shape the Next.js implementation should translate: song and album lookups with stats and associated artists, artist profiles with career aggregates, and chronological chart runs with phantom-week filtering preserved. The prototype establishes the UX contract: compact detail headers, dense stats bars, optional inline chart-run visualization, a primary week-by-week history table for songs/albums, and drill-down tables on artist pages.

The cleanest implementation path is to keep all detail routes server-first and mirror the Phase 2 pattern of thin route handlers over `src/lib/*` helpers. The planner should likely split work into three coordinated slices: shared detail data helpers/APIs, song+album detail pages with chart-run rendering, and the artist detail page with cross-linked catalog tables. The visualization should be treated as a reusable component fed by shared chart-run data, not as page-specific logic duplicated per route.
</research_summary>

<backend_contracts>
## Existing Backend Contracts to Preserve

### Song service
- `billboard_stats/services/song_service.py`
- `get_song(song_id)` returns song metadata, `song_stats`, and associated artists.
- `get_chart_run(song_id)` returns chronological Hot 100 chart points with:
  - `chart_date`
  - `rank`
  - `last_pos`
  - `is_new`
  - `peak_pos`
  - `weeks_on_chart`

### Album service
- `billboard_stats/services/album_service.py`
- `get_album(album_id)` returns album metadata, `album_stats`, and associated artists.
- `get_chart_run(album_id)` returns chronological Billboard 200 chart points with the same chart-run fields as songs.

### Artist service
- `billboard_stats/services/artist_service.py`
- `get_artist_profile(artist_id)` returns artist metadata and aggregate `artist_stats`.
- `get_artist_songs(artist_id)` returns all songs with stats, ordered by debut date.
- `get_artist_albums(artist_id)` returns all albums with stats, ordered by debut date.

### Key implication
- The Next.js phase does not need new domain logic. It needs TypeScript translations of these service contracts and route/page composition on top.
</backend_contracts>

<ui_contract_from_prototype>
## UI Contract From Prototype

Reference: `BillboardStats.html`

### Song and album detail pages
- Back link at the top of the page.
- Title block:
  - quoted title for songs/albums
  - artist credit as muted subtitle
- Dense stats bar with:
  - Peak
  - Weeks on Chart
  - Weeks at #1
  - Weeks at Peak
  - Debut Position
  - Debut Date
- `Chart Run Visualization` collapsed behind a text toggle.
- `Chart History` table is the primary data view.
- `Artists` section renders artist pills linking to artist detail pages.

### Artist detail page
- Back link
- Artist name header with date range subtitle
- Dense stats bar with career aggregates including:
  - Hot 100 Songs
  - B200 Albums
  - #1 totals
  - total weeks
  - best peak
  - max simultaneous entries
- Two dense tables:
  - `Hot 100 Songs`
  - `Billboard 200 Albums`
- Rows are clickable drill-down surfaces to song/album detail pages.

### Visualization contract
- Inline SVG, not canvas-heavy charting
- Collapsible, secondary to the table
- Inverted Y-axis (`#1` at top)
- Peak dot plus `#rank` annotation
- Only first and last X-axis labels
- Five Y-axis ticks based on chart family
</ui_contract_from_prototype>

<recommended_project_structure>
## Recommended Project Structure

```text
src/
├── app/
│   ├── artist/[id]/page.tsx
│   ├── song/[id]/page.tsx
│   ├── album/[id]/page.tsx
│   └── api/
│       ├── artists/[id]/route.ts
│       ├── songs/[id]/route.ts
│       └── albums/[id]/route.ts
├── components/
│   ├── detail/
│   │   ├── detail-header.tsx
│   │   ├── stats-bar.tsx
│   │   ├── artist-pills.tsx
│   │   ├── chart-history-table.tsx
│   │   └── chart-run-visualization.tsx
│   └── artist/
│       └── artist-catalog-table.tsx
└── lib/
    ├── songs.ts
    ├── albums.ts
    └── artists.ts
```

This keeps the query translation in `lib`, server page composition in `app`, and visual reuse in `components`.
</recommended_project_structure>

<architecture_patterns>
## Architecture Patterns

### Pattern 1: Server route + client toggle island
Use server pages for entity data fetches and a tiny client component only for the chart-visualization expand/collapse interaction. The chart-history table and stats should not wait on the client.

### Pattern 2: Shared chart-history model
Normalize song and album chart-run points to one TypeScript shape so the same history table and SVG visualization can serve both routes.

### Pattern 3: Reuse browse movement semantics
The history table should reuse Phase 2 movement semantics (`NEW`, `RE`, green up, red down, neutral flat) rather than inventing a new detail-page encoding.

### Pattern 4: Thin route handlers over typed helpers
If internal routes are added for detail entities, keep them as simple validation/serialization wrappers over new `src/lib/{songs,albums,artists}.ts` helpers, matching the Phase 2 API approach.
</architecture_patterns>

<planning_guidance>
## Planning Guidance

The phase should likely be split into at least three plans:

1. **Detail data helpers and route-safe contracts**
   - Translate Python song/album/artist services into TypeScript helpers.
   - Add route handlers if the page architecture or future client-side navigation benefits from them.

2. **Song + album detail pages**
   - Implement `[id]` routes, shared stats/header/history components, artist pills, and chart-run visualization.
   - This is a cohesive vertical slice because songs and albums share nearly all UI structure.

3. **Artist detail page**
   - Implement artist profile aggregates and the two drill-down tables.
   - Reuse shared dense table patterns but keep this separate because the data shape differs from song/album pages.

Potential wave structure:
- Wave 1: data helpers / route contracts
- Wave 2: song+album detail pages and visualization
- Wave 2 or 3: artist detail page, depending on helper/API dependencies
</planning_guidance>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Duplicating song and album detail logic
Songs and albums differ mainly in chart family and entity source. Duplicating header/stats/history/visualization components will create avoidable drift.

### Pitfall 2: Building the visualization before the data contract
If the chart-run component is designed before the TypeScript chart-run shape is stabilized, the planner will create avoidable refactors across multiple pages.

### Pitfall 3: Client-only detail page loading
Pushing detail pages into client fetch-on-mount mode would regress the Phase 2 server-first approach and make direct links slower and less reliable.

### Pitfall 4: Losing prototype row order semantics
The prototype reverses chronological chart runs for the history table so newest weeks appear first while the visualization still uses chronological order. The implementation should preserve that split intentionally.
</common_pitfalls>

<codebase_anchors>
## Codebase Anchors to Reuse

- `src/components/charts/chart-table.tsx`
  - dense table spacing
  - movement badge semantics
  - sticky header treatment

- `src/app/page.tsx` and `src/app/status/page.tsx`
  - server-first page pattern with graceful DB fallback

- `src/lib/charts.ts`
  - phantom-week filtering pattern
  - route-safe typed helper structure

- `BillboardStats.html`
  - exact detail-page section order
  - stats bar density
  - chart-run visualization semantics

- `billboard_stats/app.py`
  - working behavior for song, album, and artist detail pages
</codebase_anchors>

<validation_targets>
## Validation Targets For Planning

- Song detail route renders stats, chart history, visualization toggle, and artist pills.
- Album detail route renders the same structure with Billboard 200 data.
- Artist detail route renders aggregate stats plus Hot 100 and Billboard 200 drill-down tables.
- Shared movement semantics appear in chart-history rows.
- SVG chart run uses inverted Y-axis and peak annotation.
- Detail pages remain visually consistent with the approved `03-UI-SPEC.md`.
</validation_targets>
