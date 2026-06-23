-- Billboard Music Statistics Platform — Database Schema
-- Requires PostgreSQL 12+ with pg_trgm extension

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================
-- Core Tables
-- ============================================================

-- Individual artists (normalized, deduplicated)
CREATE TABLE artists (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL UNIQUE,
    image_url   TEXT
);

-- Unique songs (identified by title + raw credit)
CREATE TABLE songs (
    id              SERIAL PRIMARY KEY,
    title           VARCHAR(500) NOT NULL,
    artist_credit   VARCHAR(500) NOT NULL,
    image_url       TEXT,
    UNIQUE(title, artist_credit)
);

-- Unique albums
CREATE TABLE albums (
    id              SERIAL PRIMARY KEY,
    title           VARCHAR(500) NOT NULL,
    artist_credit   VARCHAR(500) NOT NULL,
    image_url       TEXT,
    UNIQUE(title, artist_credit)
);

-- Many-to-many: songs <-> normalized artists
CREATE TABLE song_artists (
    song_id     INT REFERENCES songs(id),
    artist_id   INT REFERENCES artists(id),
    role        VARCHAR(20) NOT NULL DEFAULT 'primary',
    PRIMARY KEY (song_id, artist_id)
);

-- Many-to-many: albums <-> normalized artists
CREATE TABLE album_artists (
    album_id    INT REFERENCES albums(id),
    artist_id   INT REFERENCES artists(id),
    role        VARCHAR(20) NOT NULL DEFAULT 'primary',
    PRIMARY KEY (album_id, artist_id)
);

-- Each weekly chart publication
CREATE TABLE chart_weeks (
    id          SERIAL PRIMARY KEY,
    chart_date  DATE NOT NULL,
    chart_type  VARCHAR(20) NOT NULL CHECK (chart_type IN ('hot-100', 'billboard-200')),
    UNIQUE(chart_date, chart_type)
);

-- Weekly Hot 100 position entries
CREATE TABLE hot100_entries (
    id              SERIAL PRIMARY KEY,
    chart_week_id   INT NOT NULL REFERENCES chart_weeks(id),
    song_id         INT NOT NULL REFERENCES songs(id),
    rank            SMALLINT NOT NULL,
    peak_pos        SMALLINT,
    last_pos        SMALLINT,
    weeks_on_chart  SMALLINT,
    is_new          BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(chart_week_id, rank)
);

-- Weekly Billboard 200 position entries
CREATE TABLE b200_entries (
    id              SERIAL PRIMARY KEY,
    chart_week_id   INT NOT NULL REFERENCES chart_weeks(id),
    album_id        INT NOT NULL REFERENCES albums(id),
    rank            SMALLINT NOT NULL,
    peak_pos        SMALLINT,
    last_pos        SMALLINT,
    weeks_on_chart  SMALLINT,
    is_new          BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(chart_week_id, rank)
);

-- ============================================================
-- Multi-Chart Generalization (Phase 9, additive)
-- ============================================================
-- These objects generalize the bifurcated hot100_entries/b200_entries model
-- into a chart registry + a single polymorphic chart_entries table + a
-- per-chart artist rollup. They are STRICTLY ADDITIVE: every v1.0 table,
-- column, and constraint above (hot100_entries, b200_entries,
-- chart_weeks.chart_type + its CHECK, artist_stats, song_stats, album_stats)
-- is kept verbatim so the unchanged v1.0 frontend keeps working. All new
-- statements use IF NOT EXISTS so a fresh install and an existing install
-- converge to the same shape and re-application is a no-op. Seeding of the
-- charts registry and backfill of chart_entries / artist_chart_stats happen
-- in the Phase 9 migration (Plan 02), not here. The chart_weeks.chart_id FK
-- stays NULLABLE until Phase 15.

-- Registry of every chart we ingest (DATA-01). Generalizes the
-- chart_weeks.chart_type CHECK into an open, self-describing table.
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

-- Wire chart_weeks to the registry. NULLABLE FK (additive); backfilled in
-- Plan 02 from the existing chart_type. The chart_type column + its CHECK are
-- KEPT (do NOT drop/narrow — Phase 15 retires them). Do NOT add NOT NULL or a
-- UNIQUE(chart_id, chart_date) constraint here.
ALTER TABLE chart_weeks ADD COLUMN IF NOT EXISTS chart_id INT REFERENCES charts(id);

-- Unified, polymorphic weekly entries (DATA-02). One table for all charts;
-- exactly one of song_id / album_id / artist_id is set per row, enforced by the
-- num_nonnulls CHECK. artist_id is a first-class polymorphic target so Artist
-- 100 (entity_kind='artist') drops in for free in Phase 11 with no schema
-- change. Mirrors the v1.0 per-entry columns (rank, peak_pos, last_pos,
-- weeks_on_chart, is_new) and the UNIQUE(chart_week_id, rank) idempotency
-- constraint from hot100_entries/b200_entries.
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

