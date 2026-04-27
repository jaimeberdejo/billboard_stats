# Pitfalls Research

**Project:** Billboard Stats — Next.js + Neon + Vercel
**Domain:** Read-heavy public data app with complex SQL, pg_trgm fuzzy search, serverless deployment
**Researched:** 2026-04-27
**Overall confidence:** HIGH (all pitfalls verified against official Neon docs, Vercel docs, Next.js docs)

---

## Connection & Serverless Pitfalls

### CRITICAL: Using the Direct (Unpooled) Connection String from a Serverless Function

**What goes wrong:** Every Vercel function invocation opens a new raw TCP connection to Postgres. Under load (or even modest traffic), you exhaust Neon's `max_connections` limit (419 for a 1 CU compute). New requests get connection refused errors. The free tier compute is 0.25 CU, which means even fewer available connections.

**Why it happens:** Developers copy the connection string from Neon's dashboard without enabling the `-pooler` flag, or they use `DATABASE_URL_UNPOOLED` (which Neon also exposes) for all queries.

**Consequences:** 503/500 errors under load; hard to reproduce locally; appears fine in development.

**Prevention:**
- Always use the pooled connection string for API routes: the hostname contains `-pooler` (e.g., `ep-cool-darkness-123456-pooler.us-east-2.aws.neon.tech`).
- Neon's Vercel integration now defaults `DATABASE_URL` to the pooled string and exposes `DATABASE_URL_UNPOOLED` separately. Reserve the unpooled string for migrations and `pg_dump`/`pg_restore` only.
- Verify the environment variable in use before deploying.

**Detection:** Connection count spiking in Neon metrics; `remaining_connections` query returns near zero; errors under concurrent load in staging.

**Phase:** Phase that sets up database infrastructure and the `db` singleton.

---

### CRITICAL: Creating a New pg Pool/Client Outside the Request Handler

**What goes wrong:** A module-level `new Pool()` without `attachDatabasePool` is created once per cold start. The pool holds idle connections open. Vercel suspends the function while the connections are held, causing connection leaks. Eventually the database hits max connections.

**Why it happens:** Developers follow patterns from long-running server guides that create a singleton pool at module scope, which works differently in serverless.

**Consequences:** Connection exhaustion over time; errors that are intermittent and hard to debug because they only appear under sustained traffic.

**Prevention:**
- Use `@vercel/functions` `attachDatabasePool(pool)` to hand the pool lifecycle to Vercel Fluid Compute. This allows TCP connections to be reused across invocations and gracefully closed before the function suspends.
- If not using Fluid Compute, create and destroy the connection inside each handler, or use Neon's HTTP transport (`@neondatabase/serverless` with `neon()`) for single-query-per-request patterns.
- Neon's serverless driver HTTP mode is stateless and requires no connection management — it is the safest default for simple read queries.

**Detection:** Rising `pg_stat_activity` count that never drops; "too many connections" errors after sustained traffic.

**Phase:** Foundational db client setup — get this right before any other route is built.

---

### MODERATE: Forgetting to Close Connections When Not Using a Pool Manager

**What goes wrong:** If not using `attachDatabasePool` or the HTTP driver, each `Client` or `Pool` must be explicitly closed at the end of the handler. Leaving them open leaks file descriptors (Vercel limit: 1,024 across all concurrent executions) and database connections simultaneously.

**Prevention:**
- Always wrap manual connection usage in try/finally: `await client.end()` in the finally block.
- Prefer the managed patterns (Neon HTTP driver or `attachDatabasePool`) over manual lifecycle management.

**Detection:** "Too many open files" errors; rising connection count without traffic increase.

---

### MODERATE: PgBouncer Transaction Mode Breaks Session-Scoped Features

**What goes wrong:** Neon's pooler runs PgBouncer in transaction mode. Connections are returned to the pool after each transaction, which means session state is lost between statements. The following all silently fail or produce errors:

- `SET search_path = ...` (forgotten after transaction ends)
- Temporary tables (gone after transaction)
- `PREPARE` / `EXECUTE` SQL statements (protocol-level prepared statements via pg driver are fine; SQL-level are not)
- `LISTEN` / `NOTIFY`
- Session-level advisory locks

**Why it happens:** Developers test against a local Postgres where sessions persist, then hit Neon's pooler in production.

**Consequences:** Queries return wrong results if relying on `search_path`; application-level prepared statements fail; rare but silent data correctness bugs.

**Prevention:**
- Do not rely on session state. If `search_path` needs to be set, do it at the role level: `ALTER ROLE myuser SET search_path = myschema`.
- For this project: no session-scoped features are needed (read-only queries, no advisory locks, no temp tables). Verify no SQL-level `PREPARE` statements are emitted by the pg driver.
- Note: `pg` (node-postgres) uses protocol-level prepared statements by default, which PgBouncer 1.22+ supports. This is safe.

**Detection:** `SET` commands silently ignored; queries landing in wrong schema; prepared statement name errors.

**Phase:** Connection infrastructure phase; verify immediately when first API route hits Neon.

---

## Neon-Specific Gotchas

### CRITICAL: Cold Start on First Request After Idle (Free Tier)

**What goes wrong:** Neon suspends compute after 5 minutes of inactivity by default. The free tier enforces scale-to-zero and it cannot be disabled. On resume, the first request waits for:
1. Compute wake-up: typically a few hundred milliseconds, p99 ~500ms
2. Cold memory buffers: the first queries hit disk, not memory cache. For this project's complex JOIN queries, the first query after a cold start can take 2-5 seconds.

**Why it happens:** A public read-only site with occasional traffic (weekends, off-hours) will go idle frequently. Visitors who arrive after an idle period experience the full cold start.

