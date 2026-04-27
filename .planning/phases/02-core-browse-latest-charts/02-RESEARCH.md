# Phase 2: Core Browse & Latest Charts - Research

**Researched:** 2026-04-27
**Domain:** Next.js App Router browse UI backed by PostgreSQL chart snapshot APIs
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

No user constraints - all decisions at the agent's discretion
</user_constraints>

<architectural_responsibility_map>
## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Global shell and responsive navigation | Browser/Client | CDN/Static | Navigation chrome and mobile/desktop adaptation are presentational concerns. |
| Latest chart page initial render | Frontend Server | API/Backend | The server should fetch the initial chart payload for fast first paint and direct route loads. |
| Chart/week switching interactions | Browser/Client | Frontend Server | Toggle and selector state are client concerns, but they call server-backed endpoints for new data. |
| Weekly chart snapshot retrieval | API/Backend | Database/Storage | Existing service queries already define the canonical chart snapshot shape. |
| Data freshness indicator | API/Backend | Database/Storage | Counts and latest chart dates come from aggregated DB queries, not client-derived state. |

</architectural_responsibility_map>

<research_summary>
## Summary

Phase 2 should be planned as a vertical slice around the main browsing experience rather than as separate "layout first, then APIs, then page" layers. The existing Python service layer already exposes the two backend capabilities this phase needs: weekly chart snapshots with available chart dates, and aggregate data status summaries. That means the main planning risk is not query design, but how to translate those capabilities into a Next.js 16 App Router structure that supports a fast initial render, chart/week switching, and navigation patterns consistent with the HTML prototype.

The prototype establishes the user-facing contract: a shell with nav entries for Latest Charts, Search, Records, and Data Status; a Hot 100/Billboard 200 toggle; a week selector; dense ranked tables with movement indicators; and a compact status view showing latest dates and row counts. The cleanest implementation path is to keep route handlers thin, reuse the existing query semantics from the Python service layer, and isolate client interactivity into small client components nested inside server-rendered pages.

**Primary recommendation:** Plan Phase 2 as three coordinated slices: shell/navigation, chart/status APIs, and the Latest Charts plus Data Status UI built against those APIs and the prototype contract.
</research_summary>

<standard_stack>
## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Next.js | 16.x | App Router pages, layouts, and route handlers | Already chosen in Phase 1 and provides the server/client split Phase 2 needs. |
| React | 19.x | Interactive chart toggles, selectors, and table state | Native fit for small client islands inside server-rendered pages. |
| Tailwind CSS | 4.x | Dense, token-driven prototype styling | Already configured and supports the compact table-heavy UI without adding a component framework. |
| @neondatabase/serverless | 1.x | Postgres access from route handlers | Already installed and aligned with the Neon deployment target. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| next/link | bundled | Route navigation to future detail pages | Use for shell nav and row click-through points where a real route exists. |
| next/navigation | bundled | Search params / router state for chart and week selection | Use if week/chart state should become URL-addressable. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled fetch state on every page | React Query / SWR | Helpful later for caching, but unnecessary overhead for a single browse slice right now. |
| Pure client-side page bootstrapping | Server component page + small client islands | Server-first rendering gives better direct loads and simpler data flow for this read-only app. |

**Installation:**
```bash
# No additional packages are required for the recommended Phase 2 baseline.
```
</standard_stack>

<architecture_patterns>
## Architecture Patterns

### System Architecture Diagram

```text
Browser request
  -> App Router page (/ or /charts)
    -> server-side chart bootstrap query
      -> route-safe DB helper
        -> Neon PostgreSQL
    -> render shell + initial chart/status payload
      -> client chart controls (chart toggle, week select)
        -> route handlers (/api/charts, /api/data-status)
          -> Python-query-equivalent SQL in TS
            -> Neon PostgreSQL
      -> dense tables + status panel update
```

### Recommended Project Structure
```text
src/
├── app/
│   ├── (browse)/
│   │   ├── layout.tsx        # shell for nav and shared browse chrome
│   │   ├── page.tsx          # latest charts page
│   │   └── status/page.tsx   # data status page, if split into its own route
│   └── api/
│       ├── charts/route.ts
│       └── data-status/route.ts
├── components/
│   ├── shell/
│   └── charts/
└── lib/
    ├── db.ts
    ├── charts.ts
    └── data-status.ts
```

### Pattern 1: Server-first page with client control island
**What:** Fetch the initial page payload in a server component, then hand off only the interactive controls and mutable table region to a client component.
**When to use:** For the Latest Charts page where direct route loads should be fast but the user still needs in-page toggles.
**Example:** The page loads the newest Hot 100 snapshot server-side, then a client child handles chart/week changes by calling route handlers.

