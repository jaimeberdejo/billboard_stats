# Features Research

**Domain:** Music chart statistics web app (Billboard Hot 100 / Billboard 200)
**Researched:** 2026-04-27
**Prototype reference:** BillboardStats.html (definitive UI spec)
**Scope:** Port prototype faithfully — no new feature invention in v1

---

## Table Stakes

Features users expect as baseline. Absent = product feels broken or incomplete. Applies to anyone who comes to a music-chart-data site (Billboard.com visitors, sports-reference-style enthusiasts, kworb users).

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Current chart rankings (Hot 100 + B200) | Core product — without this, there is nothing to see | Low | Ranked table with position, movement, title, artist, last-week, peak, weeks-on-chart |
| Week selector for chart date | Charts change weekly; users browse historical dates | Low | Dropdown of available chart weeks; most-recent as default |
| Movement indicators (NEW / RE / up / down / flat) | Readers expect visual grammar for chart movement before they open the page; it's on every chart display everywhere | Low | Color-coded: green up, red down, gray flat, badge for new/re-entry |
| Song detail page | Any clickable chart entry must resolve to a page with stats | Medium | Peak, total weeks, weeks-at-peak, weeks-at-#1, debut position, debut date |
| Album detail page | Same as above for B200 | Medium | Same stat set as song detail |
| Artist detail page | Clicking an artist name must go somewhere meaningful | Medium | Hot 100 songs table, B200 albums table, career stats bar |
| Week-by-week chart history table | Primary data users want when they click a song — the exact week-by-week record | Low | Date, position, movement, last-week, peak, week-count columns |
| Fuzzy search across songs / albums / artists | Users arrive knowing a name; they need to find it fast | Medium | Min-2-char trigger; tabbed results (Songs / Albums / Artists); result count shown per tab |
| Result counts in search tabs | Users need to know how many matches exist before switching tabs | Low | E.g. "Songs (12)" — already in prototype |
| Records / leaderboards page | "Who has the most #1 songs?" is the most commonly asked chart trivia question; a site without it is incomplete | Medium | Preset leaderboards: most weeks at #1, longest runs, most #1 songs by artist, most entries by artist, biggest debuts |
| HOT 100 / B200 toggle | Both charts exist; switching must be one tap | Low | Toggle group in controls bar, context-preserving |
| Mobile-responsive layout | >50% of music consumption discovery is mobile; a non-mobile chart site is broken | Low | Bottom nav on mobile, sticky top nav on desktop |
| Data status / freshness indicator | Users need to know if data is current or stale | Low | Table row counts + latest chart date per chart type |
| Back navigation from detail pages | Standard browser expectation; missing = users get stuck | Low | Back button (not just browser back) given SPA routing |
| Artist pill links on song/album detail | Collaborative artists are discoverable — "feat." artists must be clickable | Low | Pills rendered for each artist on the track |
| Sticky table headers | Long chart tables (100/200 rows) require headers to stay visible on scroll | Low | Already in prototype via `position: sticky; top: 44px` |

---

## Differentiators

Features that make this more valuable than Billboard.com's own data pages or a generic search. Billboard.com is ad-heavy, slow, and hides depth behind pagination. This app wins on density, speed, and query power.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Chart run SVG visualization (rank-over-time line) | No other free Billboard data site shows this in a clean, no-JS-library inline format | Medium | Y-axis inverted (rank 1 at top); peak dot annotated; first/last date labeled; toggle to show/hide so table is the primary anchor |
| Custom Query Builder (Records page) | Billboard.com has no custom leaderboard queries; kworb doesn't either for Hot 100 history | High | "Rank [entity] by [metric] — [sort]" sentence UI with inline selects; filters: artist name, min-weeks, peak range, debut range; top-50 results |
| Weeks-at-position queries (specific rank or top-N range) | Power-user question — "how many weeks did X spend in the top 10?" — unanswerable on any free public site | High | Backed by chart_entries scan; part of the Custom Query metric options |
| Artist career aggregates (max simultaneous charting songs) | "Max simultaneous" stat is not shown anywhere except this app | Low | Already computed in artist_stats; surface it in the stats bar |
| Dense, data-first design (Space Grotesk, 13px base, no whitespace padding) | Sports-reference users specifically choose data-dense sites over pretty-but-shallow ones; this is a differentiator against Billboard.com | Low | Design system already defined in prototype; no scope change needed |
| Re-entry badges | Chart sites often drop re-entries or treat them as new; explicit RE badge with gray styling is a meaningful data signal | Low | Already in prototype |
| Tabular-nums font-variant throughout | Small but important: numbers align in columns correctly, making comparison scanning fast | Low | Already in prototype CSS |

