# Architecture Research

**Project:** Billboard Stats — Next.js App Router + Neon PostgreSQL
**Researched:** 2026-04-27
**Confidence:** HIGH (Context7 + official Neon/Next.js docs verified)

---

## Recommended Structure

```
billboard-stats/                  ← Next.js project root
├── app/
│   ├── layout.tsx                ← Root layout: Space Grotesk font, top nav, bottom nav
│   ├── page.tsx                  ← Redirects → /charts or renders Latest Charts
│   │
│   ├── charts/
│   │   └── page.tsx              ← Server Component: HOT 100 / B200 toggle + week selector
│   │
│   ├── search/
│   │   └── page.tsx              ← Server Component: receives ?q= param, renders results
│   │
│   ├── records/
│   │   └── page.tsx              ← Server Component: preset leaderboards + query builder
│   │
│   ├── status/
│   │   └── page.tsx              ← Server Component: table row counts + latest chart dates
│   │
│   ├── songs/[id]/
│   │   └── page.tsx              ← Server Component: stats bar, SVG run, history table
│   │
│   ├── albums/[id]/
│   │   └── page.tsx              ← Server Component: stats bar, SVG run, history table
│   │
│   ├── artists/[id]/
│   │   └── page.tsx              ← Server Component: stats bar, songs table, albums table
│   │
│   └── api/                      ← Route Handlers (used by Client Components only)
│       ├── charts/route.ts       ← GET ?date=&type=
│       ├── search/route.ts       ← GET ?q=&types=
│       ├── records/route.ts      ← GET ?preset=&limit=
│       ├── songs/[id]/route.ts   ← GET
│       ├── albums/[id]/route.ts  ← GET
│       ├── artists/[id]/route.ts ← GET
│       └── status/route.ts       ← GET
│
├── lib/
│   ├── db.ts                     ← Single db client export (Pool + attachDatabasePool)
│   ├── queries/
│   │   ├── charts.ts             ← Translated from chart_service.py
│   │   ├── songs.ts              ← Translated from song_service.py
│   │   ├── albums.ts             ← Translated from album_service.py
│   │   ├── artists.ts            ← Translated from artist_service.py
│   │   ├── records.ts            ← Translated from records_service.py
│   │   └── status.ts             ← Translated from data_status_service.py
│   └── types.ts                  ← TypeScript interfaces matching Python Pydantic schemas
│
├── components/
│   ├── nav/
│   │   ├── TopNav.tsx
│   │   └── BottomNav.tsx
│   ├── charts/
│   │   ├── ChartTable.tsx        ← "use client" for interactive toggle/week selector
│   │   └── MovementBadge.tsx
│   ├── search/
│   │   └── SearchTabs.tsx        ← "use client" for tab interaction
│   ├── detail/
│   │   ├── StatsBar.tsx
│   │   ├── ChartRunSVG.tsx       ← SVG visualization, can be Server Component
│   │   └── HistoryTable.tsx
│   └── ui/                       ← Shared primitives (buttons, badges, etc.)
│
└── public/
```

**Rationale for this layout:**

- `app/api/` route handlers exist alongside page routes — not in a separate top-level `api/` dir. This is the App Router convention (route.ts at any level).
- `lib/queries/` mirrors the Python `services/` layer 1:1 — one file per domain — making translation straightforward and reviewable.
- `lib/db.ts` is a singleton export. Never instantiate Pool inside query functions; always import from here.
- Server Components own initial page renders and call `lib/queries/` directly. Route Handlers exist only for interactive Client Component requests (e.g., changing the chart week after initial load, live search input).

---

## Data Fetching Pattern

### Rule: Server Components fetch directly; Route Handlers serve Client Components

Official Next.js docs state explicitly: "For Server Components, data should be fetched directly from its source, not via Route Handlers. For Server Components rendered on demand, fetching from Route Handlers is slower due to an extra HTTP round trip."

**Pattern A — Initial page render (Server Component calling lib/queries directly):**

```typescript
// app/songs/[id]/page.tsx
import { getSong, getChartRun } from '@/lib/queries/songs'
import { unstable_cache } from 'next/cache'

const getCachedSong = unstable_cache(
  async (id: number) => getSong(id),
  ['song'],
  { revalidate: 3600, tags: ['songs'] }
)

export default async function SongPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const [song, chartRun] = await Promise.all([
    getCachedSong(Number(id)),
    getCachedChartRun(Number(id)),
  ])
  // render directly — no fetch() to /api/songs/[id]
}
```

**Pattern B — Interactive Client Component (tab switching, week selection, live search):**

```typescript
// Client Component in components/charts/ChartTable.tsx
'use client'

async function loadChart(date: string, type: string) {
  const res = await fetch(`/api/charts?date=${date}&type=${type}`)
  return res.json()
}
```

