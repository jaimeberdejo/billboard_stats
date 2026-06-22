# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — Initial Next.js Release

**Shipped:** 2026-06-22
**Phases:** 6 | **Plans:** 18

### What Was Built
- Read-only public Next.js App Router web app replacing the Streamlit interface, deployed to Vercel.
- Full browse/detail surface: Latest Charts (Hot 100 / B200), Search (fuzzy, tabbed), Records (presets + custom query builder), Data Status, and Song/Album/Artist detail pages with stats bars, week-by-week history, and a collapsible chart-run SVG.
- Typed TypeScript data layer porting the Python services to validated Next.js route handlers.
- Neon PostgreSQL provisioning with full dataset migration, and a Python ETL cut over to Neon and automated weekly via GitHub Actions.

### What Worked
- Porting existing PostgreSQL queries (including `pg_trgm` fuzzy search) to Neon required no rewrite — the "must stay PostgreSQL" constraint paid off.
- Keeping the HTML prototype as the single definitive UI reference kept the build focused and prevented scope creep into a redesign.
- Server-first rendering with graceful DB-backed fallbacks made the browse/detail pages robust.
- Splitting deployment (Phase 5) and data-freshness/automation (Phase 6) out of the original 1-4 scope let the app ship and then harden incrementally.

### What Was Inefficient
- The roadmap accumulated speculative phases (7-9, Natural-Language Query) that were never started and ultimately removed at milestone close — scope that could have stayed in a backlog rather than the active roadmap.
- Several edge cases surfaced only as post-launch quick tasks (ampersand band-name parsing in the ETL, comma-separated multi-artist query placeholder bug) rather than being caught during phase planning.

### Patterns Established
- Typed TS service helpers behind validated route handlers as the standard data-access shape.
- ETL freshness/chronology guards so future-dated rows/files can't masquerade as the latest chart data.
- GitHub Actions (`schedule` + `workflow_dispatch`) as the automation pattern for the independent Python ETL.

### Key Lessons
1. Keep speculative, unscoped features in a backlog — not as numbered active-roadmap phases — so milestone close stays clean.
2. Data-parsing edge cases (artist name splitting, multi-value SQL params) deserve explicit test coverage during planning, not after launch.
3. A faithful prototype reference is a strong anti-scope-creep tool for UI-heavy milestones.

### Cost Observations
- Model mix: not tracked this milestone.
- Notable: 7 post-launch quick tasks refined UX and fixed parsing bugs after the core phases completed.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Key Change |
|-----------|--------|------------|
| v1.0 | 6 | First milestone; established typed-route + Neon/Vercel + automated-ETL baseline |

### Top Lessons (Verified Across Milestones)

1. (Awaiting a second milestone to cross-validate.)
</content>
