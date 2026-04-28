---
phase: 3
slug: detail-pages-visualizations
status: approved
shadcn_initialized: false
preset: none
created: 2026-04-28
reviewed_at: 2026-04-28
---

# Phase 3 — UI Design Contract

> Visual and interaction contract for detail pages and chart-run visualizations. Derived from the approved Phase 2 contract, current Next.js implementation, and the HTML prototype.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none |
| Preset | not applicable |
| Component library | none |
| Icon library | none for this phase; use text glyphs or inline SVG only |
| Font | Space Grotesk variable font from local `next/font/local` |

Notes:
- Source: Phase 2 approved UI-SPEC, `src/app/globals.css`, `src/app/layout.tsx`.
- This phase must extend the existing dense newsroom UI. Do not introduce shadcn, Radix, or a card-heavy dashboard pattern.

---

## Spacing Scale

Declared values (must be multiples of 4):

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Inline glyph gaps, micro-badge insets, chart annotation offsets |
| sm | 8px | Compact cell padding, pill interior padding, small control gaps |
| md | 16px | Default page rhythm, stats-bar spacing, section spacing |
| lg | 24px | Separation between header, stats bar, visualization, and tables |
| xl | 32px | Major section breaks on desktop detail pages |
| 2xl | 48px | Reserved for full-page empty/error states |
| 3xl | 64px | Reserved for future expanded records or comparison layouts |

---

## Typography

| Role | Size | Weight | Line Height |
|------|------|--------|-------------|
| Body | 12px | 400 | 1.45 |
| Label | 10px | 600 | 1.3 |
| Heading | 16px | 600 | 1.2 |
| Display | 22px desktop / 16px mobile | 600 | 1.2 |

Additional type rules:
- Stats labels use `10px`, uppercase, `0.07em` tracking, muted gray.
- Table headers use `10px`, weight `600`, uppercase, `0.08em` tracking.
- Back link, visualization toggle, and artist pills use `12px` weight `600`.
- Large numeric stats use `16px` weight `600`; date-valued stats use `12px` weight `400` to avoid overflow.
- All numeric fields, ranks, weeks, and axis labels must preserve tabular numerals.

---

## Color

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `#FFFDFA` | App canvas, page background, long-form detail surfaces |
| Secondary (30%) | `#FFFFFF` | Stats cells, tables, nav surfaces, visualization panel interior |
| Accent (10%) | `#C8102E` | Peak stats, chart line, peak dot, rank-1 values, active emphasis |
| Destructive | `#DC2626` | Downward movement indicators and true error treatment only |

Accent reserved for: Billboard brand mark, `#1`/peak emphasis, chart-run SVG line and peak marker, `NEW` badge, and the currently expanded or focal state where a single metric needs emphasis. Do not use accent as the default color for all links, all chips, or all table rows.

Supplemental semantic colors:
- Positive movement: `#16A34A`
- Neutral movement / flat state: `#AAAAAA`
- Secondary text: `#888888`
- Border gray: `rgba(0, 0, 0, 0.1)` / prototype `#E5E5E5`
- Soft panel gray: `#F5F5F5`
- Error background: `#FCEDEE`
- Primary dark text: `#0A0A0A`

---

## Copywriting Contract

| Element | Copy |
|---------|------|
| Primary CTA | Show chart run |
| Empty state heading | No chart history available |
| Empty state body | This page does not have chart history to display yet. Try another song, album, or artist, or confirm the database stats tables are populated. |
| Error state | Could not load detail data. Refresh the page or return to Latest Charts and try again. |
| Destructive confirmation | Not applicable in Phase 3 — no destructive user actions |

Additional copy rules:
- Section labels must stay terse and data-first: `Chart History`, `Artists`, `Hot 100 Songs`, `Billboard 200 Albums`.
- The visualization toggle label must include the noun `Chart Run` or `Chart Run Visualization`; avoid generic labels like `Show graph`.
- Artist pills use the canonical artist display name only. No helper verbs inside the chip.
- Missing-entity copy should stay literal: `Artist not found` or `Not found` is acceptable; do not use playful empty-state language.

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none | not required |
| third-party registry | none | not applicable |

Safety evidence:
- `components.json` is absent in the current repo.
- Phase 2 approved contract already locked `Tool: none`; Phase 3 continues that baseline.

---

## Interaction Contract

- Keep the Phase 2 shell unchanged: sticky desktop top nav, mobile bottom nav, dense page padding, and text-first navigation states.
- Detail pages must follow this order: back link, title block, stats bar, optional visualization toggle/panel, primary history table, related-entity pills or secondary tables.
- Song and album pages use a single-column header stack: title first, artist line second. The title is the visual anchor; the artist credit is secondary muted text.
- Artist detail pages use the artist name as the display title and a date-range subtitle beneath it when available.
- Stats bars must render as a compact grid with thin dividers, not individual elevated cards. On mobile, collapse to two columns. On larger screens, auto-fit across the container.
- Song and album stats must always prioritize: peak, weeks on chart, weeks at `#1`, weeks at peak, debut position, debut date.
- Artist stats must prioritize aggregate output and scale: Hot 100 songs, Billboard 200 albums, `#1` totals, weeks totals, best peak, and max simultaneous entries.
- Artist pills are outlined chips with wrap behavior. They route to the artist detail page and change border/text color on hover; they do not fill solid red by default.
- Tables must stay dense, semantic, and horizontally resilient. Use sticky headers inside scroll containers where the table height is constrained.
- Song/album chart-history rows must be ordered newest week first. Columns stay `Week`, `Pos`, `Mv`, `Lw`, `Pk`, `Wks`.
- Movement treatment in history tables must match Phase 2 browse semantics: green up, red down, muted flat, `NEW` badge for debut/re-entry rows as appropriate.
- Chart-run visualization is collapsed by default and expands inline above the history table. The toggle is a text control, not a full-width button.
- Only render the visualization when at least two chart points exist. Otherwise omit the module instead of showing an empty graph frame.
- The chart-run SVG must be responsive, use an inverted Y-axis (`#1` at the top), and annotate the peak point with a red dot and `#rank` label.
- Use five Y-axis ticks: `1, 25, 50, 75, 100` for Hot 100 and `1, 50, 100, 150, 200` for Billboard 200.
- The SVG should show only the first and last dates on the X-axis. Do not crowd the chart with every week label.
- Tables on artist pages remain the primary drill-down surface. Each row should clearly route to the relevant song or album page without adding a separate action column.
- Empty states should appear inline within the page content area and remain visually subordinate to valid data, using dashed or lightly bordered neutral surfaces only.

---

## Phase 3 Locked Visual Decisions

- Preserve the white/off-white newsroom aesthetic from Phase 2 and the prototype. Do not switch to colorful cards, gradients, or dashboard chrome.
- Detail pages are still read-only analytical surfaces. They should feel reference-grade and compact rather than promotional.
- Use red sparingly so the chart line, `#1` values, and peak annotations carry real emphasis.
- Visualization should feel like an embedded research aid, not the hero of the page. The stats bar and table remain the primary information architecture.
- Keep borders thin and spacing tight. The density should support scanning week-by-week chart history without visual fatigue.

---

## Checker Sign-Off

- [x] Dimension 1 Copywriting: PASS
- [x] Dimension 2 Visuals: PASS
- [x] Dimension 3 Color: PASS
- [x] Dimension 4 Typography: PASS
- [x] Dimension 5 Spacing: PASS
- [x] Dimension 6 Registry Safety: PASS

**Approval:** approved 2026-04-28
