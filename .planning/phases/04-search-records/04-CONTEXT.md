# Phase 04: Search & Records - Context

**Gathered:** 2026-04-28
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers the remaining public discovery surfaces for the initial Next.js release: fuzzy search across songs, albums, and artists, plus the records/leaderboards experience including preset lists and the custom query builder. The work must complete the read-only prototype faithfully on top of the existing PostgreSQL-backed Billboard dataset and the server-safe TypeScript query layer established in earlier phases.

</domain>

<decisions>
## Implementation Decisions

### Search Experience
- Search should remain a lightweight client island inside the existing Search page shell, with a single text input and tabbed result panes for `Songs`, `Albums`, and `Artists`.
- No request should fire until the query reaches 2 characters, matching the existing Streamlit behavior and the Phase 4 requirement boundary.
- Search results should be fetched from an internal API route backed by typed lib helpers, not embedded directly in the client component.
- Search tab order and counts should follow the prototype: `Songs`, `Albums`, `Artists`, with the result count shown in the active tab label once the query is valid.
- Search results should cap the visible list at 50 rows per entity type to keep the interface dense and scannable.

### Search Result Presentation
- Song and album search tables should preserve the existing newsroom table language: `TITLE`, `ARTIST`, `PK`, `WKS`, and `WKS@PK`.
- Artist results should use a denser aggregate table instead of card rows, with columns for `NAME`, `SONGS`, `ALBUMS`, `#1 SNG`, and `#1 ALB`.
- Clicking a song, album, or artist row should navigate directly to the existing detail routes built in Phase 3.
- Empty search states should stay inline and neutral, with clear copy for `Type at least 2 characters to search`, `No songs found`, `No albums found`, and `No artists found`.

### Records Scope and Interaction
- Records should use the prototype-first layout: record selector, chart toggle, compact result count, and a natural-language custom query builder rather than a form stack.
- The preset records list should include the complete Python/Streamlit-backed set, not only the shorter prototype demo set: `Most Weeks at #1`, `Longest Chart Runs`, `Most #1 Songs (by Artist)`, `Most #1 Albums (by Artist)`, `Most Entries by Artist`, `Most Simultaneous Entries`, `Biggest Debuts`, and `Fastest to #1`.
- Unsupported chart/record combinations should render inline explanatory states instead of empty broken tables, mirroring the Streamlit behavior.
- Artist-scoped record rows should support inline drilldown expansion on the Records page; song and album rows should navigate directly to their detail pages.

### Records Query Builder
- The custom query builder should keep the prototype’s sentence-style interaction model rather than reverting to a plain form.
- The query builder should support the existing Python query dimensions: weeks at `#1`, total weeks, weeks at a specific position, and weeks in the top N, with artist, peak-range, debut-range, and minimum-weeks filters.
- Custom query results should return the top 50 rows for UI display even if a larger internal query limit is used server-side.
- Both preset records and custom query results should be served through one internal records API route with an explicit mode contract.

### the agent's Discretion
- Minor debounce, pending-state, and local-state implementation details are at the agent's discretion as long as the visible UX stays faithful to the prototype and existing dense table patterns.
- Whether the records API is organized as a single route with mode parameters or split into narrowly-scoped helper functions is at the agent's discretion, provided the page layer consumes typed contracts.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/components/charts/chart-table.tsx` establishes the project’s dense table, muted header, and red `#1` emphasis pattern.
- `src/components/detail/stats-bar.tsx` and the Phase 3 page shells provide the compact bordered grid language that Search and Records should extend rather than replace.
- `src/app/api/charts/route.ts` is the current reference for internal API validation and concise error responses.
- `src/components/shell/site-shell.tsx`, `primary-nav.tsx`, and `mobile-bottom-nav.tsx` already provide the shared page framing and navigation.

### Established Patterns
- Initial page loads are server-rendered, while high-interaction surfaces use focused client islands with fetch calls to internal API routes.
- Database-backed query logic lives in `src/lib/*` helpers and returns typed, route-safe payloads.
- Error states use inline bordered panels; empty states use neutral dashed or soft-gray surfaces with terse copy.
- Typography, spacing, and density follow the newsroom-style contract locked in prior phases.

### Integration Points
- Search result rows must route into `/song/[id]`, `/album/[id]`, and `/artist/[id]`.
- Records drilldowns reuse the same detail routes and can also surface artist-specific expansions inline on the Records page.
- The Phase 4 lib layer should translate Python `search_*` and `records_service.py` logic into TypeScript so the UI can consume one stable contract per interaction mode.

</code_context>

<specifics>
## Specific Ideas

- Keep the Search page visually close to the prototype: a prominent input field at the top, tab buttons directly beneath, and dense results below without card wrappers.
- Keep the Records page as the most interaction-heavy surface in the app, but still text-first and compact: selector, chart toggle, inline sentence builder, then leaderboard rows.
- Preserve the prototype’s result count feedback for both Search tabs and Records queries.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
