# Roadmap

**Milestone:** v1.0 Initial Next.js Release
**Goal:** Create a read-only public web app surfacing Billboard chart data finding — replacing the Streamlit interface with a polished Next.js UI using the prototype HTML.

## Phase 1: Project Setup & Infrastructure
**Goal:** Initialize Next.js project with Tailwind, Neon database connection, and Vercel deployment.
**Requirements:** CORE-01, CORE-02, CORE-03, CORE-05
**Success Criteria:**
1. Next.js App Router app loads locally with Space Grotesk font and Tailwind.
2. Vercel deployment automates on push.
3. API route successfully queries the Neon DB to fetch a test chart row.

## Phase 2: Core Browse & Latest Charts
**Goal:** Implement the main shell and the Latest Charts page.
**Requirements:** BROWSE-01, BROWSE-02, BROWSE-03, BROWSE-04, BROWSE-05, CORE-04
**Success Criteria:**
1. Mobile-responsive layout has sticky top nav on desktop and bottom nav on mobile.
2. Latest Charts page displays Hot 100/B200 tables with correct movement badges.
3. Can toggle between Hot 100 and B200 and select historical weeks.
4. Data status indicator accurately reflects DB row counts and max dates.

## Phase 3: Detail Pages & Visualizations
**Goal:** Implement entity detail pages (Song, Album, Artist) and chart run visualizations.
**Requirements:** DETAILS-01, DETAILS-02, DETAILS-03, DETAILS-04, DETAILS-05
**Plans:** 4 plans
Plans:
- [x] 03-01-PLAN.md — Build typed detail data helpers and validated internal detail APIs.
- [x] 03-02-PLAN.md — Ship shared song/album detail pages with stats bars, history tables, and artist pills.
- [x] 03-03-PLAN.md — Implement the artist detail page with aggregate stats and drill-down catalog tables.
- [x] 03-04-PLAN.md — Add the collapsible chart-run SVG visualization to song and album pages.
**Success Criteria:**
1. Song and Album pages show stats bar and week-by-week chart history table.
2. SVG chart run visualization renders correctly (collapsible, inverted Y-axis, peak dot).
3. Artist page displays career stats and tables for Hot 100 songs and B200 albums.

## Phase 4: Search & Records
**Goal:** Implement fuzzy search and the Records/Leaderboards interfaces.
**Requirements:** SEARCH-01, SEARCH-02, RECORDS-01, RECORDS-02
**Success Criteria:**
1. Search bar triggers fuzzy DB search (min 2 chars) and displays tabbed results with counts.
2. Records page lists preset leaderboards accurately.
3. Custom Query Builder works, returning top-50 results based on selected filters and sort.

### Phase 5: I want to configure neon and deploy the app in vercel

**Goal:** Provision a Neon PostgreSQL project with the full Billboard dataset, wire DATABASE_URL into Vercel, deploy the app to production, and cut over the Python ETL pipeline to write to Neon.
**Requirements:** CORE-02, CORE-03
**Depends on:** Phase 4
**Plans:** 3 plans

Plans:
- [x] 05-01-PLAN.md — Neon project creation and full data migration from localhost (pg_dump/pg_restore, row count verification)
- [x] 05-02-PLAN.md — Vercel deployment: DATABASE_URL env vars (3 scopes), GitHub integration, and production deploy
- [x] 05-03-PLAN.md — Post-deploy smoke tests, Python ETL cutover to Neon, and .env.example update

### Phase 6: update the missing data, last uploaded week is feb 14, configure the ETL to work automatically every week

**Goal:** Backfill the missing production chart data after 2026-02-14, harden freshness logic against invalid future weeks, and automate the existing Python ETL on a weekly schedule.
**Requirements**: CORE-02, BROWSE-05
**Depends on:** Phase 5
**Plans:** 3 plans

Plans:
- [x] 06-01-PLAN.md — Harden ETL chronology and freshness rules so future-dated rows/files cannot masquerade as the latest chart data
- [x] 06-02-PLAN.md — Backfill the missing Neon data, add a manual ETL runner, and document the operator runbook
- [x] 06-03-PLAN.md — Automate the weekly ETL with GitHub Actions and validate manual workflow dispatch

### Phase 7: Natural-Language Query Interpretation

**Goal:** Parse plain-English chart questions into constrained structured query objects with explicit intent classification, parameter extraction, and user-visible query interpretation.
**Requirements**: SEARCH-01, RECORDS-02
**Depends on:** Phase 6
**Plans:** 3 plans

Plans:
- [ ] 07-01-PLAN.md — Define the bounded NLQ schema, allowlisted vocabulary, and normalization helpers.
- [ ] 07-02-PLAN.md — Implement deterministic interpretation and the interpretation-only `/api/query` route.
- [ ] 07-03-PLAN.md — Lock interpretation behavior with executable golden fixtures and a regression runner.

### Phase 8: Safe Query Execution For Records & Search

**Goal:** Map structured natural-language query objects into safe allowlisted backend operations for records and search without permitting arbitrary SQL execution.
**Requirements**: CORE-02, SEARCH-01, RECORDS-02
**Depends on:** Phase 7
**Plans:** 0 plans

Plans:
- [ ] TBD (run /gsd-plan-phase 8 to break down)

### Phase 9: Query Assistant UI For Records & Search

**Goal:** Add a user-facing query assistant that accepts natural-language questions, shows the interpreted query, and renders results through the constrained records/search interface.
**Requirements**: SEARCH-01, RECORDS-01, RECORDS-02
**Depends on:** Phase 8
**Plans:** 0 plans

Plans:
- [ ] TBD (run /gsd-plan-phase 9 to break down)