```typescript
// app/api/charts/route.ts
import { type NextRequest } from 'next/server'
import { getWeeklyChart } from '@/lib/queries/charts'
import { unstable_cache } from 'next/cache'

export async function GET(request: NextRequest) {
  const date = request.nextUrl.searchParams.get('date')
  const type = request.nextUrl.searchParams.get('type') ?? 'hot-100'

  const getCached = unstable_cache(
    () => getWeeklyChart(date!, type),
    ['chart', date!, type],
    { revalidate: 3600, tags: ['charts'] }
  )

  const data = await getCached()
  return Response.json(data)
}
```

### Caching Strategy (three layers)

| Layer | Tool | Scope | Lifetime | Use For |
|-------|------|-------|----------|---------|
| Request dedup | `React.cache()` | Single render pass | Request lifetime | Prevent double queries when same data needed in multiple components on one page |
| Cross-request cache | `unstable_cache()` | Server process | `revalidate` seconds | Chart data, song/album/artist detail, records leaderboards |
| HTTP cache | `Cache-Control` header | CDN / browser | Explicit TTL | Route Handler responses consumed by browsers |

**Concrete TTL recommendations for this read-heavy, ETL-driven dataset:**

| Data | TTL | Reasoning |
|------|-----|-----------|
| Weekly chart (specific date) | 1 hour | Historical weeks never change; current week may change if ETL reruns |
| Song/album/artist detail + stats | 1 hour | Stats only rebuild when ETL runs (weekly cadence) |
| Records leaderboards | 1 hour | Same ETL cadence |
| Available chart dates list | 30 min | Can grow weekly |
| Data status (row counts, latest date) | 5 min | Useful for seeing ETL freshness quickly |
| Search results | 10 min | Fuzzy results are stable; short TTL for responsiveness to new data |

`unstable_cache` is the correct primitive here — it works with raw SQL queries that don't go through `fetch()`, which is the pattern throughout this codebase.

**Do not** use `export const dynamic = 'force-static'` on Route Handlers that accept query parameters (date, type, search query) — they cannot be statically generated.

---

## Database Connection

### Recommended: `pg` (node-postgres) + `@vercel/functions` `attachDatabasePool`

Neon's own documentation (as of 2025-2026) recommends **standard TCP pooling with `pg`** for Vercel Functions. Vercel Fluid keeps functions warm long enough to reuse connections, making `pg` Pool with `attachDatabasePool` the fastest option for repeated queries in a read-heavy app.

The `@neondatabase/serverless` neon() HTTP driver is better for edge runtime or single-query cold-start scenarios. Since these API routes run on Node.js runtime (required for `pg`), and the app is read-heavy with multiple queries per page, `pg` + pool is the right call.

**`lib/db.ts` — the only place Pool is created:**

```typescript
import { Pool } from 'pg'
import { attachDatabasePool } from '@vercel/functions'

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  max: 5,         // Neon recommends keeping this low for serverless
  idleTimeoutMillis: 10_000,
  connectionTimeoutMillis: 5_000,
})

// Closes idle connections before Vercel suspends the function
attachDatabasePool(pool)

export { pool }
```

**`lib/queries/songs.ts` — usage pattern:**

```typescript
import { pool } from '@/lib/db'
import { cache } from 'react'

export const getSong = cache(async (id: number) => {
  const { rows } = await pool.query(
    'SELECT id, title, artist_credit, image_url FROM songs WHERE id = $1',
    [id]
  )
  return rows[0] ?? null
})
```

**Key rules:**

- Pool is created once at module scope, outside any request handler — this is correct for Vercel Fluid (where the module persists across warm requests). This is the **opposite** of the pattern for `@neondatabase/serverless` Pool, which must be created inside the handler.
- `max: 5` — Neon's PgBouncer is in transaction mode. Keeping the client-side pool small prevents exhausting Neon's 64-connection limit on the free tier.
- Always use `process.env.DATABASE_URL` — Neon's Vercel integration sets this automatically with the pooler URL (hostname contains `-pooler`).
- No `pool.end()` calls in route handlers — `attachDatabasePool` handles the lifecycle.

### Connection string

Neon provides two URLs:
- **Direct:** `postgres://user:pass@ep-xxx.us-east-2.aws.neon.tech/billboard` — use for ETL only
- **Pooler:** `postgres://user:pass@ep-xxx-pooler.us-east-2.aws.neon.tech/billboard?sslmode=require` — use for Vercel (set as `DATABASE_URL`)

The Neon Vercel integration sets `DATABASE_URL` to the pooler URL automatically when you connect via the Neon dashboard integration.

---

## pg_trgm from TypeScript

