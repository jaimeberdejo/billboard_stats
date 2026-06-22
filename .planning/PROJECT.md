# Billboard Stats — Next.js Frontend

## What This Is

A public web app that replaces the existing Streamlit interface with a polished Next.js UI deployed on Vercel. It surfaces Billboard Hot 100 and Billboard 200 chart data — songs, albums, artists, records — drawn from a PostgreSQL database that's kept current by an independent Python ETL pipeline.

## Core Value

Any visitor can browse current chart rankings, search any artist/song/album, and explore historical records — all fast, public, and without friction.

## Current State

**Shipped:** ✅ v1.0 Initial Next.js Release (2026-06-22)

The Streamlit interface has been fully replaced by a read-only public Next.js web app,
deployed to Vercel on a Neon PostgreSQL database. Latest Charts, Search, Records, and
Song/Album/Artist detail pages are all live. The Python ETL writes to Neon and runs
automatically every week via GitHub Actions.

See `.planning/MILESTONES.md` for the full v1.0 record and `.planning/milestones/v1.0-ROADMAP.md`
for archived phase detail.

**Next milestone:** Not yet defined. Run `/gsd-new-milestone` to scope the next version.
The Natural-Language Query feature (former Phases 7-9) was removed from scope.

## Requirements

### Validated

- ✓ PostgreSQL database with Hot 100 and Billboard 200 chart history (1958–present) — existing
- ✓ ETL pipeline fetching Billboard chart data via `billboard.py` — existing
- ✓ Data models: songs, albums, artists, chart_weeks, chart entries, song_stats, album_stats, artist_stats — existing
- ✓ Fuzzy search via `pg_trgm` PostgreSQL extension — existing
- ✓ Service layer with records, artist, song, album, and chart queries — existing

- ✓ Next.js App Router project with TypeScript and Tailwind CSS — v1.0
- ✓ Neon PostgreSQL hosting — migrated existing database, ETL points at Neon — v1.0
- ✓ Next.js API routes replacing Python services (charts, search, records, song/album/artist detail) — v1.0
- ✓ Latest Charts page — HOT 100 / B200 toggle, week selector, ranked table with movement badges — v1.0
- ✓ Search page — fuzzy search across songs, albums, artists with tabbed results — v1.0
- ✓ Records page — preset leaderboards + custom query builder — v1.0
- ✓ Data Status page — read-only display of table row counts and latest chart dates — v1.0
- ✓ Song detail page — stats bar, chart run SVG visualization, week-by-week history table, artist pills — v1.0
- ✓ Album detail page — stats bar, chart run SVG visualization, week-by-week history table, artist pills — v1.0
- ✓ Artist detail page — stats bar, Hot 100 songs table, Billboard 200 albums table — v1.0
- ✓ Mobile-responsive layout with bottom nav (matching prototype) — v1.0
- ✓ Vercel deployment with Neon environment variable wired up — v1.0
- ✓ Automated weekly Python ETL via GitHub Actions (added Phase 6) — v1.0

### Active

(None — v1.0 shipped. Next milestone not yet scoped; run `/gsd-new-milestone`.)

### Out of Scope

- Streamlit app — replaced entirely by this project
- Telegram bot — dropped for now, can be revisited in a future milestone
- Authentication — public site, no login needed
- "Update Now" button functionality — ETL runs independently; UI is read-only in v1
- New features beyond the HTML prototype — ship the prototype faithfully first

## Context

**Post-v1.0 state.** The Next.js app is live in production on Vercel (~7,480 LOC TypeScript
across 51 `src/` files), backed by Neon PostgreSQL. The Python ETL writes to Neon and runs
weekly via GitHub Actions (`schedule` + `workflow_dispatch`). The Streamlit app has been fully
replaced. Several post-launch quick tasks refined the UI (date→chart-week links, customizable
result counts, inline drilldowns) and hardened ETL artist-name parsing (protected `&` band names).

The HTML prototype (`BillboardStats.html`) remained the UI reference and was matched faithfully:
Billboard red `#C8102E`, Space Grotesk font, white background, data-dense tables, thin borders,
sticky top nav, mobile bottom nav. The existing PostgreSQL schema and `pg_trgm` fuzzy search
ported to Neon directly with no rewrite.

The Natural-Language Query feature (former Phases 7-9) was explored in roadmap form but removed
from scope before implementation.

## Constraints

- **Hosting**: Vercel (frontend + API routes) + Neon (PostgreSQL) — serverless; no long-running Python processes
- **Database**: Must stay PostgreSQL — schema and `pg_trgm` queries are not being rewritten
- **Design**: Must faithfully match the HTML prototype — not a redesign
- **ETL**: Stays Python, runs independently — no ETL logic moves into Next.js

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Next.js API routes instead of a separate Python backend | Single deployment, fewer moving parts, SQL queries are portable | ✓ Good — services ported cleanly to typed TS route handlers |
| Neon for PostgreSQL hosting | Native Vercel integration, free tier, standard Postgres (pg_trgm works) | ✓ Good — full dataset migrated, pg_trgm works, app + ETL share Neon |
| Replace Streamlit entirely (not run alongside) | Clean break, no dual-maintenance burden | ✓ Good — Streamlit fully retired |
| Drop Telegram bot from scope | Out of scope for this milestone — focus on web UI | ✓ Good — still out of scope |
| Automate weekly ETL via GitHub Actions (Phase 6) | Keep production data fresh without manual runs | ✓ Good — scheduled + manual dispatch verified end to end |
| Drop Natural-Language Query (Phases 7-9) | Removed from scope at v1.0 close — not pursuing | — Pending revisit if a future milestone wants it |

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
*Last updated: 2026-06-22 after v1.0 milestone completion*
