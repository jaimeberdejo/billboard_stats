# Phase 4: Search & Records - Research

**Researched:** 2026-04-28
**Domain:** Next.js search and records interfaces backed by PostgreSQL fuzzy search and leaderboard queries
**Confidence:** HIGH

<user_constraints>
## User Constraints

- Ship the HTML prototype faithfully before inventing a different search or records IA.
- Preserve the established dense newsroom UI and avoid card-heavy dashboard patterns.
- Keep the app server-first where practical, but use small client islands for interactions that require immediate updates.

</user_constraints>

<research_summary>
## Summary

Phase 4 is the final public-discovery slice for the milestone. The Python app and prototype already define most of the behavior: search begins at 2 characters, results are entity-tabbed, record leaderboards are chart-filtered, and the custom query builder is sentence-driven rather than form-driven. The clean Next.js translation is to keep data access in typed server-side lib helpers, expose narrow internal API routes for the interactive surfaces, and render Search and Records as compact client islands inside the existing page shells.

The main planning risk is scope drift between the prototype and the fuller Streamlit records implementation. The prototype demonstrates the layout and the custom-query interaction style, while the Streamlit app defines the complete record set and drilldown rules. The best plan is to preserve the prototype’s layout language but implement the full Streamlit-backed record catalog, since the milestone requirement says preset leaderboards must be accurate rather than demo-only.

</research_summary>

<backend_contracts>
## Existing Backend Contracts to Preserve

### Search services
- `artist_service.search_artists(query, limit=50)` returns artist rows with `id`, `name`, and high-level stats needed for dense artist result rows.
- `song_service.search_songs(query, limit=50)` returns song rows with metadata plus stats such as peak position, total weeks, and weeks at peak.
- `album_service.search_albums(query, limit=50)` returns album rows with the same dense-table stats.

### Records services
- `records_service.py` already defines the preset leaderboard functions:
  - `most_weeks_at_number_one`
  - `longest_chart_runs`
  - `most_number_one_songs_by_artist`
  - `most_number_one_albums_by_artist`
  - `most_entries_by_artist`
  - `most_simultaneous_entries`
  - `biggest_debuts`
  - `fastest_to_number_one`
- It also defines artist-level drilldown helpers and a typed `custom_query()` entry point for the natural-language query builder.

### Key implication
- Phase 4 does not need novel product logic. It needs TypeScript translations of the Python service contracts, plus page composition and client interaction layers on top.

</backend_contracts>

<ui_contract_from_prototype>
## UI Contract From Prototype

### Search
- One prominent text input at the top of the page
- Tabs for `Songs`, `Albums`, and `Artists`
- Result counts shown inline with tab labels after the query is valid
- Dense result tables, not card grids
- Neutral inline empty states

### Records
- Compact top control bar with record selector, chart toggle, and result count
- Natural-language custom query builder with inline numeric controls
- Optional secondary filter panel for peak, debut, artist, and week filters
- Leaderboard rows that can either navigate directly or expand inline drilldowns
- No large cards, hero modules, or new side-navigation concepts

</ui_contract_from_prototype>

<recommended_project_structure>
## Recommended Project Structure

```text
src/
├── app/
│   ├── api/
│   │   ├── search/route.ts
│   │   └── records/route.ts
│   ├── search/page.tsx
│   └── records/page.tsx
├── components/
│   ├── search/
│   │   ├── search-view.tsx
│   │   └── search-results-table.tsx
│   └── records/
│       ├── records-view.tsx
│       ├── leaderboard-list.tsx
│       ├── custom-query-builder.tsx
│       └── artist-drilldown.tsx
└── lib/
    ├── search.ts
    └── records.ts
```

This keeps SQL translation in `lib`, request validation in API routes, and interactive rendering inside focused client components.

</recommended_project_structure>

<architecture_patterns>
## Architecture Patterns

### Pattern 1: Server helper + API route + client island
The existing codebase already uses typed server helpers and route validation. Search and Records should follow the same layering: lib helpers for SQL, API routes for validation/serialization, and client islands for high-frequency interaction.

### Pattern 2: One unified search response
Returning all three entity groups from a single `/api/search` request keeps tab counts synchronized and avoids one request per tab.

### Pattern 3: Mode-based records API
The records surface has many related query shapes. A single `/api/records` route with explicit modes (`preset`, `custom`, `drilldown`) is simpler for the client than a route explosion and still keeps validation explicit.

### Pattern 4: Prototype layout, Streamlit coverage
Use the prototype as the visual contract and the Streamlit app as the complete behavioral contract where the prototype is intentionally abbreviated.

</architecture_patterns>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Over-clientizing Search
Pulling database logic into client components or fetching directly from server actions on every render would fight the established route pattern and make validation less explicit.

### Pitfall 2: Shrinking the records scope to the prototype demo
The prototype only shows a subset of record types, but the milestone requirement and Python backend already support more. Planning must preserve the broader records capability.

### Pitfall 3: Breaking dense-table consistency
Switching Search or Records to cards, badges, or dashboard panels would drift from the rest of the app and from the prototype.

### Pitfall 4: Forgetting unsupported chart/record combinations
Some record types are chart-specific. The Next.js UI needs explicit informative states instead of empty results that look broken.

</common_pitfalls>

<validation_targets>
## Validation Targets For Planning

- Search only triggers once the query reaches 2 characters
- Search tabs show synchronized counts for songs, albums, and artists
- Search rows navigate to the correct Phase 3 detail pages
- Records preset leaderboards accurately match the existing backend functions
- Custom query builder produces top-50 filtered results with the sentence-driven control model
- Artist-scoped record rows support inline drilldown where the underlying record type warrants it

</validation_targets>