---

## Anti-Features (defer from v1)

Features that seem natural but add scope, complexity, or maintenance burden without proportional v1 value.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| User accounts / favorites / watchlists | Adds auth, session state, DB schema changes, significant scope | Bookmark via browser; revisit post-v1 |
| Cross-platform chart data (Spotify, Apple Music, Shazam) | Different data sources, ETL complexity, schema changes; kworb already does this better | Focus on Billboard-exclusive value: historical Hot 100 + B200 since 1958 |
| Comparison mode (artist A vs artist B side-by-side) | Visually complex, query-complex, needs new UI surface | Covered partially by Custom Query; defer full comparison view |
| Pagination on chart tables | Billboard.com uses pagination — users hate it; the full 100 or 200 rows is small enough to render in one pass | Render full list; use browser scroll |
| Genre / audio feature data (BPM, key, danceability) | Requires Spotify API integration, adds latency, schema complexity | Not in prototype; out of scope |
| Embeddable chart widgets | Distribution mechanism, not core product; adds CORS and iframe complexity | Post-v1 if demand exists |
| "Update Now" / manual ETL trigger button | ETL runs independently; a UI button creates race conditions and requires background job orchestration | ETL is fire-and-forget Python; UI is read-only |
| Social sharing (Twitter/X cards, share buttons) | Nice-to-have but zero core-value contribution in v1 | Add Open Graph meta tags passively (low-effort, meaningful reach) |
| Telegram bot integration | Was in original codebase; explicitly out of scope for this milestone | Revisit as a separate milestone |
| Export to CSV / JSON | Power-user feature; adds API surface questions and potential scraping concerns | Defer; no user request yet |
| Pagination / infinite scroll on search | Result sets are small (music catalog is bounded); full list renders fine | Limit server-side to top-50; no pagination needed |
| Dark mode | Visual scope, not data scope; adds testing burden | Use CSS custom properties from day one so it's easy to add later |

---

## Chart Visualization Notes

The prototype implements a specific approach. These notes document why it works for this domain and what constraints to honor.

### Approach: SVG line chart, inline, collapsible

**What the prototype does:**
- Pure SVG rendered server-side-safe (no D3, no Chart.js, no Recharts dependency)
- Fixed viewBox of 800x180, responsive via `width: 100%`
- Y-axis inverted: rank 1 at top, rank 100/200 at bottom
- Single line path in Billboard red (`#C8102E`)
- Peak dot annotated with `#rank` label above
- X-axis shows only first and last chart date (no crowded tick labels)
- Y-axis tick marks at quartiles (1 / 25 / 50 / 75 / 100 for Hot 100; 1 / 50 / 100 / 150 / 200 for B200)
- Collapsible behind a toggle button — table-first, chart on demand

**Why this is the right approach for rank-over-time data:**

1. Y-axis inversion is mandatory. A line "going up" must mean the song moved up in rankings (lower rank number). This is the universal expectation from the Billboard.com interface and every chart-tracking site. Failing to invert creates immediate confusion.

2. The line chart is the correct chart type for this data. Rank is a continuous sequential variable over time; users want to see the trajectory (sudden debut, slow climb, peak plateau, decay). A bar chart would obscure the shape of the run. A bump chart adds complexity only valuable when comparing multiple entities simultaneously — out of scope here.

3. Single-entity focus. Each visualization shows one song or one album's run. Multi-series on the same chart (comparing two songs) is an anti-feature for v1. The visual reading task is simpler with a single line.

4. Collapsible is intentional, not a compromise. The week-by-week table is the primary data surface — precise, scannable, sortable by the browser. The visualization is a complement for users who want shape-at-a-glance. Leading with the viz would bury the table.

