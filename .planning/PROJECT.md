# Billboard Stats — Next.js Frontend

## What This Is

A public web app that replaces the existing Streamlit interface with a polished Next.js UI deployed on Vercel. It surfaces Billboard Hot 100 and Billboard 200 chart data — songs, albums, artists, records — drawn from a PostgreSQL database that's kept current by an independent Python ETL pipeline.

## Core Value

Any visitor can browse current chart rankings, search any artist/song/album, and explore historical records — all fast, public, and without friction.

## Requirements

### Validated

- ✓ PostgreSQL database with Hot 100 and Billboard 200 chart history (1958–present) — existing
- ✓ ETL pipeline fetching Billboard chart data via `billboard.py` — existing
- ✓ Data models: songs, albums, artists, chart_weeks, chart entries, song_stats, album_stats, artist_stats — existing
- ✓ Fuzzy search via `pg_trgm` PostgreSQL extension — existing
- ✓ Service layer with records, artist, song, album, and chart queries — existing

### Active

- [ ] Next.js App Router project with TypeScript and Tailwind CSS
- [ ] Neon PostgreSQL hosting — migrate existing database, update ETL connection string
- [ ] Next.js API routes replacing Python services (charts, search, records, song/album/artist detail)
- [ ] Latest Charts page — HOT 100 / B200 toggle, week selector, ranked table with movement badges
- [ ] Search page — fuzzy search across songs, albums, artists with tabbed results
- [ ] Records page — preset leaderboards (most weeks at #1, longest runs, etc.) + custom query builder
- [ ] Data Status page — read-only display of table row counts and latest chart dates
- [ ] Song detail page — stats bar, chart run SVG visualization, week-by-week history table, artist pills
- [ ] Album detail page — stats bar, chart run SVG visualization, week-by-week history table, artist pills
- [ ] Artist detail page — stats bar, Hot 100 songs table, Billboard 200 albums table
- [ ] Mobile-responsive layout with bottom nav (matching prototype)
- [ ] Vercel deployment with Neon environment variable wired up

### Out of Scope

- Streamlit app — replaced entirely by this project
- Telegram bot — dropped for now, can be revisited in a future milestone
- Authentication — public site, no login needed
- "Update Now" button functionality — ETL runs independently; UI is read-only in v1
- New features beyond the HTML prototype — ship the prototype faithfully first

## Context

The project already has a fully mapped codebase (`/planning/codebase/`). The Streamlit app in `app.py` covers the same pages as the prototype — Latest Charts, Search, Records, Data Status — plus artist/song/album detail views. All SQL queries exist in `services/`; they'll be translated to TypeScript in Next.js API routes.

The HTML prototype (`BillboardStats.html`) is the definitive UI reference. Design system: Billboard red `#C8102E`, Space Grotesk font, white background, data-dense tables, thin borders, sticky top nav, mobile bottom nav.

The existing PostgreSQL schema and query patterns can be used directly. `pg_trgm` is supported by Neon (standard PostgreSQL extension). ETL will simply point at the Neon connection string instead of `localhost`.

## Constraints

- **Hosting**: Vercel (frontend + API routes) + Neon (PostgreSQL) — serverless; no long-running Python processes
- **Database**: Must stay PostgreSQL — schema and `pg_trgm` queries are not being rewritten
- **Design**: Must faithfully match the HTML prototype — not a redesign
- **ETL**: Stays Python, runs independently — no ETL logic moves into Next.js

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Next.js API routes instead of a separate Python backend | Single deployment, fewer moving parts, SQL queries are portable | — Pending |
| Neon for PostgreSQL hosting | Native Vercel integration, free tier, standard Postgres (pg_trgm works) | — Pending |
| Replace Streamlit entirely (not run alongside) | Clean break, no dual-maintenance burden | — Pending |
| Drop Telegram bot from scope | Out of scope for this milestone — focus on web UI | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-27 after initialization*
