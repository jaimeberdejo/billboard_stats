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