pg_trgm queries translate directly to parameterized SQL — no special driver support needed. The `%` operator and `similarity()` function are standard SQL identifiers; only the values are parameterized.

### The critical escaping issue

In psycopg2 (Python), `%` in SQL must be escaped as `%%` because `%s` is the placeholder syntax. In `pg` (node-postgres), the placeholder is `$1`, so `%` is used literally in SQL strings — **no escaping needed**.

**Python original (song_service.py):**
```python
WHERE s.title %% %s   # %% = literal %, %s = parameter
```

**TypeScript translation (`lib/queries/songs.ts`):**
```typescript
export async function searchSongs(query: string, limit = 20) {
  const { rows } = await pool.query<SongSearchRow>(
    `SELECT s.id, s.title, s.artist_credit, s.image_url,
            ss.total_weeks, ss.peak_position, ss.weeks_at_number_one,
            ss.weeks_at_peak, ss.debut_date, ss.last_date, ss.debut_position,
            similarity(s.title, $1) AS sim
     FROM songs s
     LEFT JOIN song_stats ss ON s.id = ss.song_id
     WHERE s.title % $2
     ORDER BY sim DESC
     LIMIT $3`,
    [query, query, limit]
  )
  return rows
}
```

Note: `%` in a JavaScript template string or regular string is just `%` — it's not special. `$1`, `$2`, `$3` are the pg parameterization syntax.

### Multi-entity search (songs + albums + artists in one query)

```typescript
export async function searchAll(query: string, limit = 10) {
  const { rows } = await pool.query(
    `SELECT 'song' AS type, s.id, s.title AS name, s.artist_credit,
            similarity(s.title, $1) AS sim
     FROM songs s WHERE s.title % $2
     UNION ALL
     SELECT 'album', a.id, a.title, a.artist_credit,
            similarity(a.title, $1)
     FROM albums a WHERE a.title % $2
     UNION ALL
     SELECT 'artist', ar.id, ar.name, '' AS artist_credit,
            similarity(ar.name, $1)
     FROM artists ar WHERE ar.name % $2
     ORDER BY sim DESC
     LIMIT $3`,
    [query, query, limit]
  )
  return rows
}
```

### Adjusting similarity threshold

The default threshold is 0.3 (controlled by `pg_trgm.similarity_threshold`). For this music search domain, 0.3 is usually appropriate. To lower the threshold for broader matches, use explicit comparison instead of the `%` operator:

```typescript
// Explicit threshold in the query — avoids SET commands that don't survive pooled connections
WHERE similarity(s.title, $1) > 0.2
ORDER BY similarity(s.title, $1) DESC
```

**Do not** use `SET pg_trgm.similarity_threshold = 0.2` in a pooled connection — PgBouncer in transaction mode returns connections to the pool between transactions, so session-level SET statements do not persist. Use the explicit `similarity(col, $1) > threshold` form instead.

### Index requirement

pg_trgm is already in use in the existing database (as confirmed in STACK.md). GIN indexes on the searchable columns (`songs.title`, `albums.title`, `artists.name`) must exist for the `%` operator to use the index. These should already be present; confirm before running search queries at scale.

---

## Component Boundaries

```
Browser (Client Components)
  |
  | HTTP fetch /api/*
  v
Route Handlers (app/api/*/route.ts)
  |
  | Import
  v
Query Layer (lib/queries/*.ts)          ← Also called directly by Server Components
  |
  | SQL via pg Pool
  v
Neon PostgreSQL (existing schema)
  |
  | ETL writes (separate Python process)
  v
ETL Pipeline (billboard_stats/ — unchanged)
```

**What crosses which boundary:**

| From | To | How | What |
|------|----|-----|------|
| Server Component (page.tsx) | Query layer | Direct import + await | All initial page data |
| Client Component | Route Handler | fetch() | Interactive updates (date change, search input) |
| Route Handler | Query layer | Direct import + await | Same query functions, no duplication |
| Query layer | Neon | pg Pool.query() | Parameterized SQL |
| ETL pipeline | Neon | psycopg2 (unchanged) | Direct connection string |

The query layer (`lib/queries/`) is the single source of truth for all SQL. Neither page.tsx files nor Route Handlers contain SQL inline — they call query functions.

---

## Data Flow

**Initial page load (SSR path):**
```
URL request → Next.js routing → app/charts/page.tsx (Server Component)
  → unstable_cache(getWeeklyChart) → lib/queries/charts.ts
  → pool.query(...) → Neon PostgreSQL
  → rows → TypeScript types → React Server Component renders HTML
  → HTML + hydration bundle → browser
```