5. Avoid heavy charting libraries (Recharts, Chart.js, D3) for this component. The chart is static per entity (data doesn't update in real-time during a session). SVG rendered from the API response is sufficient, eliminates a large JS bundle, and is simpler to maintain. If interactivity (hover tooltips) is added later, a lightweight library like Recharts or Victory can be introduced then.

**Specific implementation considerations:**

- For songs with very long runs (100+ weeks), the X-axis labels will overlap on mobile. Mitigation: abbreviate month ("Jun '19") or show year only when run exceeds 52 weeks.
- Songs that never charted at #1 still need the peak annotated. The peak dot should always be shown regardless of peak position.
- Re-entries create discontinuous runs in the data. The prototype treats the full chart history as a single continuous path (no gap rendering). This is acceptable for v1 — users can read the table for the exact gap. A future enhancement could render dotted/dashed segments for off-chart gaps.
- The 800x180 viewBox with `preserveAspectRatio="xMidYMid meet"` handles all responsive breakpoints correctly — no additional CSS needed beyond `width: 100%`.

---

## Feature Dependencies

```
Chart table (Latest Charts)
  └── Week selector (requires chart_weeks table with available dates)
  └── Movement badges (requires last-week position data)
  └── Song/Album detail page navigation

Song detail page
  └── Stats bar (requires song_stats computed values)
  └── Chart run visualization (requires chart_entries for that song, time-sorted)
  └── Chart history table (same data as visualization, tabular form)
  └── Artist pills → Artist detail page

Album detail page
  └── (same dependency tree as Song detail, sourced from album_stats + chart_entries)

Artist detail page
  └── Stats bar (requires artist_stats computed values)
  └── Hot 100 songs table (requires join: songs → chart_entries → artist)
  └── B200 albums table (requires join: albums → chart_entries → artist)

Search page
  └── Fuzzy search (requires pg_trgm indexes on songs.title, albums.title, artists.name)
  └── Tabbed results with counts (requires COUNT per entity type from search query)
  └── Navigation to Song / Album / Artist detail

Records page — preset leaderboards
  └── Requires pre-aggregated stats (records_service queries)
  └── Navigation to Song / Album / Artist detail

Records page — Custom Query
  └── Requires chart_entries table scan (potentially expensive without index)
  └── Artist filter requires fuzzy match or exact match against artists table
  └── Depends on: peak range, debut range, min-weeks filters (all column-indexed)
```

---

## MVP Recommendation

The prototype already defines the MVP. All Table Stakes features above are in scope. The prioritization order for implementation within phases:

1. **Latest Charts page** — First because it is the landing page and validates the DB connection, ETL pipeline, and data model end-to-end
2. **Song detail + Album detail pages** — Second because chart rows are clickable; unresolvable clicks break trust immediately
3. **Artist detail page** — Third; linked from detail pages via artist pills
4. **Search page** — Fourth; search is how returning users navigate efficiently
5. **Records page (preset leaderboards first, Custom Query second)** — Preset leaderboards are low-complexity queries; Custom Query is the most complex feature and should come last
6. **Data Status page** — Lowest risk, lowest complexity; can ship alongside any other page

**Defer to post-v1:** Everything in Anti-Features above.

---

## Sources and Confidence

| Finding | Source | Confidence |
|---------|--------|------------|
| Y-axis inversion for rank charts | Domo bump chart docs, Microsoft Research rank visualization paper | HIGH |
| Bottom nav as table stakes for mobile | Material Design, AppMySite 2025 guide, phone-simulator.com 2026 guide | HIGH |
| Debounce pattern + 300ms + min-2-char for search | Algolia autocomplete docs, Peterbe.com, DEV community articles | HIGH |
| Prototype feature set (all pages, data fields, interactions) | Direct read of BillboardStats.html source code | HIGH |
| SVG over charting libraries for static rank data | Derived from prototype implementation + bundle-size reasoning | MEDIUM |
| Custom query builder as differentiator | Verified by checking kworb.net feature set via web search | MEDIUM |
| Sports-reference density as UX differentiator for data sites | Sports-Reference.com blog, community discussion | MEDIUM |
