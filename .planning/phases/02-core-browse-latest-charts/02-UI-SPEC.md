---
phase: 2
slug: core-browse-latest-charts
status: approved
shadcn_initialized: false
preset: none
created: 2026-04-27
---

# Phase 2 — UI Design Contract

> Visual and interaction contract for frontend phases. Generated locally from the prototype and Phase 2 research, verified against the UI-SPEC template and phase requirements.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none |
| Preset | not applicable |
| Component library | none |
| Icon library | none for Phase 2 baseline; use text glyphs or inline SVG only if needed |
| Font | Space Grotesk variable font from local `next/font/local` |

---

## Spacing Scale

Declared values (must be multiples of 4):

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Toggle button vertical padding, micro-badge insets |
| sm | 8px | Table cell horizontal padding, compact form control padding |
| md | 16px | Default page side padding, nav horizontal padding, section rhythm |
| lg | 24px | Card and shell interior padding on desktop |
| xl | 32px | Major section separation in the browse shell |
| 2xl | 48px | Reserved for future detail-page section breaks |
| 3xl | 64px | Reserved for full-page hero or empty-state compositions |

Exceptions: `12px` is allowed for compact section-header gaps and mobile page padding because the prototype already uses that density and it keeps the charts view compact.

---

## Typography

| Role | Size | Weight | Line Height |
|------|------|--------|-------------|
| Body | 12px | 400 | 1.45 |
| Label | 11px | 600 | 1.3 |
| Heading | 16px | 700 | 1.2 |
| Display | 15px | 700 | 1.1 |

Additional type rules:
- Table headers use `10px`, weight `600`, uppercase, tracking `0.08em`.
- Nav links use `12px`, weight `500`, compact tracking.
- All rank, movement, LW, PK, WKS, and row-count figures must preserve tabular numerals.

---

## Color

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `#FFFFFF` | App background, sticky nav surfaces, table header background |
| Secondary (30%) | `#F5F5F5` | Hover surfaces, inactive controls, soft panels, compact status containers |
| Accent (10%) | `#C8102E` | Active chart toggle, Billboard wordmark, rank-1 emphasis, NEW badge |
| Destructive | `#DC2626` | Downward movement indicators only when the chart position worsens |

Accent reserved for: active chart toggle state, Billboard branding, rank-1 treatment, NEW badge, and focal status highlights. Do not use accent as the default color for all links or all interactive elements.

Supplemental semantic colors:
- Positive movement: `#16A34A`
- Neutral movement / flat state: `#AAAAAA`
- Secondary text: `#888888`
- Primary dark text: `#0A0A0A`

---

## Copywriting Contract

| Element | Copy |
|---------|------|
| Primary CTA | No primary CTA in Phase 2; this is a browse surface, not a conversion flow |
| Empty state heading | No chart data available |
| Empty state body | Try another chart week or confirm the database has Billboard data loaded. |
| Error state | Could not load chart data. Refresh the page or try a different week. |
| Destructive confirmation | Not applicable in Phase 2 — no destructive user actions |

Additional copy rules:
- Navigation labels must remain `Latest Charts`, `Search`, `Records`, and `Data Status`.
- Chart toggle labels must be exactly `HOT 100` and `B200`.
- Dense UI copy should prefer terse data vocabulary over explanatory marketing phrasing.

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none | not required |
| third-party registry | none | shadcn view + diff required if introduced later |

---

## Interaction Contract

- Desktop navigation is a sticky top bar at `44px` height with the brand left-aligned and text nav items on the right.
- Mobile navigation hides desktop nav links and uses a bottom nav with four items; labels truncate to the first word when space is constrained.
- Latest Charts uses one compact control row: chart toggle on the left, week selector next, entry count aligned to the right.
- Chart tables are dense, semantic tables with sticky headers, horizontal overflow handling, and hover states that do not overpower the data.
- Table row clicks may route to future detail pages, but the row styling must already communicate clickability via hover-only surface change, not heavy buttons.
- Data Status uses a compact stats bar followed by a simple status table, matching the prototype’s read-only operational feel.

---

## Phase 2 Locked Visual Decisions

- Keep the prototype’s white-first, newsroom-style visual language. Do not redesign this into a card-heavy SaaS dashboard.
- Use thin borders and dense spacing. The browse experience should feel data-first and compact, not airy.
- Preserve the prototype’s sticky table header behavior, with the header offset below the sticky top nav.
- Use the Phase 1 local Space Grotesk setup and Tailwind v4 CSS token approach. Do not introduce a separate typography or component framework in this phase.
- Data Status should remain visually subordinate to Latest Charts. It is informational support, not the primary focal screen.

---

## Checker Sign-Off

- [x] Dimension 1 Copywriting: PASS
- [x] Dimension 2 Visuals: PASS
- [x] Dimension 3 Color: PASS
- [x] Dimension 4 Typography: PASS
- [x] Dimension 5 Spacing: PASS
- [x] Dimension 6 Registry Safety: PASS

**Approval:** approved 2026-04-27
