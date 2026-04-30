---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: in_progress
last_updated: "2026-04-29T10:25:37.548Z"
last_activity: 2026-04-29 -- Reformulated natural-language query work into phases 07-09
progress:
  total_phases: 9
  completed_phases: 6
  total_plans: 18
  completed_plans: 18
  percent: 100
---

## Current Position

Phase: 07
Plan: Not started
Status: Ready to plan
Last activity: 2026-04-29 -- Reformulated natural-language query work into phases 07-09

## Accumulated Context

**Planned Phase:** 05 (i-want-to-configure-neon-and-deploy-the-app-in-vercel) — 3 plans — 2026-04-29T00:00:00.000Z

**Planned Phase:** 06 (update-the-missing-data-last-uploaded-week-is-feb-14-configu) — 3 plans — 2026-04-29T00:00:00.000Z

**Planned Phase:** 04 (search-records) — 4 plans — 2026-04-28T19:16:15.211Z

### Roadmap Evolution

- Phase 5 added: configure Neon and deploy the app in Vercel
- Phase 6 added: update the missing data, last uploaded week is feb 14, configure the ETL to work automatically every week
- Phase 7 added: constrained natural-language query layer for records/search
- Phase 7 reformulated: natural-language query interpretation
- Phase 8 added: safe query execution for records and search
- Phase 9 added: query assistant UI for records and search

## Quick Tasks Completed

| Date | Quick Task | Summary |
| --- | --- | --- |
| 2026-04-30 | `260430-2cv-implement-all-this-date-input-year-searc` | Added direct chart week jump input, previous/next week buttons, last-week chart fields, and Janet alias merging in artist reads/search. |
| 2026-04-30 | `260430-2zo-investigate-this-some-bands-have-in-thei` | Confirmed the ETL currently splits many valid `&` band names as separate artists; documented concrete examples and the recommended allowlist-based fix. |
| 2026-04-30 | `260430-3c0-fix-ampersand-artist-parsing-so-band-nam` | Added protected `&` act-name parsing in the ETL and unit tests so known band/duo names are preserved while real collaborations still split. |
| 2026-04-30 | `260430-e13-add-customizable-results-count-box-on-re` | Added a 1–1000 results input to the records-page top bar and threaded the requested limit through the API and records queries. |
| 2026-04-30 | `260430-e69-inline-simultaneous-entries-expansion-un` | Moved artist drilldowns inline under leaderboard rows and changed simultaneous-entry drilldowns to show every chart week for the artist, grouped inline by week. |
