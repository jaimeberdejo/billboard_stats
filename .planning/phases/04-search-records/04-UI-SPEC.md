---
phase: 4
slug: search-records
status: approved
shadcn_initialized: false
preset: none
created: 2026-04-28
reviewed_at: 2026-04-28
---

# Phase 4 — UI Design Contract

> Visual and interaction contract for Search and Records. Derived from the approved HTML prototype, current Next.js implementation, and the existing Streamlit behavior.

## Design System

| Property | Value |
|----------|-------|
| Tool | none |
| Component library | none |
| Icon library | none for this phase |
| Font | Space Grotesk variable font |

Notes:
- Preserve the white/off-white newsroom aesthetic already established in Phases 2 and 3.
- Search and Records are dense analytical surfaces, not dashboards.

## Typography

| Role | Size | Weight | Notes |
|------|------|--------|-------|
| Page heading | 16px / 22px desktop | 700 / 600 | matches existing route headings |
| Body | 12px | 400 | default table/body text |
| Label | 10px | 600 | uppercase with `0.07em` to `0.08em` tracking |
| Interactive inline controls | 11px–12px | 600 | tabs, toggles, sentence-builder segments |

All numeric values must preserve tabular numerals.

## Color

| Role | Value | Usage |
|------|-------|-------|
| Canvas | `#FFFDFA` | page background |
| Surface | `#FFFFFF` | tables and control surfaces |
| Accent | `#C8102E` | active tabs, rank-1 emphasis, inline numeric sentence controls |
| Positive | `#16A34A` | preserved for movement-related semantics where needed |
| Neutral text | `#888888` | secondary copy |
| Border | `rgba(0, 0, 0, 0.1)` | table and panel borders |
| Soft panel | `#F5F5F5` | empty states and inactive surfaces |

## Interaction Contract

- Search page order: heading, search input, tabs with counts, results area.
- Search should feel immediate but restrained: no fetch until 2 characters, no submit button, no extra side panels.
- Records page order: heading, top control bar, optional filter rail/panel, natural-language query builder when in custom mode, then results.
- Tabs and toggles are text-first segmented controls, not pill-heavy or card-heavy widgets.
- Search results and record results use dense tables or leaderboard rows with thin separators and hover-only emphasis.
- Search result rows and record rows that map to songs/albums/artists must navigate directly to the existing detail routes.
- Artist-level record rows that support drilldown expand inline below the selected row; do not navigate away immediately.
- Unsupported chart/record combinations must render terse inline explanation states.
- Empty states should stay subordinate to valid data, using neutral bordered/dashed surfaces only.

## Locked Visual Decisions

- Search tabs stay in the order `Songs`, `Albums`, `Artists`.
- Search result counts appear inline with tab labels after the query becomes valid.
- Records uses the prototype’s sentence-style query builder instead of a standard form stack.
- The Records page may include the richer Streamlit-backed preset list, but its controls and spacing must still visually match the prototype language.
- Do not introduce bright accent chips, chart widgets, or side dashboards for Search and Records.

## Copywriting Contract

| Element | Copy |
|---------|------|
| Search placeholder | `Search artists, songs, albums…` |
| Search min-length helper | `Type at least 2 characters to search.` |
| Empty state | `No songs found` / `No albums found` / `No artists found` |
| Records empty state | `No records found.` |
| Unsupported record note | chart-specific explanatory copy matching the Streamlit behavior |

## Checker Sign-Off

- [x] Copywriting: PASS
- [x] Visual consistency: PASS
- [x] Density / table semantics: PASS
- [x] Color restraint: PASS
- [x] Prototype fidelity: PASS

**Approval:** approved 2026-04-28