**Consequences:** First visitor after idle gets a slow page load (potentially timing out on Vercel's default 10s limit if queries are slow enough). Neon metrics show first-query duration spikes.

**Prevention:**
- On paid Neon plans: increase `suspend_timeout_seconds` or disable scale-to-zero for the production database. For a public-facing app, keeping compute warm is worth the small cost.
- Application-level: implement a lightweight "keep-warm" strategy — a scheduled Vercel cron job (free) hitting a `/api/health` endpoint that runs a `SELECT 1` query every 4 minutes. This is cheap and effective.
- Next.js response caching: cache chart and records data (which changes weekly at most) with `unstable_cache` and appropriate `revalidate` intervals. Cached responses are served without hitting the database, reducing the number of cold-start-exposing requests.
- Collocate Vercel deployment region and Neon compute region (e.g., both `us-east-1`).

**Warning signs:** Vercel function duration spikes visible in the dashboard; first-visitor complaints about slow load; `/api/health` monitoring alerts.

**Phase:** Infrastructure phase (region selection, environment setup) and performance phase (caching strategy).

---

### MODERATE: Compute Suspension Clears All Session State

**What goes wrong:** When Neon compute suspends, all active connections are closed and session context is wiped: prepared statements, temporary tables, advisory locks, LISTEN/NOTIFY configurations. Applications that rely on session state will silently lose it after any suspension.

**Why it happens:** Any idle period longer than 5 minutes (free tier: mandatory; paid: configurable) triggers suspension.

**Consequences for this project:** Low direct risk because the app is stateless (read-only queries, no session state). The main risk is with the ETL pipeline — if it uses session-level configuration or temp tables across a long-running job, a mid-run suspension could corrupt state.

**Prevention:** Ensure the ETL script reconnects and re-establishes any session state after each connection. Do not assume a connection stays alive across a long ETL run — add explicit connection health checks and reconnect logic.

---

### MODERATE: Branch Compute Costs Accumulate Silently

**What goes wrong:** The Neon-Vercel integration can create a database branch per Vercel preview deployment. Each branch gets its own compute. On the free tier (100 CU-hours/month, max 10 branches per project), branches from old PRs accumulate, consuming compute hours. The integration does not automatically delete obsolete preview branches.

**Consequences:** Free tier compute exhausted; unexpected charges on paid plans; stale preview environments with outdated data.

**Prevention:**
- Enable automatic branch deletion in Neon settings when the corresponding Git branch is deleted.
- For this project's single-developer workflow, consider skipping the Neon preview branching integration entirely — use a single `development` Neon branch instead of per-PR branches. The schema is stable and the data is read-only (no test mutations).

**Detection:** Branch count creeping up in Neon console; compute-hours usage higher than expected relative to production traffic.

---

### LOW: Neon Storage Limit on Free Tier (0.5 GB per project)

**What goes wrong:** Billboard chart history from 1958–present is likely 50-200 MB depending on data density. This fits the free tier (0.5 GB). However, if `pg_trgm` GIN indexes are large, or if the ETL adds significant history over time, storage can approach the limit. Exceeding 0.5 GB pauses writes.

**Prevention:** Run `SELECT pg_database_size(current_database())` immediately after migration to establish a baseline. Monitor monthly. If approaching 0.4 GB, upgrade to paid tier before writes pause.

---

## Data Migration Risks

### CRITICAL: Sequence Values Not Migrated Correctly (Duplicate Key Violations Post-Migration)

**What goes wrong:** `pg_dump` exports sequence current values, but after restore, sequences may start from 1 instead of the last inserted ID. The ETL pipeline inserts new rows after migration and gets duplicate primary key violations because the sequence is behind the max existing ID.

**Why it happens:** Subtle `pg_restore` behavior with `--no-owner` or when the sequence ownership is broken.

**Consequences:** ETL failures immediately after switching to Neon; potential data corruption if errors are swallowed silently.

**Prevention:**
- After restoring, run this validation for every table with a serial/identity column:
  ```sql
  SELECT setval(pg_get_serial_sequence('chart_weeks', 'id'),
                (SELECT MAX(id) FROM chart_weeks));
  ```
  Do this for all tables: `songs`, `albums`, `artists`, `chart_weeks`, and any junction tables.
- Do not point the ETL at Neon until sequences are validated.

**Detection:** `ERROR: duplicate key value violates unique constraint` on first ETL run after migration.

**Phase:** Migration phase — must be validated before ETL cutover.

---

### CRITICAL: Using the Pooled Connection String for pg_dump/pg_restore

**What goes wrong:** `pg_dump` and `pg_restore` require a direct (session-mode) connection. Running them through the PgBouncer pooled endpoint causes failures because PgBouncer transaction mode does not support the protocol features `pg_dump` relies on.

**Why it happens:** The Vercel-Neon integration sets `DATABASE_URL` to the pooled string by default. A developer copies this into the migration command.

**Consequences:** Dump/restore failures; corrupted or incomplete schema dumps.

**Prevention:**
- Always use `DATABASE_URL_UNPOOLED` (or the direct hostname without `-pooler`) for `pg_dump`, `pg_restore`, schema migration tools (Flyway, Liquibase, raw `psql` DDL).
- Keep both env vars documented and distinguished: pooled for app, unpooled for admin operations.

---

### MODERATE: ALTER OWNER Errors During Restore

**What goes wrong:** `pg_restore` emits `ALTER OWNER` statements for every object. Neon's `neon_superuser` role cannot execute these, causing non-fatal errors. Restore succeeds but the output log is full of errors, making it hard to detect real failures.

**Prevention:**
- Always restore with `--no-owner` and `--no-acl` flags:
  ```bash
  pg_restore --no-owner --no-acl -d "$DATABASE_URL_UNPOOLED" dump.fc
  ```
- Suppress the expected ownership noise so real errors are visible.

---

### MODERATE: Extension Availability Check Before Migration

**What goes wrong:** `pg_trgm` is a standard Postgres extension that Neon supports, but it must be explicitly enabled with `CREATE EXTENSION IF NOT EXISTS pg_trgm;`. If the extension exists in the local database dump but the restore user lacks `CREATE` privileges, or the extension is missing from the dump, the GIN indexes depending on `pg_trgm` will fail to create.

**Prevention:**
- Verify `pg_trgm` is active post-restore: `SELECT * FROM pg_extension WHERE extname = 'pg_trgm';`
- Enable manually if needed before running the index creation step:
  ```sql
  CREATE EXTENSION IF NOT EXISTS pg_trgm;
  ```
- Run a test migration on a Neon development branch before touching production.

**Detection:** Index creation errors during restore; search queries returning errors about missing operator class.

---

### MODERATE: Local vs. Neon PostgreSQL Version Mismatch

**What goes wrong:** Neon supports PostgreSQL 14–17. `pg_dump` from a newer local Postgres can produce output incompatible with an older Neon instance. Syntax differences in system catalogs and extension APIs cause restore failures.

**Prevention:**
- Check local Postgres version: `psql --version`
- Check Neon project version: visible in the Neon Console under Project Settings.
- Use `pg_dump` from the same version as the Neon target (use Docker if needed: `docker run postgres:16 pg_dump ...`).

---

### LOW: Large Object Incompatibility

**What goes wrong:** If the local database contains PostgreSQL large objects (unlikely for chart data, but possible if any binary blobs were stored), they are not supported by Neon.

**Prevention:** Run `pg_dump --no-blobs` to exclude them. They are unlikely to exist in a chart statistics database.

---

## Next.js App Router Mistakes

### CRITICAL: Calling Internal Route Handlers from Server Components

**What goes wrong:** A Server Component does `fetch('http://localhost:3000/api/charts')` to get data. This is unnecessary: both the Server Component and the Route Handler run on the same server. The extra HTTP round-trip adds latency, requires hardcoding the base URL (breaks in preview deployments), and bypasses TypeScript type safety.

**Why it happens:** Developers migrating from Pages Router patterns where `getServerSideProps` called API routes.

**Prevention:**
- In Server Components, call the data-fetching logic directly — import the query function and call it.
- Route Handlers (`/api/*`) exist only for client-side fetching, third-party webhooks, and browser-initiated requests.
- For this project: the Charts, Search, Records, and Status pages should query Neon directly in Server Components (or through a thin `lib/db/queries.ts` layer), not through `fetch('/api/...')`.

**Detection:** `fetch('http://localhost:3000/api/...')` appearing inside a `page.tsx` or `layout.tsx` file.

**Phase:** Every feature phase — establish this pattern in Phase 1.

---

### CRITICAL: Sequential Database Queries Creating Waterfalls

**What goes wrong:** An artist detail page needs artist stats, their Hot 100 songs, and their Billboard 200 albums. Writing this as three sequential `await` calls means each waits for the previous to finish. Total latency = sum of all three queries.

**Why it happens:** Natural `async/await` writing style runs queries sequentially by default.

**Consequences:** 3× the latency on detail pages. On a cold-start Neon compute, this compounds severely (each query hits cold buffers).

**Prevention:**
- Use `Promise.all` for independent queries:
  ```typescript
  const [artistStats, songs, albums] = await Promise.all([
    getArtistStats(id),
    getArtistHot100Songs(id),
    getArtistBillboard200Albums(id),
  ]);
  ```
- Apply this to all detail pages (artist, song, album) and the Records page (which fetches multiple leaderboards).

**Detection:** Function execution time = sum of individual query times; visible in Vercel function duration logs.

**Phase:** Every feature phase. Establish the pattern in the first detail page built, then follow it.

---

### CRITICAL: Placing Suspense Boundary Inside the Async Component

**What goes wrong:**
```tsx
// Wrong — Suspense is inside the component that does the fetch
export default async function ChartsPage() {
  const data = await getChartData(); // suspends here
  return (
    <Suspense fallback={<Spinner />}> // never reached during suspend
      <ChartTable data={data} />
    </Suspense>
  );
}
```
The Suspense boundary must be a parent of the component that suspends, not a child.

**Why it happens:** Mental model confusion about where the suspension point is.

**Consequences:** The fallback UI never renders; loading states are missing; users see blank pages or unhandled promise errors.

**Prevention:**
- Place `<Suspense>` in the parent component or layout, wrapping the async child:
  ```tsx
  // In layout.tsx or a parent page
  <Suspense fallback={<TableSkeleton />}>
    <ChartsTable />  {/* this component does the await */}
  </Suspense>
  ```
- Use `loading.tsx` files as a coarser-grained alternative for full-page loading states.

**Phase:** Every feature phase — especially the Charts page (initial phase) to establish the pattern.

---

### MODERATE: Adding "use client" Too High in the Component Tree

**What goes wrong:** Adding `'use client'` to a parent component (e.g., a layout or page wrapper) forces all children into the client bundle, even ones with no interactivity. This includes data-heavy Server Components, losing all the performance benefits of server rendering.

**Why it happens:** A developer needs one interactive element (a toggle button, a search input) and adds `'use client'` to the nearest parent instead of extracting a small client wrapper.

**Consequences:** Larger JS bundle shipped to the browser; database queries move client-side and expose connection strings; loss of server-side streaming.

**Prevention:**
- Keep `'use client'` as a leaf concern. Extract interactive elements into small wrapper components:
  ```
  // ChartPage.tsx (Server Component) — fetches data
  //   └── ChartTable.tsx (Server Component) — renders static table
  //         └── WeekSelectorButton.tsx ('use client') — handles click
  ```
- Rule of thumb: if a component only receives props and renders JSX (no `useState`, no browser APIs), it does not need `'use client'`.

**Detection:** `'use client'` appearing in `layout.tsx`, `page.tsx`, or wrapper components that contain data-fetching children.

---

### MODERATE: Not Caching Database Queries That Change Infrequently

**What goes wrong:** The Records page leaderboards (`most_weeks_at_1`, `longest_chart_run`, etc.) and the chart history queries are expensive SQL (aggregations, multi-table joins). If these re-run on every request with no caching, the app hammers the database for data that only changes weekly (after the ETL runs).

**Why it happens:** Developers unfamiliar with `unstable_cache` fall back to no-cache behavior (every request hits the database).

**Consequences:** Unnecessary load on Neon compute; increased latency for all visitors; higher CU-hours consumption (cost on paid plans).

**Prevention:**
- Wrap expensive, infrequently-changing queries with `unstable_cache` and a `revalidate` interval matching the ETL cadence (e.g., 3600s for daily updates, 604800s for weekly):
  ```typescript
  import { unstable_cache } from 'next/cache';

  export const getCachedRecordsLeaderboard = unstable_cache(
    async () => getRecordsLeaderboard(),
    ['records-leaderboard'],
    { revalidate: 3600, tags: ['records'] }
  );
  ```
- For the current chart page (changes weekly), use `revalidate: 86400` (daily) as a safe default.
- The search endpoint (user-driven, arbitrary input) should NOT be cached — queries are too varied and must be fresh.

**Detection:** Every page load appearing as a distinct Neon query in the database connection logs with no cache hits.

**Phase:** Can be added in a dedicated performance phase after initial feature implementation; but design the query layer with caching in mind from the start.

---

### MODERATE: Route Handler GET Caching Behavior Changed in Next.js 15

**What goes wrong:** In Next.js 14, `GET` Route Handlers were cached by default. In Next.js 15, `GET` Route Handlers are NOT cached by default. Developers who rely on cached behavior from 14 or assume caching without explicitly opting in get stale data or unexpectedly dynamic responses.

**Prevention:**
- Be explicit: if an API route should be cached, add `export const dynamic = 'force-static'`.
- If it must always be fresh (e.g., the current chart week), no annotation needed — dynamic by default.
- For this project: the `/api/charts/current` and `/api/search` routes should be dynamic; `/api/records/leaderboards` could be statically cached.

---

### LOW: Missing Error Boundaries for Async Server Components

**What goes wrong:** An async Server Component that throws (e.g., Neon connection error, query timeout) propagates the error to the entire page unless an error boundary wraps it. The user sees a full-page error instead of a graceful fallback.

**Prevention:**
- Create `error.tsx` files at the route segment level to handle thrown errors gracefully.
- For the search page especially: if the `pg_trgm` query fails (e.g., extension not enabled), return an empty result rather than crashing the page.

---

## Vercel Limits to Know

### Function Payload: 4.5 MB Hard Limit

**What it means:** The response body from any Vercel Function (API route) cannot exceed 4.5 MB. Exceeding it returns HTTP 413.

**Risk for this project:** The Hot 100 chart page returns 100 rows; the Billboard 200 returns 200 rows. Each row has ~10-15 fields. This is far under 4.5 MB for JSON. However, if a future "export all history" feature is added, this limit matters.

**Prevention:** Keep pagination on any list endpoint. Never return unbounded query results. The Records leaderboards should apply LIMIT to all queries (which they already do in the existing service layer).

**Detection:** HTTP 413 errors in Vercel logs; response size warnings.

---

### Function Timeout: 10s Default (Hobby), 300s With Fluid Compute

**What it means:**
- Hobby plan with standard functions: 10 second maximum duration
- Hobby plan with Fluid Compute enabled: 300 seconds default
- Pro plan with Fluid Compute: up to 800 seconds

**Risk for this project:** The pg_trgm fuzzy search query against all songs/albums/artists is the most expensive operation. On a cold Neon compute with cold memory buffers, this query could take 2-5 seconds. Combined with Vercel function cold start overhead, hitting 10s is plausible under worst conditions.

**Prevention:**
- Enable Fluid Compute in Vercel project settings to raise the effective timeout to 300s.
- Set explicit `maxDuration` in route configuration for the search endpoint:
  ```typescript
  export const maxDuration = 30; // seconds
  ```
- Add GIN indexes on all fuzzy-searched columns before deployment (the existing codebase may already have these — verify in the migration).
- Apply `LIMIT` to fuzzy search queries (already done in the existing service layer — preserve this).
- Keep the Neon compute warm with periodic pings to avoid cold buffer compounding with slow queries.

**Detection:** FUNCTION_INVOCATION_TIMEOUT (HTTP 504) errors in Vercel logs; function duration approaching 10s in dashboard.

**Phase:** Infrastructure phase (enable Fluid Compute before any routes go live); performance phase (index verification).

---

### Function Bundle Size: 250 MB Uncompressed

**What it means:** All code imported by a function (node_modules included) must be under 250 MB after tracing.

**Risk for this project:** Low. The `pg` (node-postgres) driver is small. No heavy native dependencies.

**Prevention:** Avoid importing large libraries (e.g., full `lodash`, heavy data processing libs) inside API routes. Use `outputFileTracingIncludes` in `next.config.ts` to audit bundle contents if the limit is approached.

---

### File Descriptors: 1,024 Shared Across Concurrent Executions

**What it means:** All concurrent function invocations on the same Vercel instance share a pool of 1,024 file descriptors. Database connections consume file descriptors.

**Risk for this project:** Moderate. If many concurrent requests each hold a database connection, file descriptor exhaustion can occur before connection count limits are hit.

**Prevention:**
- Use the Neon HTTP transport (which does not hold a persistent TCP socket) for single-query-per-request patterns.
- Alternatively, use `attachDatabasePool` with a small pool size (2-5 connections).
- Do not create new connections without reusing them.

---

### Vercel Hobby Plan: No Custom Headers on Caching

**What it means:** On the Hobby plan, CDN caching via `Cache-Control` headers on API responses is limited. Pro plan gets full edge caching.

**Risk for this project:** If deploying on Hobby plan, aggressive in-application caching (via `unstable_cache` and `revalidate`) is the primary mechanism. Edge caching is less reliable.

**Prevention:** Rely on Next.js `unstable_cache` and ISR (`revalidate`) rather than raw `Cache-Control` headers for data caching on Hobby plan.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Database client setup | Module-level pool without `attachDatabasePool`; wrong connection string | Use pooled URL + `attachDatabasePool` or Neon HTTP driver from day one |
| Data migration | Sequence values wrong post-restore; `pg_restore` using pooled URL | Validate all sequences; use `DATABASE_URL_UNPOOLED` for restore |
| pg_trgm search | GIN indexes missing or extension not enabled on Neon | `CREATE EXTENSION pg_trgm`; verify indexes post-migration; test cold-start query time |
| Charts page | Sequential queries for chart + metadata; missing Suspense | `Promise.all` for parallel queries; `<Suspense>` in parent layout |
| Records page | Expensive aggregations re-run every request | `unstable_cache` with weekly `revalidate` |
| Artist/Song/Album detail | 3 independent queries run sequentially | `Promise.all` for parallel fetch |
| Search route | Fuzzy search timeout on cold compute | Verify GIN index exists; `maxDuration` config; keep-warm cron |
| All API routes | Server Component calling own API route | Import query functions directly; no `fetch('/api/...')` in Server Components |
| Deployment | Neon compute cold start on first visitor | Keep-warm cron job; verify collocated regions; `unstable_cache` on heavy reads |

---

## Sources

- [Neon Connection Pooling Docs](https://neon.com/docs/connect/connection-pooling) — PgBouncer transaction mode limits, max connections by compute size (HIGH confidence)
- [Neon Connection Latency Docs](https://neon.com/docs/connect/connection-latency) — Cold start latency, mitigation strategies (HIGH confidence)
- [Neon Compute Lifecycle Docs](https://neon.com/docs/introduction/compute-lifecycle) — Auto-suspend defaults, session state loss on resume (HIGH confidence)
- [Neon Vercel Connection Methods](https://neon.com/docs/guides/vercel-connection-methods) — `attachDatabasePool`, pooled vs unpooled URL guidance (HIGH confidence)
- [Neon Migrate from Postgres Docs](https://neon.com/docs/import/migrate-from-postgres) — `--no-owner`, `--no-blobs`, sequence issues (HIGH confidence)
- [Neon pg_trgm Extension Docs](https://neon.com/docs/extensions/pg_trgm) — GIN/GiST index setup, similarity threshold (HIGH confidence)
- [Vercel Functions Limits](https://vercel.com/docs/functions/limitations) — 4.5 MB payload, 300s/800s timeout, 1024 file descriptors, 250 MB bundle (HIGH confidence)
- [Vercel Common Next.js App Router Mistakes](https://vercel.com/blog/common-mistakes-with-the-next-js-app-router-and-how-to-fix-them) — Server Component anti-patterns, Suspense placement, caching (HIGH confidence)
- [Next.js App Router Docs — Data Fetching Patterns](https://nextjs.org/docs/14/app/building-your-application/data-fetching/patterns) — Parallel vs sequential fetching, `Promise.all` (HIGH confidence)
- [Next.js Route Handlers Caching Behavior](https://github.com/vercel/next.js) — Next.js 15 GET handler not cached by default (HIGH confidence — Context7 verified)
- [Neon Free Tier Limits 2025-2026](https://neon.com/docs/introduction/plans) — 100 CU-hours, 0.5 GB, 10 branches, mandatory scale-to-zero (MEDIUM confidence — verified via search)
