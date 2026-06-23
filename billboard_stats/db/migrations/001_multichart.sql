-- Migration 001 — Multi-Chart Generalization (Phase 9, Plan 02)
-- =============================================================================
-- Operator-applied, STRICTLY ADDITIVE, IDEMPOTENT migration that takes an
-- EXISTING v1.0 production database from the bifurcated
-- hot100_entries/b200_entries shape to the generalized multi-chart shape WITHOUT
-- mutating anything the unchanged v1.0 frontend reads.
--
-- It is applied by billboard_stats/etl/migrate_multichart.py, which wraps the
-- whole thing in a SINGLE transaction and asserts row-count parity, rolling back
-- on any mismatch. The Python runner — NOT this file — owns the parity assertions
-- so a violation can roll back.
--
-- Safety contract (mirrors db/schema.sql's additive Phase 9 block):
--   * DDL is guarded with IF NOT EXISTS so a fresh install and an existing
--     install converge to the same shape and re-application is a no-op. The DDL
--     here is byte-for-byte consistent with the new objects already authored in
--     db/schema.sql by Plan 01.
--   * Seeding uses ON CONFLICT (slug) DO NOTHING, so re-running never duplicates
--     a registry row. entity_kind is the load-bearing field: hot-100 → 'song',
--     billboard-200 → 'album'.
--   * The chart_weeks.chart_id backfill only fills NULLs and KEEPS chart_type
--     populated (Phase 15 retires chart_type, not this migration).
--   * The chart_entries backfill copies hot100_entries (song_id set) and
--     b200_entries (album_id set) into the polymorphic chart_entries table with
--     exactly ONE entity FK per row (so the num_nonnulls(...) = 1 CHECK holds)
--     and SKIPS already-migrated rows via ON CONFLICT (chart_week_id, rank) DO
--     NOTHING, so a re-run inserts zero duplicate rows.
--   * It DROPS, RENAMES, or NARROWS no v1.0 object. hot100_entries, b200_entries,
--     chart_weeks.chart_type + its CHECK, and the *_stats tables are untouched.

-- -----------------------------------------------------------------------------
-- 1. DDL (additive; IF NOT EXISTS) — identical to db/schema.sql's Phase 9 block.
-- -----------------------------------------------------------------------------

-- Registry of every chart we ingest (DATA-01).
CREATE TABLE IF NOT EXISTS charts (
    id          SERIAL PRIMARY KEY,
    slug        VARCHAR(64) NOT NULL UNIQUE,    -- billboard.py slug, e.g. 'hot-100'
    title       VARCHAR(128),                   -- human label, e.g. 'Billboard Hot 100'
    entity_kind VARCHAR(16) NOT NULL CHECK (entity_kind IN ('song', 'album', 'artist')),  -- ranked entity type
    category    VARCHAR(32),                    -- UI grouping, e.g. 'core' | 'genre' | 'artist'
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,  -- include in weekly fetch?
    first_date  DATE,                           -- earliest real chart (post-phantom)
    sort_order  SMALLINT NOT NULL DEFAULT 100
);

-- Wire chart_weeks to the registry. NULLABLE FK (additive); KEEP chart_type.
ALTER TABLE chart_weeks ADD COLUMN IF NOT EXISTS chart_id INT REFERENCES charts(id);

-- Unified, polymorphic weekly entries (DATA-02). Exactly one of
-- song_id / album_id / artist_id is set per row (num_nonnulls CHECK).
CREATE TABLE IF NOT EXISTS chart_entries (
    id              BIGSERIAL PRIMARY KEY,
    chart_id        INT NOT NULL REFERENCES charts(id),
    chart_week_id   INT NOT NULL REFERENCES chart_weeks(id),
    song_id         INT REFERENCES songs(id),    -- exactly one of the three is non-null
    album_id        INT REFERENCES albums(id),
    artist_id       INT REFERENCES artists(id),
    rank            SMALLINT NOT NULL,
    peak_pos        SMALLINT,
    last_pos        SMALLINT,
    weeks_on_chart  SMALLINT,
    is_new          BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (chart_week_id, rank),
    CHECK (num_nonnulls(song_id, album_id, artist_id) = 1)  -- one-of-three polymorphism guard
);

-- Per-chart artist rollup (DATA-03). One ROW per (artist, chart).
CREATE TABLE IF NOT EXISTS artist_chart_stats (
    artist_id        INT  NOT NULL REFERENCES artists(id),
    chart_id         INT  NOT NULL REFERENCES charts(id),
    total_entries    INT  NOT NULL DEFAULT 0,
    total_weeks      INT  NOT NULL DEFAULT 0,
    number_ones      INT  NOT NULL DEFAULT 0,
    best_peak        SMALLINT,
    max_simultaneous INT  NOT NULL DEFAULT 0,
    first_date       DATE,
    last_date        DATE,
    PRIMARY KEY (artist_id, chart_id)
);

-- Multi-chart entry indexes (mirror db/schema.sql).
CREATE INDEX IF NOT EXISTS idx_ce_chart ON chart_entries(chart_id);
CREATE INDEX IF NOT EXISTS idx_ce_week ON chart_entries(chart_week_id);
CREATE INDEX IF NOT EXISTS idx_ce_song ON chart_entries(song_id) WHERE song_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ce_album ON chart_entries(album_id) WHERE album_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ce_artist ON chart_entries(artist_id) WHERE artist_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_acs_chart ON artist_chart_stats(chart_id);

-- -----------------------------------------------------------------------------
-- 2. Seed the charts registry (DATA-01). Idempotent via the slug UNIQUE.
--    entity_kind is load-bearing: hot-100 → song, billboard-200 → album.
-- -----------------------------------------------------------------------------
INSERT INTO charts (slug, title, entity_kind, category, sort_order)
VALUES ('hot-100', 'Billboard Hot 100', 'song', 'core', 1)
ON CONFLICT (slug) DO NOTHING;

INSERT INTO charts (slug, title, entity_kind, category, sort_order)
VALUES ('billboard-200', 'Billboard 200', 'album', 'core', 2)
ON CONFLICT (slug) DO NOTHING;

-- -----------------------------------------------------------------------------
-- 3. Backfill chart_weeks.chart_id from the existing chart_type.
--    Only fills NULLs (idempotent); KEEPS chart_type populated.
-- -----------------------------------------------------------------------------
UPDATE chart_weeks SET chart_id = (SELECT id FROM charts WHERE slug = chart_weeks.chart_type)
WHERE chart_id IS NULL;

-- -----------------------------------------------------------------------------
-- 4. Backfill chart_entries from the two v1.0 entry tables (DATA-02).
--    Each row sets EXACTLY one entity FK (num_nonnulls CHECK = 1):
--    song_id for hot-100, album_id for billboard-200, artist_id stays NULL.
--    ON CONFLICT (chart_week_id, rank) DO NOTHING skips already-migrated rows,
--    so a second run inserts zero duplicates.
-- -----------------------------------------------------------------------------

-- Hot 100: hot100_entries (song_id) → chart_entries (chart_id = hot-100).
-- The JOIN to chart_weeks ON cw.chart_type = 'hot-100' scopes the backfill to
-- rows whose source week is ACTUALLY a hot-100 week (WR-02). In a clean v1.0 DB
-- every hot100_entries row references a hot-100 week, but that invariant is
-- otherwise unverified: were any row to point at a billboard-200 week, an
-- unscoped backfill would label it chart_id=hot-100 while step 3 sets that
-- week's chart_weeks.chart_id to billboard-200, silently corrupting the
-- per-chart rollup. The JOIN guarantees chart_entries.chart_id always agrees
-- with the referenced week's chart_id. Still idempotent/additive via ON
-- CONFLICT (chart_week_id, rank) DO NOTHING.
INSERT INTO chart_entries
    (chart_id, chart_week_id, song_id, rank, peak_pos, last_pos, weeks_on_chart, is_new)
SELECT
    (SELECT id FROM charts WHERE slug = 'hot-100'),
    h.chart_week_id,
    h.song_id,
    h.rank,
    h.peak_pos,
    h.last_pos,
    h.weeks_on_chart,
    h.is_new
FROM hot100_entries h
JOIN chart_weeks cw ON cw.id = h.chart_week_id AND cw.chart_type = 'hot-100'
ON CONFLICT (chart_week_id, rank) DO NOTHING;

-- Billboard 200: b200_entries (album_id) → chart_entries (chart_id = billboard-200).
-- Symmetric chart_type scoping to hot-100 above (WR-02).
INSERT INTO chart_entries
    (chart_id, chart_week_id, album_id, rank, peak_pos, last_pos, weeks_on_chart, is_new)
SELECT
    (SELECT id FROM charts WHERE slug = 'billboard-200'),
    b.chart_week_id,
    b.album_id,
    b.rank,
    b.peak_pos,
    b.last_pos,
    b.weeks_on_chart,
    b.is_new
FROM b200_entries b
JOIN chart_weeks cw ON cw.id = b.chart_week_id AND cw.chart_type = 'billboard-200'
ON CONFLICT (chart_week_id, rank) DO NOTHING;