-- Per-chart artist rollup (DATA-03). One ROW per (artist, chart) — adding a
-- chart adds rows, never columns. Generalizes the per-chart facts that the v1.0
-- artist_stats table hardcodes as hot100_/b200_ columns. Career totals derive
-- by aggregation (SUM/MIN/MAX GROUP BY artist_id) over these rows. The column
-- names declared here are authoritative — Plan 03's INSERT writes exactly these.
-- Coexists with artist_stats (compat); artist_stats is NOT altered or dropped.
CREATE TABLE IF NOT EXISTS artist_chart_stats (
    artist_id        INT  NOT NULL REFERENCES artists(id),
    chart_id         INT  NOT NULL REFERENCES charts(id),
    total_entries    INT  NOT NULL DEFAULT 0,   -- songs OR albums OR direct artist entries on this chart
    total_weeks      INT  NOT NULL DEFAULT 0,   -- summed weeks_on_chart presence on this chart
    number_ones      INT  NOT NULL DEFAULT 0,   -- count of #1 placements on this chart
    best_peak        SMALLINT,                  -- best (lowest) rank achieved on this chart
    max_simultaneous INT  NOT NULL DEFAULT 0,   -- max concurrent entries in a single week
    first_date       DATE,                      -- earliest chart_week date on this chart
    last_date        DATE,                      -- latest chart_week date on this chart
    PRIMARY KEY (artist_id, chart_id)
);

-- ============================================================
-- Pre-computed Stats Tables
-- ============================================================

-- Aggregated stats per song
CREATE TABLE song_stats (
    song_id             INT PRIMARY KEY REFERENCES songs(id),
    total_weeks         INT NOT NULL DEFAULT 0,
    peak_position       SMALLINT,
    weeks_at_peak       INT NOT NULL DEFAULT 0,
    weeks_at_number_one INT NOT NULL DEFAULT 0,
    debut_date          DATE,
    last_date           DATE,
    debut_position      SMALLINT
);

-- Aggregated stats per album
CREATE TABLE album_stats (
    album_id            INT PRIMARY KEY REFERENCES albums(id),
    total_weeks         INT NOT NULL DEFAULT 0,
    peak_position       SMALLINT,
    weeks_at_peak       INT NOT NULL DEFAULT 0,
    weeks_at_number_one INT NOT NULL DEFAULT 0,
    debut_date          DATE,
    last_date           DATE,
    debut_position      SMALLINT
);

-- Aggregated career stats per artist (cross-chart)
CREATE TABLE artist_stats (
    artist_id               INT PRIMARY KEY REFERENCES artists(id),
    total_hot100_songs      INT NOT NULL DEFAULT 0,
    total_b200_albums       INT NOT NULL DEFAULT 0,
    total_hot100_weeks      INT NOT NULL DEFAULT 0,
    total_b200_weeks        INT NOT NULL DEFAULT 0,
    hot100_number_ones      INT NOT NULL DEFAULT 0,
    b200_number_ones        INT NOT NULL DEFAULT 0,
    best_hot100_peak        SMALLINT,
    best_b200_peak          SMALLINT,
    first_chart_date        DATE,
    latest_chart_date       DATE,
    max_simultaneous_hot100 INT NOT NULL DEFAULT 0
);

-- ============================================================
-- Indexes
-- ============================================================

-- Fast lookups for chart runs
CREATE INDEX idx_hot100_song_id ON hot100_entries(song_id);
CREATE INDEX idx_hot100_chart_week ON hot100_entries(chart_week_id);
CREATE INDEX idx_b200_album_id ON b200_entries(album_id);
CREATE INDEX idx_b200_chart_week ON b200_entries(chart_week_id);

-- Multi-chart entry indexes (Phase 9): mirror the per-entry indexes above for
-- the polymorphic chart_entries table — by week, by chart, and a partial index
-- per entity FK so each lookup matches the v1.0 access pattern.
CREATE INDEX IF NOT EXISTS idx_ce_chart ON chart_entries(chart_id);
CREATE INDEX IF NOT EXISTS idx_ce_week ON chart_entries(chart_week_id);
CREATE INDEX IF NOT EXISTS idx_ce_song ON chart_entries(song_id) WHERE song_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ce_album ON chart_entries(album_id) WHERE album_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ce_artist ON chart_entries(artist_id) WHERE artist_id IS NOT NULL;

-- Per-chart artist rollup index (mirrors ARCHITECTURE.md idx_acs_chart).
CREATE INDEX IF NOT EXISTS idx_acs_chart ON artist_chart_stats(chart_id);

-- Fast lookups by date
CREATE INDEX idx_chart_weeks_date ON chart_weeks(chart_date);
CREATE INDEX idx_chart_weeks_type_date ON chart_weeks(chart_type, chart_date);

-- Fast lookups by artist_id on join tables
CREATE INDEX IF NOT EXISTS idx_song_artists_artist ON song_artists(artist_id);
CREATE INDEX IF NOT EXISTS idx_album_artists_artist ON album_artists(artist_id);

-- Artist name search (trigram)
CREATE INDEX idx_artists_name_trgm ON artists USING gin (name gin_trgm_ops);

-- Song/album title search (trigram)
CREATE INDEX idx_songs_title_trgm ON songs USING gin (title gin_trgm_ops);
CREATE INDEX idx_albums_title_trgm ON albums USING gin (title gin_trgm_ops);