**Interactive update (e.g., user changes chart week):**
```
User clicks week selector (Client Component) → fetch('/api/charts?date=...&type=...')
  → app/api/charts/route.ts → unstable_cache(getWeeklyChart)
  → lib/queries/charts.ts → Neon PostgreSQL
  → JSON response → Client Component re-renders table
```

**Search (live input):**
```
User types in search box (Client Component, debounced 300ms)
  → fetch('/api/search?q=...')
  → app/api/search/route.ts → searchAll() in lib/queries/
  → pool.query with pg_trgm similarity → Neon PostgreSQL
  → JSON response → Client Component renders tabbed results
```

---

## Build Order

Build in this dependency order — each phase unblocks the next.

**1. Foundation (everything else depends on this)**
- `lib/db.ts` — Pool creation and `attachDatabasePool`
- `lib/types.ts` — TypeScript interfaces for all entities (Song, Album, Artist, ChartEntry, SongStats, etc.) — translate from `models/schemas.py`
- Environment: `DATABASE_URL` wired to Neon in `.env.local` and Vercel project settings

**2. Query layer (`lib/queries/*.ts`)**
- Translate service files 1:1. Recommended order: `charts.ts` → `songs.ts` → `albums.ts` → `artists.ts` → `records.ts` → `status.ts`
- Test each query file independently with a simple script before building UI
- The `_VALID_HOT100_WEEKS_CTE` and `_VALID_B200_WEEKS_CTE` from Python `stats_builder.py` must be translated to TypeScript constants in `lib/queries/charts.ts`

**3. Layout and navigation**
- `app/layout.tsx` — root HTML, Space Grotesk font import, top nav shell
- `components/nav/TopNav.tsx` and `BottomNav.tsx` — both as Client Components (nav state)

**4. Data Status page** (simplest — single query, static table)
- `app/status/page.tsx` + `lib/queries/status.ts`
- Good smoke test: confirms Neon connection, query layer, and Server Component pattern all work

**5. Charts page** (high value, validates week-selector interactivity pattern)
- `lib/queries/charts.ts`
- `app/charts/page.tsx` (initial SSR load)
- `app/api/charts/route.ts` (week switching)
- `components/charts/ChartTable.tsx` (Client Component with toggle + week picker)

**6. Detail pages — Song, Album, Artist** (medium complexity, parallel build)
- `lib/queries/songs.ts`, `lib/queries/albums.ts`, `lib/queries/artists.ts`
- `app/songs/[id]/page.tsx`, `app/albums/[id]/page.tsx`, `app/artists/[id]/page.tsx`
- `components/detail/StatsBar.tsx`, `ChartRunSVG.tsx`, `HistoryTable.tsx`
- These are pure Server Components (no interactive state on initial load)

**7. Search page** (requires all entity query layers to exist)
- `lib/queries/` — searchSongs, searchAlbums, searchArtists (or combined searchAll)
- `app/api/search/route.ts`
- `app/search/page.tsx` (initial SSR with `?q=` param)
- `components/search/SearchTabs.tsx` (Client Component)

**8. Records page** (depends on records_service.py translation, most complex query logic)
- `lib/queries/records.ts`
- `app/records/page.tsx`
- `app/api/records/route.ts` (for custom query builder interactions)

---

## Sources

- [Next.js App Router — Route Handlers](https://nextjs.org/docs/app/getting-started/route-handlers) — HIGH confidence (official, fetched 2026-04-27, version 16.2.4)
- [Next.js — Server Components vs Route Handlers caveat](https://nextjs.org/docs/app/guides/backend-for-frontend) — HIGH confidence (official, explicit warning against using Route Handlers from Server Components)
- [Next.js — Project Structure](https://nextjs.org/docs/app/getting-started/project-structure) — HIGH confidence (official, fetched 2026-04-27, version 16.2.4)
- [Next.js — unstable_cache](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/04-functions/unstable_cache.mdx) — HIGH confidence (Context7, canonical)
- [Next.js — React cache deduplication](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/caching-without-cache-components.mdx) — HIGH confidence (Context7, canonical)
- [Neon — Choosing connection method](https://neon.com/docs/connect/choose-connection) — HIGH confidence (official Neon docs, fetched 2026-04-27)
- [Neon — Connecting from Vercel](https://neon.com/docs/guides/vercel-connection-methods) — HIGH confidence (official Neon docs, fetched 2026-04-27)
- [@neondatabase/serverless — Pool and neon() patterns](https://github.com/neondatabase/serverless/blob/main/README.md) — HIGH confidence (Context7, official repo)
- [Neon — pg_trgm extension](https://neon.com/docs/extensions/pg_trgm) — HIGH confidence (official Neon docs)
- [PostgreSQL — pg_trgm documentation](https://www.postgresql.org/docs/current/pgtrgm.html) — HIGH confidence (official PostgreSQL docs)