### Pattern 2: Thin route handlers over service helpers
**What:** Move SQL into `src/lib/*` helpers and keep `route.ts` files focused on request parsing and response serialization.
**When to use:** For `/api/charts` and `/api/data-status`, where the backend contract should mirror the existing Python service layer cleanly.
**Example:** `src/lib/charts.ts` exposes `getWeeklyChart()` and `getAvailableDates()`, while `src/app/api/charts/route.ts` validates `chart` and `date` inputs and returns JSON.

### Anti-Patterns to Avoid
- **Horizontal slicing the phase:** Building "all APIs first" and "all UI later" creates unnecessary handoff friction and obscures whether the browse flow works end to end.
- **Client-only initial loads:** Making the page boot empty and fetch everything after mount will regress perceived performance and complicate route-level testing.
- **Prototype drift:** Treating the HTML prototype as inspiration instead of contract will make later detail/search phases harder to align visually.
</architecture_patterns>

<dont_hand_roll>
## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Navigation state | Custom history stack in app state | App Router routes and `next/link` | Native routing keeps future detail/search pages composable. |
| Dense table behavior | Full custom grid abstraction | Plain semantic tables with Tailwind classes | The prototype behavior is straightforward and does not justify a custom grid framework. |
| Server/client contract types | Ad hoc JSON shapes repeated in components | Shared TS mapping helpers in `src/lib` | Reused shapes reduce drift between route handlers and pages. |

**Key insight:** Phase 2 needs disciplined translation of an existing UI/backend contract, not framework invention.
</dont_hand_roll>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Over-coupling page state to one hardcoded chart
**What goes wrong:** The initial Hot 100 view works, but Billboard 200 or historical weeks require duplicated components or branching logic everywhere.
**Why it happens:** The data contract is not normalized around shared chart entry fields.
**How to avoid:** Define a shared chart row type and a single table renderer that accepts chart metadata plus rows.
**Warning signs:** Separate components emerge for Hot 100 and B200 before any meaningful schema differences appear.

### Pitfall 2: Fetching too much chart metadata on every interaction
**What goes wrong:** Each chart/week change refetches counts, dates, and full page chrome even though only the rows changed.
**Why it happens:** API boundaries are not separated between "chart snapshot" and "data status summary".
**How to avoid:** Keep chart snapshot and data status as separate fetch paths with stable, focused payloads.
**Warning signs:** One large route handler starts serving unrelated concerns because it is convenient.

### Pitfall 3: Losing URL/state coherence for week selection
**What goes wrong:** Users can interactively change chart/week, but refresh/back behavior becomes confusing and impossible to share.
**Why it happens:** State is kept only in local client state with no routing or query-param strategy.
**How to avoid:** Decide during planning whether chart/week belongs in search params or whether only latest-load routes are needed in v1.
**Warning signs:** The same selection state is duplicated in page, control, and fetch helper layers.
</common_pitfalls>

<code_examples>
## Code Examples

### Existing chart snapshot contract
```python
def get_weekly_chart(chart_date: date, chart_type: str = "hot-100") -> List[ChartEntry]:
    ...
```
Source: `billboard_stats/services/chart_service.py`

### Existing available-dates contract
```python
def get_available_dates(chart_type: str = "hot-100") -> List[date]:
    ...
```
Source: `billboard_stats/services/chart_service.py`

### Existing data status summary contract
```python
def get_data_summary() -> dict:
    ...
```
Source: `billboard_stats/services/data_status_service.py`
</code_examples>

<sota_updates>
## State of the Art (2024-2025)

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Monolithic client-rendered pages | Server components with targeted client islands | Next.js 13-16 era | Better initial render and simpler data loading for read-only browse flows. |
| Tailwind config-first tokens | Tailwind v4 CSS `@theme` tokens | Tailwind v4 | Phase 2 styling should extend `globals.css` tokens rather than assume `tailwind.config.ts`. |
| External Google font dependency | Local or build-hosted `next/font` assets | Ongoing, reinforced by restricted build envs | Keep the bundled local font approach from Phase 1. |

**New tools/patterns to consider:**
- Route handlers as first-party JSON APIs for internal page fetches.
- Query-param-driven browse state if shareable chart/week views matter in v1.

**Deprecated/outdated:**
- Treating App Router pages like client-only SPA views.
- Adding a new styling system on top of the existing Tailwind v4 baseline.
</sota_updates>

<open_questions>
## Open Questions

- Should Data Status live as its own route in Phase 2, or as a panel surfaced from the main browse shell while preserving the nav contract?
- Should chart type and week selection be reflected in the URL for shareability, or kept as internal interactive state for the first cut?
- Does Phase 2 need clickable row navigation wired to placeholder detail routes immediately, or can link targets wait for Phase 3 as long as the shell structure is ready?
</open_questions>
