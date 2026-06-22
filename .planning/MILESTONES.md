# Milestones

## v1.0 Initial Next.js Release (Shipped: 2026-06-22)

**Phases completed:** 6 phases, 18 plans
**Delivered:** A public, read-only Next.js web app replacing the Streamlit interface — Latest Charts, Search, Records, and Song/Album/Artist detail pages — deployed to Vercel on a Neon PostgreSQL database kept current by an automated weekly Python ETL.

**Key accomplishments:**

- **Foundation & shell** — Next.js App Router with local Space Grotesk branding, Tailwind v4 theme tokens, a Neon health endpoint, and a shared SiteShell (sticky desktop top nav / fixed mobile bottom nav).
- **Typed data layer** — Ported the Python chart, search, records, and detail services to typed TypeScript helpers behind validated Next.js route handlers.
- **Browse & detail UI** — Server-first Latest Charts and Data Status views with movement-aware dense tables, plus Song/Album/Artist detail pages with stats bars, week-by-week history, artist pills, and a collapsible chart-run SVG visualization.
- **Search & Records** — Fuzzy tabbed search and the Records page with preset leaderboards plus a sentence-style custom query builder over the typed records API.
- **Neon + Vercel deployment** — Provisioned Neon PostgreSQL, migrated the full Billboard dataset, wired DATABASE_URL across Vercel scopes, and shipped to production with verified smoke tests.
- **Automated weekly ETL** — Cut the Python ETL over to Neon, hardened freshness/chronology rules, backfilled missing data, and automated weekly runs via GitHub Actions (`schedule` + `workflow_dispatch`).

**Stats:** ~7,480 LOC TypeScript across 51 `src/` files. Branching strategy: none (trunk).

---
