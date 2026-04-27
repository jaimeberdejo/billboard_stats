# Requirements

**Milestone:** v1.0 Initial Next.js Release
**Status:** Defined

---

## Active Requirements (v1.0)

### CORE: Infrastructure & Navigation
- [ ] **CORE-01**: Setup Next.js App Router project with TypeScript and Tailwind
- [ ] **CORE-02**: Connect to Neon PostgreSQL database and setup typed API routes replacing Python services
- [ ] **CORE-03**: Deploy application to Vercel
- [ ] **CORE-04**: Implement mobile-responsive layout (sticky top nav desktop, bottom nav mobile)
- [ ] **CORE-05**: Implement tabular-nums font-variant and dense data-first design (Space Grotesk)

### BROWSE: Latest Charts
- [ ] **BROWSE-01**: Display Latest Charts (Hot 100 & B200) in ranked tables with sticky headers
- [ ] **BROWSE-02**: Toggle between Hot 100 and Billboard 200
- [ ] **BROWSE-03**: Select specific historical chart weeks via dropdown
- [ ] **BROWSE-04**: Display movement indicators (green up, red down, gray flat, NEW/RE badges)
- [ ] **BROWSE-05**: Display data status / freshness indicator (row counts and latest chart dates)

### DETAILS: Entity Pages
- [ ] **DETAILS-01**: Song detail page with stats bar (peak, total weeks, debut, etc) and artist pill links
- [ ] **DETAILS-02**: Album detail page with stats bar and artist pill links
- [ ] **DETAILS-03**: Artist detail page with career aggregates (max simultaneous songs) and Hot 100/B200 tables
- [ ] **DETAILS-04**: Week-by-week chart history table for songs and albums
- [ ] **DETAILS-05**: Chart run SVG visualization (inline, collapsible, y-axis inverted, peak annotated)

### SEARCH: Discoverability
- [ ] **SEARCH-01**: Fuzzy search across songs, albums, and artists (min 2 chars)
- [ ] **SEARCH-02**: Tabbed search results (Songs/Albums/Artists) showing exact result counts

### RECORDS: Leaderboards & Queries
- [ ] **RECORDS-01**: Preset leaderboards (most weeks at #1, longest runs, biggest debuts, etc)
- [ ] **RECORDS-02**: Custom Query Builder filtering by metric, sort, artist, peak, debut, and min-weeks

## Future Requirements (Deferred)
- None yet

## Out of Scope
- Streamlit app support (deprecated)
- Telegram bot integration
- User authentication / accounts
- "Update Now" ETL trigger button
- Cross-platform chart data (Spotify/Apple)
- Comparison mode (artist vs artist)
- Dark mode
- Data export to CSV/JSON

---

## Traceability

- **CORE-01**: Phase 1
- **CORE-02**: Phase 1
- **CORE-03**: Phase 1
- **CORE-04**: Phase 2
- **CORE-05**: Phase 1
- **BROWSE-01**: Phase 2
- **BROWSE-02**: Phase 2
- **BROWSE-03**: Phase 2
- **BROWSE-04**: Phase 2
- **BROWSE-05**: Phase 2
- **DETAILS-01**: Phase 3
- **DETAILS-02**: Phase 3
- **DETAILS-03**: Phase 3
- **DETAILS-04**: Phase 3
- **DETAILS-05**: Phase 3
- **SEARCH-01**: Phase 4
- **SEARCH-02**: Phase 4
- **RECORDS-01**: Phase 4
- **RECORDS-02**: Phase 4
